import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, writeFile, symlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import seed from './fixtures/quick-smoke.json';
import { classify, workloadKey, workloadLabel, type Submission } from '../src/model';
import { parseSubmission, parseSubmissionText, validateCatalog } from '../src/validation';
import { exportSummary, suggestSubmission } from '../src/export';
import { loadCatalog } from '../scripts/catalog';

const sample = (): Submission => parseSubmission(structuredClone(seed));
const options = { id: 'test-campaign', hostId: 'test-host', hostLabel: 'Test host' };

// Synthetic acquisition metadata exercises the exporter without requiring a
// contributor's private raw files or starting a benchmark.
function rawSummary() {
  const c = sample();
  return {
    campaign: {
      manifest_present: true,
      started_at: '2026-09-14T11:04:02+02:00 (2026-09-14T09:04:02+00:00)',
      suite_name: 'Test suite',
      completion_status: 'complete',
      runs_planned: c.runs.length,
      headless: false,
      hardware: {
        cpu_model: 'Test CPU',
        os: 'Test OS',
        architecture: 'test',
        memory_gib: 16,
        graphics: [{ model: 'Test GPU' }],
        hostname: 'PRIVATE_HOST',
      },
      provenance: { source_sha256: 'a'.repeat(64), git: { commit: 'b'.repeat(40), dirty: false } },
    },
    diagnostics: { manifest_present: false, error: null, entries: {} },
    report_provenance: { recorded_at: '2030-01-01T00:00:00Z', source_sha256: 'c'.repeat(64) },
    runs: c.runs.map((r) => ({
      run_id: r.id,
      scenario: r.scenario,
      frontend: r.frontend,
      backend: r.backend,
      mode: r.mode,
      repetition: r.repetition,
      status: r.status,
      config: r.config,
      measurement_seconds: r.measurement_seconds,
      warmup_seconds: r.warmup_seconds,
      samples: r.samples,
      ...r.metrics,
      metadata: {
        headless: false,
        qt_platform_plugin: 'cocoa',
        versions: { renderer: '1.0' },
        argv: ['PRIVATE_ARG'],
        environment: { TOKEN: 'PRIVATE_TOKEN' },
      },
      provenance: {
        source_sha256: 'a'.repeat(64),
        git: { commit: 'b'.repeat(40), dirty: false },
        recorded_at: '2026-09-14T09:04:03Z',
        artifacts: { renderer: { path: '/PRIVATE_PATH', files: { binary: 'd'.repeat(64) } } },
      },
      path: '/PRIVATE_PATH',
    })),
  };
}

test('real seed validates; workload identity ignores JSON property order', () => {
  assert.equal(parseSubmission(sample()).runs.length, 8);
  const c = sample().runs[0].config;
  assert.equal(
    workloadKey(c),
    workloadKey(Object.fromEntries(Object.entries(c).reverse()) as typeof c),
  );
});

test('schema rejects unknown/private fields, unsupported versions and invalid observations', () => {
  for (const mutate of [
    (c: any) => (c.host.hostname = 'private'),
    (c: any) => (c.schema_version = 2),
    (c: any) => (c.runs[0].metrics.submitted_hz = null),
    (c: any) => (c.runs[0].metrics.submitted_hz = NaN),
    (c: any) => (c.runs[0].samples = 0),
    (c: any) => (c.runs[0].config.append_count = c.runs[0].config.points + 1),
    (c: any) => (c.runs[1].id = c.runs[0].id),
    (c: any) => (c.planned_runs = 1),
    (c: any) => (c.classification = 'benchmark'),
    (c: any) => (c.runs[0].config.curves = 65),
    (c: any) => delete c.runs[0].config.image_plots,
  ]) {
    const c = sample();
    mutate(c);
    assert.throws(() => parseSubmission(c));
  }
  assert.throws(() => parseSubmissionText(' '.repeat(5 * 1024 * 1024 + 1)), /5 MiB/);
});

test('catalogue rejects duplicates but accepts an empty collection', () => {
  assert.deepEqual(validateCatalog([]), []);
  assert.throws(() => validateCatalog([sample(), sample()]), /Duplicate campaign ID/);
  const copy = sample();
  copy.id = 'another-name';
  assert.throws(() => validateCatalog([sample(), copy]), /already submitted/);
});

test('host histories sort acquisition instants across timezone offsets', () => {
  const earlier = sample(),
    later = sample();
  earlier.recorded_at = '2026-09-14T11:00:00+02:00';
  later.recorded_at = '2026-09-14T10:00:00Z';
  later.id = 'later-campaign';
  later.input_sha256 = 'f'.repeat(64);
  assert.equal(validateCatalog([earlier, later])[0].id, later.id);
});

test('report links cannot execute scripts or carry credentials', () => {
  for (const url of [
    'javascript:alert(1)',
    'http://example.com',
    'https://user:secret@example.com',
    'https://127.0.0.1/report',
    'https://localhost/report',
  ]) {
    const c = sample();
    c.links.report = url;
    assert.throws(() => parseSubmission(c));
  }
  const c = sample();
  c.links.report = 'https://example.com/report.html';
  assert.equal(parseSubmission(c).links.report, c.links.report);
});

test('longer campaign classification requires three repeats of each exact case', () => {
  const base = sample().runs[0];
  const runs = [1, 2, 3].map((repetition) => ({
    ...structuredClone(base),
    id: `run-${repetition}`,
    repetition,
    measurement_seconds: 30,
  }));
  assert.equal(classify(runs), 'benchmark');
  for (const mutate of [
    (r: any) => (r.mode = r.mode === 'replay' ? 'stream' : 'replay'),
    (r: any) => (r.backend = 'python'),
    (r: any) => r.config.seed++,
    (r: any) => (r.context.fingerprint = 'e'.repeat(64)),
    (r: any) => r.warmup_seconds++,
    (r: any) => (r.repetition = 1),
    (r: any) => (r.measurement_seconds = 5),
  ]) {
    const altered = structuredClone(runs);
    mutate(altered[2]);
    assert.equal(classify(altered), 'smoke');
  }
  for (const protocol of ['headless', 'offscreen', 'x11', null]) {
    const altered = structuredClone(runs);
    altered[0].context.display_protocol = protocol;
    assert.equal(classify(altered), 'diagnostic');
  }
});

test('export keeps acquisition metadata, omits private fields and does not mutate input', async () => {
  const raw = rawSummary(),
    before = structuredClone(raw);
  const result = await exportSummary(raw, options);
  assert.deepEqual(raw, before);
  assert.equal(result.recorded_at, '2026-09-14T11:04:02+02:00');
  assert.equal(result.runs[0].context.commit, 'b'.repeat(40));
  assert.equal(result.runs[0].context.display_protocol, 'native');
  assert.equal(result.classification, 'smoke');
  assert.doesNotMatch(JSON.stringify(result), /PRIVATE_|2030-01-01/);
  assert.deepEqual(result.links, { report: null, extended_report: null, raw_data: null });
});

test('report regeneration and per-run timestamps do not create different acquisitions or contexts', async () => {
  const raw = rawSummary(),
    first = await exportSummary(raw, options);
  raw.report_provenance.recorded_at = '2040-01-01T00:00:00Z';
  raw.runs[0].provenance.recorded_at = '2040-01-01T00:00:00Z';
  const second = await exportSummary(raw, { ...options, id: 'renamed-campaign' });
  assert.equal(first.input_sha256, second.input_sha256);
  assert.equal(first.runs[0].context.fingerprint, second.runs[0].context.fingerprint);
  raw.runs[0].metadata.versions.renderer = '2.0';
  const changed = await exportSummary(raw, options);
  assert.notEqual(first.runs[0].context.fingerprint, changed.runs[0].context.fingerprint);
});

test('failed runs and missing observations survive export; combined hosts are refused', async () => {
  const raw = rawSummary();
  raw.runs[0].status = 'failed';
  raw.runs[0].samples = 0;
  raw.runs[0].submitted_hz = null;
  const result = await exportSummary(raw, options);
  assert.equal(result.runs.length, raw.runs.length);
  assert.equal(result.runs[0].metrics.submitted_hz, null);
  assert.equal(result.runs[0].status, 'failed');
  await assert.rejects(
    exportSummary({ ...raw, campaign: { ...raw.campaign, merged_extension_runs: 1 } }, options),
    /separately/,
  );
  await assert.rejects(
    exportSummary({ ...raw, diagnostics: { entries: { other: {} } } }, options),
    /separately/,
  );
  await assert.rejects(
    exportSummary({ ...raw, campaign: { ...raw.campaign, manifest_present: false } }, options),
    /manifest/,
  );
});

test('catalogue loader checks filenames and refuses symlinks', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'plotbench-catalog-'));
  try {
    await writeFile(join(directory, 'README.md'), 'Not a submission');
    assert.equal((await loadCatalog(directory)).campaigns.length, 0);
    const c = sample(),
      path = join(directory, c.id + '.json');
    await writeFile(path, JSON.stringify(c));
    assert.equal((await loadCatalog(directory)).campaigns.length, 1);
    await writeFile(join(directory, c.id + '-2.json'), JSON.stringify(c));
    await assert.rejects(loadCatalog(directory), new RegExp(`rename it to ${c.id}\\.json`));
    await rm(join(directory, c.id + '-2.json'));
    const stale: any = sample();
    stale.id = 'stale-export';
    for (const run of stale.runs) {
      delete run.config.waveform_plots;
      delete run.config.curves;
      delete run.config.image_plots;
    }
    await writeFile(join(directory, 'stale-export.json'), JSON.stringify(stale));
    await assert.rejects(
      loadCatalog(directory),
      /stale-export\.json: .*\(\+23 more\)\. This file predates .*export it again/,
    );
    await rm(join(directory, 'stale-export.json'));
    await symlink(path, join(directory, 'linked.json'));
    await assert.rejects(loadCatalog(directory), /regular JSON/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test('submission fields are proposed from public summary data only', async () => {
  const raw = rawSummary();
  const proposed = suggestSubmission(raw);
  assert.deepEqual(
    { ...proposed, notes: undefined },
    {
      id: 'test-cpu-test-os-20260914-test-suite',
      hostId: 'test-cpu-test-os',
      hostLabel: 'Test CPU · Test OS',
      notes: undefined,
    },
  );
  assert.equal(
    proposed.notes,
    '1 repetition per case, 2 s warmup and 5 s measurement per run. Native desktop display.',
  );
  assert.doesNotMatch(JSON.stringify(proposed), /PRIVATE_/);
  assert.equal((await exportSummary(raw, proposed)).host.label, 'Test CPU · Test OS');

  raw.campaign.suite_name = 'A very long suite name '.repeat(8);
  raw.campaign.hardware.os = 'macOS 15.7.5 (24G624)';
  const runs: any[] = raw.runs;
  runs[0].metadata = { ...runs[0].metadata, pixel_ratio: 2, display: { refresh_hz: 120 } };
  const long = suggestSubmission(raw);
  assert.match(long.id, /^[a-z0-9][a-z0-9-]{0,79}$/);
  assert.ok(long.id.length <= 80 && !long.id.endsWith('-'));
  assert.equal(long.hostId, 'test-cpu-macos');
  assert.equal(long.hostLabel, 'Test CPU · macOS');
  assert.match(long.notes, /more than one display context/);
  for (const run of runs) run.metadata = runs[0].metadata;
  assert.match(suggestSubmission(raw).notes, /Native desktop display at 120 Hz and 2× scaling\./);
  // The run-level flag decides, as in the export; the campaign flag is the fallback.
  for (const run of runs) run.metadata = { ...run.metadata, headless: true };
  assert.match(suggestSubmission(raw).notes, /Headless or offscreen/);

  const empty = suggestSubmission({});
  assert.deepEqual(empty, { id: 'host', hostId: 'host', hostLabel: 'Unknown CPU', notes: '' });
  assert.match(empty.id, /^[a-z0-9][a-z0-9-]{0,79}$/);
});

test('plot counts are kept, and summaries without counts mean one plot and one curve', async () => {
  const raw = rawSummary();
  const runs: any[] = raw.runs;
  runs[0].config = { ...runs[0].config };
  delete runs[0].config.waveform_plots;
  delete runs[0].config.curves;
  delete runs[0].config.image_plots;
  runs[1].config = { ...runs[1].config, waveform_plots: 2, curves: 3, image_plots: 3 };
  const result = await exportSummary(raw, options);
  const counts = (c: Submission['runs'][number]['config']) => [
    c.waveform_plots,
    c.curves,
    c.image_plots,
  ];
  assert.deepEqual(counts(result.runs[0].config), [1, 1, 1]);
  assert.deepEqual(counts(result.runs[1].config), [2, 3, 3]);
  assert.notEqual(
    workloadKey(result.runs[0].config),
    workloadKey({ ...result.runs[0].config, curves: 2 }),
  );
  assert.match(workloadLabel({ ...result.runs[1].config, view: 'both' }), /2 plots × 3 curves/);
  assert.match(workloadLabel({ ...result.runs[1].config, view: 'both' }), /3 plots · /);
  assert.doesNotMatch(workloadLabel(result.runs[0].config), /plots/);
});
