// The official baseline suite as the website sees it. The only definition lives in
// scenarios/baseline.json; this module parses that file at build time, derives the
// seven sections from it and states the structural rule a published campaign must meet.
import raw from '../../scenarios/baseline.json';
import { workloadKey, type Workload } from './model';

export const BASELINE_VERSION = 1;
export const BASELINE_SUITE_PATH = 'scenarios/baseline.json';

export interface Section {
  /** 1-based position in the suite file, used for ordering and numbering. */
  index: number;
  /** Case name in the suite file, URL slug and every published run's `scenario`. */
  slug: string;
  title: string;
  /** `workloadKey(config)`; the identity a run's config must match exactly. */
  key: string;
  config: Workload;
}
export interface Baseline {
  name: string;
  sections: Section[];
  frontends: string[];
  backend: 'rust';
  mode: 'stream';
  warmupSeconds: number;
  measurementSeconds: number;
  cooldownSeconds: number;
  repetitions: number;
}

// Presentation copy only; the identity of a section is its slug and config.
export const SECTION_TITLES: Record<string, string> = {
  waveform: 'Waveform',
  'multi-curve': 'Multi-curve waveform',
  'multi-plot': 'Multi-plot waveform',
  'scalar-image': 'Scalar image',
  'rgb-image': 'RGB image',
  'multi-image': 'Multiple scalar images',
  'large-image': 'Large scalar image',
};

const WORKLOAD_KEYS = [
  'hz',
  'points',
  'append_count',
  'width',
  'height',
  'waveform_mode',
  'image_mode',
  'view',
  'seed',
  'waveform_plots',
  'curves',
  'image_plots',
] as const;
const SLUG = /^[a-z0-9][a-z0-9-]*$/;

function record(value: unknown, path: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error(`${path}: must be an object`);
  return value as Record<string, unknown>;
}
function positiveInteger(value: unknown, path: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 1)
    throw new Error(`${path}: must be a positive integer`);
  return value;
}
function oneOf<T extends string>(value: unknown, allowed: readonly T[], path: string): T {
  if (typeof value !== 'string' || !allowed.includes(value as T))
    throw new Error(`${path}: must be one of ${allowed.join(', ')}`);
  return value as T;
}
function stringList(value: unknown, path: string): string[] {
  if (!Array.isArray(value) || !value.length || !value.every((v) => typeof v === 'string'))
    throw new Error(`${path}: must be a non-empty list of strings`);
  if (new Set(value).size !== value.length) throw new Error(`${path}: entries must be unique`);
  return value as string[];
}

/** Every published workload field must be explicit so no default is re-implemented here. */
export function parseWorkload(value: unknown, path: string): Workload {
  const c = record(value, path);
  const keys = Object.keys(c).sort();
  if (keys.join(',') !== [...WORKLOAD_KEYS].sort().join(','))
    throw new Error(`${path}: config must list exactly the fields ${WORKLOAD_KEYS.join(', ')}`);
  const hz = c.hz;
  if (typeof hz !== 'number' || !Number.isFinite(hz) || hz <= 0 || hz > 120)
    throw new Error(`${path}.hz: must be a number between 0 and 120`);
  const config: Workload = {
    hz,
    points: positiveInteger(c.points, `${path}.points`),
    append_count: positiveInteger(c.append_count, `${path}.append_count`),
    width: positiveInteger(c.width, `${path}.width`),
    height: positiveInteger(c.height, `${path}.height`),
    waveform_mode: oneOf(c.waveform_mode, ['replace', 'append'], `${path}.waveform_mode`),
    image_mode: oneOf(c.image_mode, ['scalar', 'rgb'], `${path}.image_mode`),
    view: oneOf(c.view, ['waveform', 'image', 'both'], `${path}.view`),
    seed: positiveInteger(c.seed, `${path}.seed`),
    waveform_plots: positiveInteger(c.waveform_plots, `${path}.waveform_plots`),
    curves: positiveInteger(c.curves, `${path}.curves`),
    image_plots: positiveInteger(c.image_plots, `${path}.image_plots`),
  };
  if (config.append_count > config.points)
    throw new Error(`${path}: append_count must not exceed points`);
  return config;
}

export function parseBaselineSuite(value: unknown): Baseline {
  const suite = record(value, 'suite');
  if (typeof suite.name !== 'string' || !suite.name.trim())
    throw new Error('suite.name: must be a non-empty string');
  if (!Array.isArray(suite.cases) || !suite.cases.length)
    throw new Error('suite.cases: must be a non-empty list of explicit cases');
  if ('case_groups' in suite)
    throw new Error('suite.case_groups: the baseline must use explicit cases only');
  const modes = stringList(suite.modes, 'suite.modes'),
    backends = stringList(suite.backends, 'suite.backends');
  if (modes.length !== 1 || modes[0] !== 'stream')
    throw new Error('suite.modes: the baseline streams only');
  if (backends.length !== 1 || backends[0] !== 'rust')
    throw new Error('suite.backends: the baseline uses the Rust source only');
  const seconds = (key: string) => {
    const v = suite[key];
    if (typeof v !== 'number' || !Number.isFinite(v) || v < 0)
      throw new Error(`suite.${key}: must be a non-negative number`);
    return v;
  };
  const warmupSeconds = seconds('warmup_seconds'),
    measurementSeconds = seconds('measurement_seconds'),
    cooldownSeconds = seconds('cooldown_seconds');
  if (measurementSeconds < 10)
    throw new Error('suite.measurement_seconds: benchmark campaigns measure at least 10 s');
  const repetitions = positiveInteger(suite.repetitions, 'suite.repetitions');
  if (repetitions < 3) throw new Error('suite.repetitions: benchmark campaigns need at least 3');
  const sections: Section[] = [];
  const slugs = new Set<string>(),
    keys = new Set<string>();
  suite.cases.forEach((entry, i) => {
    const c = record(entry, `suite.cases[${i}]`);
    if (typeof c.name !== 'string' || !SLUG.test(c.name))
      throw new Error(`suite.cases[${i}].name: must match ${SLUG}`);
    if (slugs.has(c.name)) throw new Error(`suite.cases[${i}].name: duplicate case ${c.name}`);
    const config = parseWorkload(c.config, `suite.cases[${i}].config`);
    const key = workloadKey(config);
    if (keys.has(key)) throw new Error(`suite.cases[${i}]: duplicate workload`);
    const title = SECTION_TITLES[c.name];
    if (!title) throw new Error(`suite.cases[${i}]: no title for section ${c.name}`);
    slugs.add(c.name);
    keys.add(key);
    sections.push({ index: i + 1, slug: c.name, title, key, config });
  });
  return {
    name: suite.name,
    sections,
    frontends: stringList(suite.frontends, 'suite.frontends'),
    backend: 'rust',
    mode: 'stream',
    warmupSeconds,
    measurementSeconds,
    cooldownSeconds,
    repetitions,
  };
}

// Parsing at import time makes a malformed suite fail the build, the tests and CI at once.
export const BASELINE: Baseline = parseBaselineSuite(raw);
export const SECTIONS: readonly Section[] = BASELINE.sections;
const byKey = new Map(SECTIONS.map((s) => [s.key, s]));
const bySlug = new Map(SECTIONS.map((s) => [s.slug, s]));

export function sectionOf(config: Workload): Section | null {
  return byKey.get(workloadKey(config)) ?? null;
}
export function sectionBySlug(slug: string | null | undefined): Section | null {
  return slug ? (bySlug.get(slug) ?? null) : null;
}
/** The conditions every section shares, for headings and the suite page. */
export function fixedConditions(): string {
  const hz = new Set(SECTIONS.map((s) => s.config.hz)),
    seed = new Set(SECTIONS.map((s) => s.config.seed));
  return [
    'Rust source',
    'streaming delivery',
    [...hz].map((v) => `${v} Hz`).join('/'),
    `seed ${[...seed].join('/')}`,
    `${BASELINE.warmupSeconds} s warmup + ${BASELINE.measurementSeconds} s measurement`,
    `${BASELINE.repetitions} repetitions`,
  ].join(' · ');
}

/** The subset of a run the structural rule needs; served by both a parsed Submission and raw summary.json rows. */
export interface BaselineRun {
  id: string;
  scenario: string;
  frontend: string;
  backend: string;
  mode: string;
  repetition: number;
  measurement_seconds: number;
  warmup_seconds: number;
  config: Workload;
  /** Runner status; "interrupted" and "provenance-changed" windows are truncated, not failed. */
  status?: string;
  commit?: string | null;
  source_hash?: string | null;
}
export interface BaselineCandidate {
  planned_runs: number;
  /** The runner's campaign completion status; only "completed" campaigns are published. */
  completion_status?: string;
  runs: readonly BaselineRun[];
}

/**
 * Why a campaign is not a complete run of the official baseline. An empty list means it is.
 * The rule is structural and count-based: per-run identity and timings, every section present,
 * exactly repetitions 1..N for every frontend in every section, and a planned/recorded run count
 * that equals sections x repetitions x frontends, from one completed acquisition at one source
 * revision. Failed runs count as present so failures stay published; interrupted or
 * provenance-changed runs are truncated windows and are not. Any subset of the suite's
 * frontends is allowed.
 */
export function baselineProblems(candidate: BaselineCandidate): string[] {
  const problems: string[] = [];
  const expected = Array.from({ length: BASELINE.repetitions }, (_, i) => i + 1);
  const coverage = new Map<string, Map<string, number[]>>();
  const frontends = new Set<string>();
  const commits = new Set<string>(),
    sources = new Set<string>();
  if (candidate.completion_status !== undefined && candidate.completion_status !== 'completed')
    problems.push(
      `completion status "${candidate.completion_status}"; an official campaign must run to completion`,
    );
  for (const r of candidate.runs) {
    if (r.status === 'interrupted' || r.status === 'provenance-changed')
      problems.push(
        `${r.id}: run was ${r.status}; a truncated or invalidated window cannot be published`,
      );
    if (r.commit) commits.add(r.commit);
    if (r.source_hash) sources.add(r.source_hash);
    const section = sectionOf(r.config);
    if (!section) {
      problems.push(
        `${r.id}: workload (${r.config.view}, ${r.config.hz} Hz, ${r.config.points} points, ` +
          `${r.config.waveform_plots} x ${r.config.curves} curves, ${r.config.width} x ${r.config.height} ${r.config.image_mode}, ` +
          `${r.config.image_plots} image plots, seed ${r.config.seed}) is not a baseline section`,
      );
      continue;
    }
    if (r.scenario !== section.slug)
      problems.push(`${r.id}: scenario "${r.scenario}" must be the section name "${section.slug}"`);
    if (r.backend !== BASELINE.backend)
      problems.push(`${r.id}: source backend ${r.backend}; the baseline uses ${BASELINE.backend}`);
    if (r.mode !== BASELINE.mode)
      problems.push(`${r.id}: delivery mode ${r.mode}; the baseline uses ${BASELINE.mode}`);
    if (r.measurement_seconds !== BASELINE.measurementSeconds)
      problems.push(
        `${r.id}: measured ${r.measurement_seconds} s; the baseline measures ${BASELINE.measurementSeconds} s`,
      );
    if (r.warmup_seconds !== BASELINE.warmupSeconds)
      problems.push(
        `${r.id}: warmup ${r.warmup_seconds} s; the baseline warms up ${BASELINE.warmupSeconds} s`,
      );
    if (!BASELINE.frontends.includes(r.frontend))
      problems.push(`${r.id}: frontend ${r.frontend} is not part of the baseline suite`);
    frontends.add(r.frontend);
    const sections = coverage.get(r.frontend) ?? new Map<string, number[]>();
    const reps = sections.get(section.slug) ?? [];
    reps.push(r.repetition);
    sections.set(section.slug, reps);
    coverage.set(r.frontend, sections);
  }
  for (const section of SECTIONS)
    if (![...coverage.values()].some((sections) => sections.has(section.slug)))
      problems.push(
        `section "${section.slug}" has no runs; all ${SECTIONS.length} sections are required`,
      );
  for (const [frontend, sections] of [...coverage].sort(([a], [b]) => a.localeCompare(b)))
    for (const section of SECTIONS) {
      const reps = [...(sections.get(section.slug) ?? [])].sort((a, b) => a - b);
      if (reps.join(',') !== expected.join(','))
        problems.push(
          `${frontend}: section "${section.slug}" has repetitions [${reps.join(', ')}] instead of 1..${BASELINE.repetitions}`,
        );
    }
  if (commits.size > 1)
    problems.push(
      `runs span ${commits.size} source commits (${[...commits].map((c) => c.slice(0, 7)).join(', ')}); an official campaign is one acquisition at one revision`,
    );
  if (sources.size > 1)
    problems.push(
      `runs span ${sources.size} source hashes; an official campaign is one acquisition at one revision`,
    );
  const planned = SECTIONS.length * BASELINE.repetitions * frontends.size;
  if (candidate.planned_runs !== planned)
    problems.push(
      `planned_runs ${candidate.planned_runs} differs from ${planned} (${SECTIONS.length} sections x ${BASELINE.repetitions} repetitions x ${frontends.size} frontends)`,
    );
  if (candidate.runs.length !== candidate.planned_runs)
    problems.push(
      `${candidate.runs.length} recorded runs of ${candidate.planned_runs} planned; an official campaign must be complete`,
    );
  return problems;
}
