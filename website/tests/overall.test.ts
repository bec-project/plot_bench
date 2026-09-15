import assert from 'node:assert/strict';
import test from 'node:test';
import fixture from './fixtures/baseline-campaign.json';
import { BASELINE, SECTIONS, type Section } from '../src/baseline';
import { observations, type Submission } from '../src/model';
import { parseSubmission } from '../src/validation';
import { collectWinners } from '../src/winners';
import { collectOverall } from '../src/overall';

const seed = parseSubmission(structuredClone(fixture));
interface Shape {
  /** Median rate per section; a null rate marks a failed run. */
  rate: number | ((section: Section) => number | null);
  memory?: number | null;
  cpu?: number | null;
  /** Sections to record; every listed section gets repetitions 1..3. */
  sections?: readonly string[];
  commit?: string;
  /** Section slugs whose first repetition is flagged as source-limited. */
  limited?: readonly string[];
}
// A campaign built from the suite itself: one run per section and repetition, all sharing
// the fixture's complete display context so every group is eligible for a board.
function campaign(id: string, frontend: string, host: string, shape: Shape): Submission {
  const c = structuredClone(seed);
  c.id = id;
  c.host.id = host;
  c.host.label = host;
  c.runs = SECTIONS.filter((s) =>
    (shape.sections ?? SECTIONS.map((x) => x.slug)).includes(s.slug),
  ).flatMap((section) =>
    Array.from({ length: BASELINE.repetitions }, (_, i) => {
      const r = structuredClone(seed.runs[0]);
      const rate = typeof shape.rate === 'number' ? shape.rate : shape.rate(section);
      r.id = `${section.slug}-${i + 1}`;
      r.scenario = section.slug;
      r.frontend = frontend;
      r.repetition = i + 1;
      r.config = structuredClone(section.config);
      r.metrics.submitted_hz = rate;
      r.metrics.rss_peak_mib = shape.memory === undefined ? 200 : shape.memory;
      r.metrics.cpu_mean_percent = shape.cpu === undefined ? 20 : shape.cpu;
      r.metrics.source_deadline_misses = i === 0 && shape.limited?.includes(section.slug) ? 1 : 0;
      r.status = rate === null ? 'failed' : 'ok';
      r.samples = rate === null ? 0 : 100;
      if (shape.commit) r.context.commit = shape.commit;
      return r;
    }),
  );
  c.planned_runs = c.runs.length;
  return c;
}
const ranks = (o: ReturnType<typeof collectOverall>) =>
  o.entries.map((e) => [e.frontend, e.rank, e.total, e.wins]);

test('the overall rank adds the displayed section ranks; lower totals win', () => {
  const first = (s: Section) => (s.index <= 5 ? 60 : 50),
    second = (s: Section) => (s.index <= 5 ? 50 : 60);
  const input = observations([
      campaign('a', 'alpha', 'host-a', { rate: first }),
      campaign('b', 'beta', 'host-b', { rate: second }),
      campaign('g', 'gamma', 'host-c', { rate: 40 }),
    ]),
    before = structuredClone(input);
  const overall = collectOverall(input);
  assert.deepEqual(ranks(overall), [
    ['alpha', 1, 9, 5],
    ['beta', 2, 12, 2],
    ['gamma', 3, 21, 0],
  ]);
  assert.equal(overall.boards.length, 7);
  assert.deepEqual(
    overall.boards.map((b) => b.section?.slug),
    SECTIONS.map((s) => s.slug),
  );
  assert.deepEqual(
    overall.entries[0].placements.map((p) => [p.section.slug, p.rank]),
    SECTIONS.map((s) => [s.slug, s.index <= 5 ? 1 : 2]),
  );
  assert.deepEqual(overall.entries[0].hosts, ['host-a']);
  assert.deepEqual(overall.incomplete, []);
  assert.equal(overall.closeRatePercent, 2);
  assert.deepEqual(input, before);
});

test('a frontend without every section is listed as incomplete and keeps its section placements', () => {
  const input = observations([
    campaign('a', 'alpha', 'host-a', { rate: 60 }),
    campaign('b', 'beta', 'host-b', { rate: 50 }),
    campaign('d', 'delta', 'host-d', {
      rate: (s) => (s.index === 1 ? 70 : 40),
      sections: SECTIONS.filter((s) => s.slug !== 'large-image').map((s) => s.slug),
    }),
  ]);
  const overall = collectOverall(input);
  assert.deepEqual(
    overall.incomplete.map((i) => [i.frontend, i.missing.map((s) => s.slug)]),
    [['delta', ['large-image']]],
  );
  assert.equal(overall.incomplete[0].present.length, 6);
  assert.deepEqual(
    overall.entries.map((e) => e.frontend),
    ['alpha', 'beta'],
  );
  // The section board still shows delta first; the overall sum uses that displayed rank.
  const board = collectWinners(input).boards[0];
  assert.equal(board.section?.slug, 'waveform');
  assert.deepEqual(
    board.records.map((r) => [r.frontend, r.rank]),
    [
      ['delta', 1],
      ['alpha', 2],
      ['beta', 3],
    ],
  );
  assert.equal(overall.entries[0].placements[0].rank, 2);
  assert.deepEqual(ranks(overall), [
    ['alpha', 1, 2 + 6, 6],
    ['beta', 2, 3 + 12, 0],
  ]);
});

test('paced sections are decided by memory, then CPU, inside the close-rate band', () => {
  const overall = collectOverall(
    observations([
      campaign('a', 'alpha', 'host-a', { rate: 60, memory: 300, cpu: 10 }),
      campaign('b', 'beta', 'host-b', { rate: 60, memory: 100, cpu: 50 }),
      campaign('g', 'gamma', 'host-c', { rate: 60, memory: 100, cpu: 30 }),
    ]),
  );
  assert.deepEqual(ranks(overall), [
    ['gamma', 1, 7, 7],
    ['beta', 2, 14, 0],
    ['alpha', 3, 21, 0],
  ]);
});

test('equal totals are ordered by section wins; equal totals and wins share a rank', () => {
  // alpha: 1,1,1,1,3,3,2 = 12 with 4 wins; beta: 2,2,2,2,1,1,2 = 12 with 2 wins.
  const alpha = (s: Section) => (s.index <= 4 ? 60 : s.index <= 6 ? 40 : 50),
    beta = (s: Section) => (s.index <= 4 ? 50 : s.index <= 6 ? 60 : 50),
    gamma = (s: Section) => (s.index <= 4 ? 40 : s.index <= 6 ? 50 : 60);
  const byWins = collectOverall(
    observations([
      campaign('a', 'alpha', 'host-a', { rate: alpha }),
      campaign('b', 'beta', 'host-b', { rate: beta }),
      campaign('g', 'gamma', 'host-c', { rate: gamma }),
    ]),
  );
  assert.deepEqual(ranks(byWins), [
    ['alpha', 1, 12, 4],
    ['beta', 2, 12, 2],
    ['gamma', 3, 17, 1],
  ]);
  const joint = collectOverall(
    observations([
      campaign('a', 'alpha', 'host-a', { rate: 60 }),
      campaign('b', 'beta', 'host-b', { rate: 60 }),
      campaign('g', 'gamma', 'host-c', { rate: 40 }),
    ]),
  );
  assert.deepEqual(ranks(joint), [
    ['alpha', 1, 7, 7],
    ['beta', 1, 7, 7],
    ['gamma', 3, 21, 0],
  ]);
});

test('empty input and a single entrant produce empty structures and rank 1', () => {
  assert.deepEqual(collectOverall([]), {
    entries: [],
    incomplete: [],
    boards: [],
    excludedGroups: 0,
    closeRatePercent: 2,
  });
  const single = collectOverall(observations([campaign('a', 'alpha', 'host-a', { rate: 60 })]));
  assert.deepEqual(ranks(single), [['alpha', 1, 7, 7]]);
  assert.equal(single.entries[0].placements.length, 7);
  assert.equal(single.entries[0].revisions, 1);
  assert.equal(single.entries[0].limitedGroups, 0);
});

test('source-limited groups are counted per entry without changing placements', () => {
  const overall = collectOverall(
    observations([
      campaign('a', 'alpha', 'host-a', { rate: 60, limited: ['multi-plot', 'rgb-image'] }),
      campaign('b', 'beta', 'host-b', { rate: 50 }),
    ]),
  );
  assert.deepEqual(
    overall.entries.map((e) => [e.frontend, e.rank, e.limitedGroups]),
    [
      ['alpha', 1, 2],
      ['beta', 2, 0],
    ],
  );
});

test('the close-rate tolerance passes through to the boards and unsupported values throw', () => {
  const input = observations([
    campaign('a', 'alpha', 'host-a', { rate: 60, memory: 300 }),
    campaign('b', 'beta', 'host-b', { rate: 59.5, memory: 100 }),
  ]);
  assert.deepEqual(
    ranks(collectOverall(input)).map((r) => r[0]),
    ['beta', 'alpha'],
  );
  assert.equal(collectOverall(input).closeRatePercent, 2);
  const strict = collectOverall(input, 0);
  assert.deepEqual(
    ranks(strict).map((r) => r[0]),
    ['alpha', 'beta'],
  );
  assert.equal(strict.closeRatePercent, 0);
  assert.equal(strict.boards[0].closeRatePercent, 0);
  assert.throws(() => collectOverall(input, 3), /threshold/);
});

test('two source revisions of one frontend share each section board and count as revisions', () => {
  const overall = collectOverall(
    observations([
      campaign('a1', 'alpha', 'host-a', { rate: 60, commit: 'a'.repeat(40) }),
      campaign('a2', 'alpha', 'host-a', { rate: 59.8, commit: 'b'.repeat(40) }),
      campaign('b', 'beta', 'host-b', { rate: 50, commit: 'a'.repeat(40) }),
    ]),
  );
  assert.deepEqual(ranks(overall), [
    ['alpha', 1, 7, 7],
    ['beta', 2, 14, 0],
  ]);
  assert.equal(overall.entries[0].revisions, 2);
  assert.equal(overall.entries[1].revisions, 1);
  assert.equal(overall.entries[0].placements.length, 7);
  assert.ok(overall.boards.every((b) => b.revisions === 2 && b.evaluatedGroups === 3));
  assert.ok(overall.entries[0].placements.every((p) => p.record.groups.length === 2));
});
