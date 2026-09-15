import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import fixture from './fixtures/baseline-campaign.json';
import {
  BASELINE,
  BASELINE_VERSION,
  SECTIONS,
  SECTION_TITLES,
  baselineProblems,
  parseBaselineSuite,
  sectionBySlug,
  sectionOf,
} from '../src/baseline';
import { classify, workloadKey, type Submission } from '../src/model';
import { parseSubmission } from '../src/validation';

const sample = (): Submission => parseSubmission(structuredClone(fixture));
const SLUGS = [
  'waveform',
  'multi-curve',
  'multi-plot',
  'scalar-image',
  'rgb-image',
  'multi-image',
  'large-image',
];
const suiteFile = () =>
  JSON.parse(
    readFileSync(fileURLToPath(new URL('../../scenarios/baseline.json', import.meta.url)), 'utf8'),
  );

test('the suite defines seven distinct, fully specified sections in a fixed order', () => {
  assert.equal(BASELINE_VERSION, 1);
  assert.equal(SECTIONS.length, 7);
  assert.deepEqual(
    SECTIONS.map((s) => s.slug),
    SLUGS,
  );
  assert.deepEqual(
    SECTIONS.map((s) => s.index),
    [1, 2, 3, 4, 5, 6, 7],
  );
  for (const s of SECTIONS) assert.equal(Object.keys(s.config).length, 12, s.slug);
  assert.equal(new Set(SECTIONS.map((s) => s.key)).size, 7);
  assert.deepEqual(new Set(Object.keys(SECTION_TITLES)), new Set(SLUGS));
  for (const s of SECTIONS) assert.equal(s.title, SECTION_TITLES[s.slug]);
});

test('sections are found by exact workload identity or by slug, never by name alone', () => {
  const runs = sample().runs;
  for (const r of runs) assert.equal(sectionOf(r.config)?.slug, r.scenario, r.id);
  assert.equal(sectionOf({ ...runs[0].config, seed: 43 }), null);
  assert.equal(sectionBySlug('nope'), null);
  assert.equal(sectionBySlug(null), null);
  assert.equal(sectionBySlug('rgb-image')?.index, 5);
});

test('parseBaselineSuite refuses suites that are not the single stream/rust baseline', () => {
  const base = suiteFile();
  assert.deepEqual(parseBaselineSuite(base).sections, BASELINE.sections);
  for (const [pattern, mutate] of [
    [/streams only/, (s: any) => (s.modes = ['stream', 'replay'])],
    [/Rust source only/, (s: any) => (s.backends = ['python'])],
    [/exactly the fields/, (s: any) => (s.cases[0].config.generation = 0)],
    [/exactly the fields/, (s: any) => delete s.cases[0].config.image_plots],
    [/duplicate workload/, (s: any) => (s.cases[1].config = { ...s.cases[0].config })],
    [/duplicate case/, (s: any) => (s.cases[1].name = s.cases[0].name)],
    [/at least 3/, (s: any) => (s.repetitions = 1)],
    [/no title/, (s: any) => (s.cases[0].name = 'untitled')],
    [/explicit cases only/, (s: any) => (s.case_groups = [])],
    [/at least 10 s/, (s: any) => (s.measurement_seconds = 5)],
  ] as const) {
    const s = structuredClone(base);
    mutate(s);
    assert.throws(() => parseBaselineSuite(s), pattern);
  }
});

test('the fixture is a complete benchmark-classified baseline campaign', () => {
  assert.equal(classify(sample().runs), 'benchmark');
  assert.deepEqual(baselineProblems(sample()), []);
  assert.equal(sample().runs.length, 42);
});

test('the structural rule is count-based and names the first deviation', () => {
  const c = sample();
  const lastOfWaveform = c.runs.findIndex((r) => r.scenario === 'waveform' && r.repetition === 3);
  c.runs.splice(lastOfWaveform, 1);
  assert.match(baselineProblems(c)[0], /pyqtgraph: section "waveform" has repetitions \[1, 2\]/);
  const duplicated = sample();
  duplicated.runs[2].repetition = 2;
  assert.match(baselineProblems(duplicated)[0], /repetitions \[1, 2, 2\]/);
  const extra = sample();
  extra.planned_runs = 63;
  assert.deepEqual(baselineProblems(extra), [
    'planned_runs 63 differs from 42 (7 sections x 3 repetitions x 2 frontends)',
    '42 recorded runs of 63 planned; an official campaign must be complete',
  ]);
});

test('the suite file on disk matches the parsed sections and timings (guards drift with core)', () => {
  const suite = suiteFile();
  assert.equal(suite.name, BASELINE.name);
  assert.deepEqual(
    suite.cases.map((c: { name: string }) => c.name),
    SECTIONS.map((s) => s.slug),
  );
  assert.deepEqual(
    suite.cases.map((c: { config: any }) => workloadKey(c.config)),
    SECTIONS.map((s) => s.key),
  );
  assert.deepEqual(
    [
      suite.warmup_seconds,
      suite.measurement_seconds,
      suite.cooldown_seconds,
      suite.repetitions,
      suite.backends,
      suite.modes,
      suite.frontends,
    ],
    [
      BASELINE.warmupSeconds,
      BASELINE.measurementSeconds,
      BASELINE.cooldownSeconds,
      BASELINE.repetitions,
      [BASELINE.backend],
      [BASELINE.mode],
      BASELINE.frontends,
    ],
  );
  assert.deepEqual([BASELINE.warmupSeconds, BASELINE.measurementSeconds], [5, 30]);
});
