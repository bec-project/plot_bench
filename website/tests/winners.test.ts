import assert from 'node:assert/strict';
import test from 'node:test';
import seed from '../results/apple-m1-max-20260914-quick.json';
import { parseSubmission } from '../src/validation';
import { observations, type Submission } from '../src/model';
import { collectWinners, winnerKey } from '../src/winners';

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

test('display-precision ties retain all frontend and host records with shared ranks', () => {
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

test('case identity separates sources, timings, workloads and collection types', () => {
  const base = observations([campaign('a', 'alpha', 'host-a', [10])])[0];
  const mutations = [
    (o: typeof base) => (o.run.backend = 'python' as const),
    (o: typeof base) => (o.run.mode = base.run.mode === 'stream' ? 'replay' : 'stream'),
    (o: typeof base) => o.run.config.seed++,
    (o: typeof base) => o.run.config.hz++,
    (o: typeof base) => o.run.config.points++,
    (o: typeof base) => o.run.config.width++,
    (o: typeof base) => o.run.measurement_seconds++,
    (o: typeof base) => o.run.warmup_seconds++,
    (o: typeof base) => (o.run.context.source_hash = 'f'.repeat(64)),
    (o: typeof base) => (o.run.context.commit = 'e'.repeat(40)),
    (o: typeof base) => (o.run.context.dirty = true),
    (o: typeof base) => (o.campaign.classification = 'benchmark' as const),
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
  assert.equal(g.limited, 1);
  assert.deepEqual(collectWinners([]), { boards: [], excludedGroups: 0 });
});
