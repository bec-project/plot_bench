import assert from 'node:assert/strict';
import test from 'node:test';
import seed from './fixtures/baseline-campaign.json';
import { parseSubmission } from '../src/validation';
import { observations, type Submission, type Observation } from '../src/model';
import {
  groupObservations,
  summarizeRates,
  compatibilityKey,
  inDateRange,
} from '../src/aggregation';

function campaign(id: string, rates: (number | null)[], day = '14'): Submission {
  const c = structuredClone(parseSubmission(seed));
  c.id = id;
  c.recorded_at = `2026-09-${day}T12:00:00Z`;
  c.planned_runs = rates.length;
  c.runs = rates.map((rate, index) => {
    const r = structuredClone(c.runs[0]);
    r.id = `run-${index + 1}`;
    r.repetition = index + 1;
    r.metrics.submitted_hz = rate;
    r.status = rate === null ? 'failed' : 'ok';
    r.samples = rate === null ? 0 : 100;
    return r;
  });
  return c;
}

test('two-level medians give campaigns equal weight regardless of repetition count', () => {
  const many = campaign('many', Array(100).fill(60));
  const few = campaign('few', [20, 30, 40], '15');
  const failed = campaign('failed', [null, null], '16');
  const input = observations([many, few, failed]),
    before = structuredClone(input);
  const [g] = groupObservations(input);
  assert.deepEqual(g.rates, { median: 45, q1: 37.5, q3: 52.5, min: 30, max: 60, count: 2 });
  assert.equal(g.campaigns.length, 3);
  assert.equal(g.attempted, 105);
  assert.equal(g.successful, 103);
  assert.equal(g.campaigns[0].rates.median, null);
  assert.equal(g.first, many.recorded_at);
  assert.equal(g.last, failed.recorded_at);
  assert.deepEqual(input, before);
});

test('failed runs never enter medians even when they contain a numeric rate; zero is valid', () => {
  const c = campaign('failed-numeric', [10, 20, 999, 0]);
  c.runs[2].status = 'failed';
  c.runs[2].metrics.source_deadline_misses = 1;
  const [g] = groupObservations(observations([c]));
  assert.equal(g.rates.median, 10);
  assert.equal(g.successful, 3);
  assert.equal(g.attempted, 4);
  assert.equal(g.limited, 1);
  assert.equal(g.campaigns[0].observations.length, 4);
  assert.equal(g.rates.q1, null);
  assert.equal(g.rates.q3, null);
  assert.equal(g.campaigns[0].rates.min, 0);
  assert.equal(g.campaigns[0].rates.max, 20);
});

test('empty, all-failed and singleton groups keep absence and spread explicit', () => {
  assert.deepEqual(groupObservations([]), []);
  assert.equal(summarizeRates([]).median, null);
  const [g] = groupObservations(observations([campaign('failure', [null])]));
  assert.equal(g.rates.count, 0);
  assert.equal(g.rates.median, null);
  assert.equal(g.attempted, 1);
  assert.equal(summarizeRates([0]).median, 0);
  assert.equal(summarizeRates([7]).q1, null);
  assert.deepEqual(summarizeRates([4, 1, 3, 2]), {
    median: 2.5,
    q1: 1.75,
    q3: 3.25,
    min: 1,
    max: 4,
    count: 4,
  });
});

test('every compatibility dimension separates groups, including explicit context fields', () => {
  const base = observations([campaign('a', [10])])[0];
  const mutations: ((o: Observation) => void)[] = [
    (o) => (o.campaign.host.id = 'other-host'),
    (o) => (o.campaign.host.cpu = 'Other CPU'),
    (o) => (o.campaign.host.gpu = 'Other GPU'),
    (o) => (o.campaign.host.memory_gib = 64),
    (o) => (o.campaign.host.os = 'Other OS'),
    (o) => (o.campaign.host.architecture = 'x64'),
    (o) => (o.campaign.classification = 'smoke'),
    (o) => (o.campaign.classification = 'diagnostic'),
    (o) => (o.run.frontend = 'other'),
    (o) => (o.run.backend = 'python'),
    (o) => (o.run.mode = base.run.mode === 'stream' ? 'replay' : 'stream'),
    (o) => o.run.warmup_seconds++,
    (o) => o.run.measurement_seconds++,
    (o) => (o.run.context.fingerprint = 'f'.repeat(64)),
    (o) => (o.run.context.source_hash = 'e'.repeat(64)),
    (o) => (o.run.context.commit = 'd'.repeat(40)),
    (o) => (o.run.context.dirty = !base.run.context.dirty),
    (o) => (o.run.context.versions.renderer = 'changed'),
    (o) => (o.run.context.renderer = 'changed'),
    (o) => (o.run.context.measurement_stage = 'changed'),
    (o) => (o.run.context.pixel_ratio = 3),
    (o) => (o.run.context.viewport_size = [123, 456]),
    (o) => (o.run.context.plot_viewports.image = [12, 34]),
    (o) => (o.run.context.display_protocol = 'wayland'),
    (o) => (o.run.context.refresh_hz = 144),
    (o) => (o.run.context.headless = true),
  ];
  for (const key of [
    'hz',
    'points',
    'append_count',
    'width',
    'height',
    'seed',
    'waveform_plots',
    'curves',
    'image_plots',
  ] as const)
    mutations.push((o) => o.run.config[key]++);
  for (const mutate of mutations) {
    const other = structuredClone(base);
    other.campaign.id = 'b';
    mutate(other);
    assert.equal(groupObservations([base, other]).length, 2, mutate.toString());
  }
  for (const key of ['view', 'image_mode', 'waveform_mode'] as const) {
    const other = structuredClone(base);
    const alternatives = { view: 'image', image_mode: 'rgb', waveform_mode: 'append' } as const;
    Object.assign(other.run.config, { [key]: alternatives[key] });
    assert.notEqual(compatibilityKey(base), compatibilityKey(other));
  }
});

test('renamed labels, scenario names, repetitions, dates and JSON key order do not split compatible runs', () => {
  const a = campaign('a', [10]),
    b = campaign('b', [20], '15');
  b.host.label = 'Renamed public label';
  b.runs[0].scenario = 'renamed';
  b.runs[0].repetition = 12;
  b.runs[0].context.versions = Object.fromEntries(
    Object.entries(b.runs[0].context.versions).reverse(),
  );
  const groups = groupObservations(observations([a, b]));
  assert.equal(groups.length, 1);
  assert.equal(groups[0].rates.median, 15);
  assert.equal(groups[0].representative.campaign.id, 'b');
});

test('incomplete provenance cannot silently merge unrelated observations', () => {
  const a = campaign('a', [10, 20]),
    b = campaign('b', [30]);
  for (const c of [a, b]) for (const r of c.runs) r.context.source_hash = null;
  const groups = groupObservations(observations([a, b]));
  assert.equal(groups.length, 3);
  assert.ok(groups.every((g) => g.incompleteContext));
});

test('inclusive UTC acquisition dates filter campaigns before aggregation', () => {
  assert.equal(inDateRange('2026-09-15T01:00:00+02:00', '2026-09-14', '2026-09-14'), true);
  assert.equal(inDateRange('2026-09-14T23:00:00-02:00', '2026-09-14', '2026-09-14'), false);
  assert.equal(inDateRange('2026-09-14T12:00:00Z', '2026-09-15', '2026-09-14'), false);
  const input = observations([campaign('a', [10]), campaign('b', [90], '15')]);
  const groups = groupObservations(
    input.filter((o) => inDateRange(o.campaign.recorded_at, '', '2026-09-14')),
  );
  assert.equal(groups[0].rates.median, 10);
  assert.equal(groups[0].campaigns.length, 1);
});
