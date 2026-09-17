import assert from 'node:assert/strict';
import test from 'node:test';
import seed from './fixtures/baseline-campaign.json';
import { parseSubmission } from '../src/validation';
import { groupObservations } from '../src/aggregation';
import { BASELINE, SECTIONS } from '../src/baseline';
import { observations, type Submission } from '../src/model';
import { collectWinners, winnerKey, closeRatePercent } from '../src/winners';

function campaign(
  id: string,
  frontend: string,
  host: string,
  rates: (number | null)[],
): Submission {
  const c = structuredClone(parseSubmission(seed));
  c.id = id;
  c.host.id = host;
  c.host.label = host;
  c.planned_runs = rates.length;
  c.runs = rates.map((rate, i) => {
    const r = structuredClone(c.runs[0]);
    r.id = `run-${i}`;
    r.frontend = frontend;
    r.repetition = i + 1;
    r.metrics.submitted_hz = rate;
    r.status = rate === null ? 'failed' : 'ok';
    r.samples = rate === null ? 0 : 100;
    return r;
  });
  return c;
}

test('best observed record per frontend is selected across hosts using group medians', () => {
  const input = observations([
      campaign('slow', 'alpha', 'host-a', [10, 20, 999]),
      campaign('fast', 'alpha', 'host-b', [40, 50, 60]),
      campaign('rival', 'beta', 'host-c', [45, 45, 45]),
    ]),
    before = structuredClone(input);
  const { boards } = collectWinners(input);
  assert.equal(boards.length, 1);
  assert.deepEqual(
    boards[0].records.map((r) => [r.frontend, r.rank, r.score]),
    [
      ['alpha', 1, 50],
      ['beta', 2, 45],
    ],
  );
  assert.equal(boards[0].records[0].groups[0].representative.campaign.host.id, 'host-b');
  assert.equal(boards[0].evaluatedGroups, 3);
  assert.equal(boards[0].hosts, 3);
  assert.deepEqual(input, before);
});

test('campaign medians keep equal weight before record selection', () => {
  const { boards } = collectWinners(
    observations([
      campaign('many', 'alpha', 'same-host', Array(100).fill(60)),
      campaign('few', 'alpha', 'same-host', [30]),
      campaign('other', 'beta', 'other-host', [50]),
    ]),
  );
  assert.equal(boards[0].records[0].frontend, 'beta');
  assert.equal(boards[0].records[1].score, 45);
});

test('close-rate resource ties retain all frontend and host records with shared ranks', () => {
  const { boards } = collectWinners(
    observations([
      campaign('a', 'alpha', 'host-a', [59.96]),
      campaign('b', 'alpha', 'host-b', [60.04]),
      campaign('c', 'beta', 'host-c', [60]),
      campaign('d', 'gamma', 'host-d', [40]),
    ]),
  );
  assert.deepEqual(
    boards[0].records.map((r) => r.rank),
    [1, 1, 3],
  );
  assert.equal(boards[0].records[0].groups.length, 2);
  assert.equal(boards[0].records[0].score, 60);
});

function withResources(
  c: Submission,
  memory: (number | null)[],
  cpu: (number | null)[],
): Submission {
  for (const [i, r] of c.runs.entries()) {
    r.metrics.rss_peak_mib = memory[i % memory.length];
    r.metrics.cpu_mean_percent = cpu[i % cpu.length];
  }
  return c;
}
function system(
  id: string,
  rate: number,
  memory: number | null,
  cpu: number | null,
  frontend = id,
): Submission {
  return withResources(campaign(id, frontend, id, [rate]), [memory], [cpu]);
}

test('close throughput favors memory first, then CPU; materially slower rates stay behind', () => {
  const input = observations([
    system('fast', 100, 500, 1),
    system('efficient', 99, 100, 80),
    system('cpu-efficient', 99.5, 100, 20),
    system('slow', 90, 1, 0),
  ]);
  const records = collectWinners(input).boards[0].records;
  assert.deepEqual(
    records.map((r) => r.frontend),
    ['cpu-efficient', 'efficient', 'fast', 'slow'],
  );
  assert.equal(records[0].score, 99.5);
  assert.equal(records[0].memoryMib, 100);
  assert.equal(records[0].cpuPercent, 20);
  assert.equal(collectWinners(input, 0).boards[0].records[0].frontend, 'fast');
});

test('resource ranking also chooses the efficient configuration of a single frontend', () => {
  const records = collectWinners(
    observations([
      system('fast-host', 60, 500, 1, 'alpha'),
      system('efficient-host', 59, 100, 20, 'alpha'),
      system('other-host', 60, 200, 10, 'beta'),
    ]),
  ).boards[0].records;
  assert.equal(records[0].frontend, 'alpha');
  assert.equal(records[0].groups[0].representative.campaign.host.id, 'efficient-host');
  assert.equal(records[0].score, 59);
});

test('fastest-anchored bands avoid chained closeness and remain input-order independent', () => {
  const input = observations([
    system('a', 100, 500, 10),
    system('b', 98, 300, 10),
    system('c', 96, 100, 10),
  ]);
  const expected = [
    ['b', 0, 1],
    ['a', 0, 2],
    ['c', 1, 3],
  ];
  for (const permutation of [input, [...input].reverse(), [input[1], input[2], input[0]]]) {
    assert.deepEqual(
      collectWinners(permutation).boards[0].records.map((r) => [r.frontend, r.rateBand, r.rank]),
      expected,
    );
  }
  const boundary = collectWinners(
    observations([system('a', 100, 500, 1), system('b', 97.99, 1, 0)]),
  ).boards[0];
  assert.equal(boundary.records[0].frontend, 'a');
});

test('global throughput bands are formed before choosing a frontend configuration', () => {
  const records = collectWinners(
    observations([
      system('a-fast', 100, 400, 10, 'alpha'),
      system('a-slow', 98, 50, 1, 'alpha'),
      system('b', 102, 300, 20, 'beta'),
    ]),
  ).boards[0].records;
  assert.equal(records[0].frontend, 'beta');
  assert.equal(records[1].groups[0].representative.campaign.host.id, 'a-fast');
});

test('resource medians retain equal campaign weights and ignore failed repetitions', () => {
  const a = withResources(campaign('a', 'alpha', 'same', Array(100).fill(60)), [100], [80]);
  const b = withResources(
    campaign('b', 'alpha', 'same', [60, 60, 60, null]),
    [300, 300, 300, 0],
    [20, 20, 20, 0],
  );
  const record = collectWinners(observations([a, b])).boards[0].records[0];
  assert.equal(record.memoryMib, 200);
  assert.equal(record.cpuPercent, 50);
  assert.equal(record.groups[0].attempted, 104);
  assert.equal(record.groups[0].successful, 103);
  b.runs[0].metrics.rss_peak_mib = null;
  const partial = collectWinners(observations([a, b])).boards[0].records[0];
  assert.equal(partial.memoryMib, null);
  assert.equal(partial.cpuPercent, null);
  assert.equal(partial.groups[0].resources.cpuPercent, 50);
});

test('missing resource coverage is not zero and CPU cannot bypass unknown memory', () => {
  const records = collectWinners(
    observations([
      system('unknown', 60, null, 0),
      system('known', 60, 100, 50),
      system('zero', 60, 0, 0),
      system('missing-cpu', 60, 100, null),
    ]),
  ).boards[0].records;
  assert.deepEqual(
    records.map((r) => r.frontend),
    ['zero', 'known', 'missing-cpu', 'unknown'],
  );
  const unknowns = collectWinners(
    observations([system('a', 60, null, 20), system('b', 59, null, 0)]),
  ).boards[0].records;
  assert.deepEqual(
    unknowns.map((r) => r.rank),
    [1, 1],
  );
  assert.ok(unknowns.every((r) => r.cpuPercent === null));
  const incomplete = withResources(campaign('p', 'partial', 'p', [60, 60]), [100], [10, null]);
  assert.equal(collectWinners(observations([incomplete])).boards[0].records[0].cpuPercent, null);
});

test('resources tie at displayed precision and close-rate ties show their rate range', () => {
  const records = collectWinners(
    observations([
      system('a', 60, 100.03, 20.02, 'alpha'),
      system('b', 59, 100.04, 20.04, 'alpha'),
      system('c', 59.5, 100, 20, 'beta'),
    ]),
  ).boards[0].records;
  assert.deepEqual(
    records.map((r) => r.rank),
    [1, 1],
  );
  assert.equal(records[0].score, 60);
  assert.equal(records[0].minimumScore, 59);
  assert.equal(records[0].groups.length, 2);
});

test('close-rate thresholds are explicit and invalid URL choices use the default', () => {
  assert.equal(closeRatePercent(null), 2);
  assert.equal(closeRatePercent('0'), 0);
  assert.equal(closeRatePercent('1'), 1);
  assert.equal(closeRatePercent('5'), 5);
  for (const value of ['', '-1', 'NaN', '100', '2.0']) assert.equal(closeRatePercent(value), 2);
  assert.throws(() => collectWinners([], 3), /threshold/);
});

test('case identity separates sources, timings, workloads and collection types', () => {
  const base = observations([campaign('a', 'alpha', 'host-a', [10])])[0];
  assert.equal(base.run.scenario, 'waveform');
  const mutations = [
    (o: typeof base) => (o.run.backend = 'python' as const),
    (o: typeof base) => (o.run.mode = base.run.mode === 'stream' ? 'replay' : 'stream'),
    (o: typeof base) => o.run.config.seed++,
    (o: typeof base) => o.run.config.hz++,
    (o: typeof base) => o.run.config.points++,
    (o: typeof base) => o.run.config.width++,
    (o: typeof base) => o.run.config.curves++,
    (o: typeof base) => o.run.config.image_plots++,
    (o: typeof base) => o.run.measurement_seconds++,
    (o: typeof base) => o.run.warmup_seconds++,
    (o: typeof base) => (o.campaign.classification = 'smoke' as const),
    (o: typeof base) => (o.campaign.classification = 'diagnostic' as const),
  ];
  for (const mutate of mutations) {
    const other = structuredClone(base);
    other.campaign.id = 'b';
    mutate(other);
    assert.notEqual(winnerKey(base), winnerKey(other));
    assert.equal(collectWinners([base, other]).boards.length, 2);
  }
});

test('source revisions and dirty trees share a board but never merge into one group', () => {
  const a = campaign('a', 'alpha', 'host-a', [60, 60, 60]),
    b = campaign('b', 'alpha', 'host-a', [60, 60, 60]);
  for (const r of b.runs) {
    r.context.commit = 'e'.repeat(40);
    r.context.source_hash = 'f'.repeat(64);
  }
  assert.equal(winnerKey(observations([a])[0]), winnerKey(observations([b])[0]));
  assert.equal(groupObservations(observations([a, b])).length, 2);
  const { boards } = collectWinners(observations([a, b]));
  assert.equal(boards.length, 1);
  assert.equal(boards[0].evaluatedGroups, 2);
  assert.equal(boards[0].revisions, 2);
  assert.equal(boards[0].records.length, 1);
  assert.equal(boards[0].records[0].groups.length, 2);
  const dirty = campaign('dirty', 'alpha', 'host-a', [60, 60, 60]);
  for (const r of dirty.runs) r.context.dirty = true;
  const withDirty = collectWinners(observations([a, b, dirty]));
  assert.equal(withDirty.boards.length, 1);
  assert.equal(withDirty.boards[0].evaluatedGroups, 3);
  assert.equal(withDirty.boards[0].revisions, 2);
});

// One run per section (and per repetition) so a campaign can populate every board.
function sectioned(id: string, frontend: string, host: string, rate: number): Submission {
  const c = campaign(id, frontend, host, []);
  c.runs = SECTIONS.flatMap((section) =>
    Array.from({ length: BASELINE.repetitions }, (_, i) => {
      const r = structuredClone(parseSubmission(seed).runs[0]);
      r.id = `${section.slug}-${i + 1}`;
      r.scenario = section.slug;
      r.frontend = frontend;
      r.repetition = i + 1;
      r.config = structuredClone(section.config);
      r.metrics.submitted_hz = rate;
      return r;
    }),
  );
  c.planned_runs = c.runs.length;
  return c;
}

test('boards follow the suite order and carry their section', () => {
  const { boards } = collectWinners(
    observations([sectioned('a', 'alpha', 'host-a', 60), sectioned('b', 'beta', 'host-b', 50)]),
  );
  assert.equal(boards.length, SECTIONS.length);
  boards.forEach((board, i) => {
    assert.equal(board.section?.slug, SECTIONS[i].slug);
    assert.equal(board.section?.index, i + 1);
    assert.deepEqual(
      board.records.map((r) => [r.frontend, r.rank]),
      [
        ['alpha', 1],
        ['beta', 2],
      ],
    );
  });
  const reversed = collectWinners(
    observations([sectioned('b', 'beta', 'host-b', 50), sectioned('a', 'alpha', 'host-a', 60)]),
  );
  assert.deepEqual(
    reversed.boards.map((b) => b.section?.slug),
    SECTIONS.map((s) => s.slug),
  );
});

test('an unknown display scale is excluded; different scales compete as separate groups', () => {
  const unknown = campaign('unknown-scale', 'alpha', 'host-a', [60]);
  unknown.runs[0].context.pixel_ratio = null;
  const known = campaign('known', 'beta', 'host-b', [50]);
  const excluded = collectWinners(observations([unknown, known]));
  assert.equal(excluded.excludedGroups, 1);
  assert.deepEqual(
    excluded.boards[0].records.map((r) => r.frontend),
    ['beta'],
  );
  const one = campaign('1x', 'alpha', 'host-a', [60, 60, 60]),
    two = campaign('2x', 'alpha', 'host-a', [60, 60, 60]);
  for (const r of one.runs) r.context.pixel_ratio = 1;
  for (const r of two.runs) r.context.pixel_ratio = 2;
  const scales = collectWinners(observations([one, two]));
  assert.equal(scales.excludedGroups, 0);
  assert.equal(scales.boards.length, 1);
  assert.equal(scales.boards[0].evaluatedGroups, 2);
  assert.equal(scales.boards[0].records.length, 1);
  assert.deepEqual(
    scales.boards[0].records[0].groups.map((g) => g.representative.run.context.pixel_ratio).sort(),
    [1, 2],
  );
});

test('a workload outside the suite forms a fallback board without a section, sorted last', () => {
  const custom = campaign('custom', 'alpha', 'host-a', [60, 60, 60]);
  for (const r of custom.runs) r.config.points = 20000;
  const { boards } = collectWinners(observations([custom, sectioned('a', 'alpha', 'host-a', 60)]));
  assert.equal(boards.length, SECTIONS.length + 1);
  assert.equal(boards[SECTIONS.length].section, null);
  assert.match(boards[SECTIONS.length].key, /20000/);
  assert.equal(boards[SECTIONS.length].records[0].frontend, 'alpha');
  assert.deepEqual(
    boards.slice(0, SECTIONS.length).map((b) => b.section?.slug),
    SECTIONS.map((s) => s.slug),
  );
});

test('hardware and rendering contexts remain separate observations within one record case', () => {
  const a = campaign('a', 'alpha', 'host-a', [10]),
    b = campaign('b', 'beta', 'host-b', [20]);
  b.host.os = 'other-os';
  b.host.cpu = 'other-cpu';
  b.runs[0].context.fingerprint = 'd'.repeat(64);
  b.runs[0].context.versions.renderer = '2';
  b.runs[0].context.pixel_ratio = 3;
  const { boards } = collectWinners(observations([a, b]));
  assert.equal(boards.length, 1);
  assert.equal(boards[0].records[0].groups[0].representative.campaign.host.os, 'other-os');
});

test('failed-only and incomplete groups are excluded; valid zero and source flags survive', () => {
  const failed = campaign('failed', 'alpha', 'host-a', [null]);
  const unknown = campaign('unknown', 'beta', 'host-b', [999]);
  unknown.runs[0].context.source_hash = null;
  const zero = campaign('zero', 'gamma', 'host-c', [0, null]);
  zero.runs[1].metrics.source_deadline_misses = 1;
  const result = collectWinners(observations([failed, unknown, zero]));
  assert.equal(result.excludedGroups, 2);
  assert.equal(result.boards.length, 1);
  assert.equal(result.boards[0].records[0].score, 0);
  const g = result.boards[0].records[0].groups[0];
  assert.equal(g.attempted, 2);
  assert.equal(g.successful, 1);
  assert.equal(g.sourceLimited, 1);
  assert.equal(g.frontendLimited, 0);
  assert.deepEqual(collectWinners([]), { boards: [], excludedGroups: 0, excludedBySection: {} });
});

test('exclusions are counted per section as well as in total', () => {
  const unknownScale = campaign('scale', 'alpha', 'host-a', [60, 60, 60]);
  for (const r of unknownScale.runs) r.context.pixel_ratio = null;
  const { boards, excludedGroups, excludedBySection } = collectWinners(
    observations([unknownScale, campaign('fine', 'beta', 'host-b', [50, 50, 50])]),
  );
  assert.equal(boards.length, 1);
  assert.equal(excludedGroups, 1);
  assert.deepEqual(excludedBySection, { waveform: 1 });
});
