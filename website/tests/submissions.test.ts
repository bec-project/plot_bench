import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, writeFile, symlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import seed from './fixtures/baseline-campaign.json';
import { SECTIONS } from '../src/baseline';
import { classify, workloadKey, workloadLabel, type Submission } from '../src/model';
import { parseSubmission, parseSubmissionText, validateCatalog } from '../src/validation';
import { exportSummary, suggestSubmission } from '../src/export';
import { loadCatalog } from '../scripts/catalog';

const sample = (): Submission => parseSubmission(structuredClone(seed));
const options = { id: 'test-campaign', hostId: 'test-host', hostLabel: 'Test host' };
const NOT_BASELINE = /Not a baseline campaign: /;
const NOT_EXPORTABLE =
  /Only campaigns of the official baseline suite can be published\. Run \.\/scripts\/plotbench run --baseline without timing, repetition, mode, backend or limit overrides\. Problem: /;

// Synthetic acquisition metadata shaped like a summary.json of the official baseline
// (seven cases, 3 x 30 s, 2 s cooldown, Rust source, streaming). It exercises the exporter
// without requiring a contributor's private raw files or starting a benchmark.
function rawSummary() {
  const c = sample();
  return {
    campaign: {
      manifest_present: true,
      started_at: '2026-09-14T11:04:02+02:00 (2026-09-14T09:04:02+00:00)',
      suite_name: 'Plotbench baseline',
      completion_status: 'completed',
      runs_planned: c.runs.length,
      headless: false,
      warmup_seconds: 5,
      measurement_seconds: 30,
      cooldown_seconds: 2,
      repetitions: 3,
      modes: ['stream'],
      backends: ['rust'],
      frontends: ['pyqtgraph', 'matplotlib'],
      cases: SECTIONS.map((s) => ({ name: s.slug, config: { ...s.config } })),
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
      // summary.json rows carry the workload plus the source generation counter.
      config: { ...r.config, generation: 0 },
      measurement_seconds: r.measurement_seconds,
      warmup_seconds: r.warmup_seconds,
      samples: r.samples,
      ...r.metrics,
      metadata: {
        headless: false,
        qt_platform_plugin: 'cocoa',
        renderer: r.context.renderer,
        measurement_stage: r.context.measurement_stage,
        versions: { ...r.context.versions },
        pixel_ratio: 2,
        viewport_size: [1100, 820],
        plot_viewports: { ...r.context.plot_viewports },
        display: { refresh_hz: 120, device_pixel_ratio: 2, name: 'PRIVATE_DISPLAY' },
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
type RawSummary = ReturnType<typeof rawSummary>;

test('real seed validates; workload identity ignores JSON property order', () => {
  assert.equal(parseSubmission(sample()).runs.length, 42);
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
    (c: any) => (c.classification = 'smoke'),
    (c: any) => (c.runs[0].config.curves = 65),
    (c: any) => delete c.runs[0].config.image_plots,
  ]) {
    const c = sample();
    mutate(c);
    assert.throws(() => parseSubmission(c));
  }
  assert.throws(() => parseSubmissionText(' '.repeat(5 * 1024 * 1024 + 1)), /5 MiB/);
});

test('only complete benchmark-classified baseline campaigns pass the submission gate', () => {
  const single = sample();
  single.runs = single.runs.filter((r) => r.frontend === 'pyqtgraph');
  single.planned_runs = single.runs.length;
  assert.equal(parseSubmission(single).runs.length, 21);
  const deviations: [RegExp, (c: Submission) => void][] = [
    [
      /run-0001: workload \(waveform, 30 Hz.*\) is not a baseline section/,
      all((r) => (r.config.hz = 30)),
    ],
    [/run-0001: source backend python; the baseline uses rust/, all((r) => (r.backend = 'python'))],
    [/run-0001: delivery mode replay; the baseline uses stream/, all((r) => (r.mode = 'replay'))],
    [
      /run-0001: measured 10 s; the baseline measures 30 s/,
      all((r) => (r.measurement_seconds = 10)),
    ],
    [/run-0001: warmup 2 s; the baseline warms up 5 s/, all((r) => (r.warmup_seconds = 2))],
    [
      /run-0001: scenario "renamed" must be the section name "waveform"/,
      (c) => (c.runs[0].scenario = 'renamed'),
    ],
    [
      /run-0001: frontend unknown is not part of the baseline suite/,
      (c) =>
        c.runs.filter((r) => r.frontend === 'pyqtgraph').forEach((r) => (r.frontend = 'unknown')),
    ],
    [
      /section "large-image" has no runs; all 7 sections are required/,
      (c) => {
        c.runs = c.runs.filter((r) => r.scenario !== 'large-image');
        c.planned_runs = c.runs.length;
      },
    ],
    [
      /pyqtgraph: section "waveform" has repetitions \[1, 2, 4\] instead of 1\.\.3/,
      (c) => (c.runs[2].repetition = 4),
    ],
    [
      // A missing repetition also drops the campaign to smoke, which the gate names first.
      /classification is smoke/,
      (c) => {
        c.runs.splice(2, 1);
        c.planned_runs = c.runs.length;
        c.classification = 'smoke';
      },
    ],
    [
      /planned_runs 43 differs from 42 \(7 sections x 3 repetitions x 2 frontends\)/,
      (c) => (c.planned_runs = 43),
    ],
    [
      /run-0001: official campaigns need a recorded commit from a clean checkout/,
      (c) => (c.runs[0].context.dirty = true),
    ],
    [
      /run-0001: official campaigns need a recorded commit from a clean checkout/,
      (c) => (c.runs[0].context.commit = null),
    ],
    [
      /classification is smoke; the results site publishes only complete benchmark-classified runs of scenarios\/baseline\.json on a visible desktop/,
      (c) => {
        for (const r of c.runs) r.measurement_seconds = 5;
        c.classification = 'smoke';
      },
    ],
    [
      /classification is diagnostic/,
      (c) => {
        for (const r of c.runs) r.context.display_protocol = 'x11';
        c.classification = 'diagnostic';
      },
    ],
  ];
  for (const [pattern, mutate] of deviations) {
    const c = sample();
    mutate(c);
    assert.equal(classify(c.runs), c.classification, pattern.source);
    assert.throws(() => parseSubmission(c), NOT_BASELINE, pattern.source);
    assert.throws(() => parseSubmission(c), pattern);
  }
  const many = sample();
  for (const r of many.runs) r.config.hz = 30;
  assert.throws(() => parseSubmission(many), /is not a baseline section \(\+\d+ more\)$/);
  function all(mutate: (r: Submission['runs'][number]) => void) {
    return (c: Submission) => c.runs.forEach(mutate);
  }
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

test('JFreeChart XWayland baseline is publishable but other XWayland frontends stay diagnostic', async () => {
  const campaign = sample();
  campaign.runs = campaign.runs
    .filter((r) => r.frontend === 'pyqtgraph')
    .map((r) => ({
      ...r,
      frontend: 'jfreechart',
      context: { ...r.context, display_protocol: 'xwayland' },
    }));
  campaign.planned_runs = campaign.runs.length;
  campaign.classification = 'benchmark';
  assert.equal(classify(campaign.runs), 'benchmark');
  assert.equal(parseSubmission(campaign).runs.length, 21);

  const other = structuredClone(campaign);
  other.runs[0].frontend = 'pyqtgraph';
  assert.equal(classify(other.runs), 'diagnostic');

  const raw: any = rawSummary();
  raw.runs = raw.runs.filter((r: any) => r.frontend === 'pyqtgraph');
  raw.campaign.frontends = ['jfreechart'];
  raw.campaign.runs_planned = raw.runs.length;
  for (const run of raw.runs) {
    run.frontend = 'jfreechart';
    delete run.metadata.qt_platform_plugin;
    run.metadata.display_protocol = 'xwayland';
  }
  const exported = await exportSummary(raw, options);
  assert.equal(exported.classification, 'benchmark');
  assert.equal(exported.runs.length, 21);
  assert.ok(exported.runs.every((r) => r.context.display_protocol === 'xwayland'));
  assert.equal(parseSubmission(exported).runs.length, 21);
});

test('export keeps acquisition metadata, omits private fields and does not mutate input', async () => {
  const raw = rawSummary(),
    before = structuredClone(raw);
  const result = await exportSummary(raw, options);
  assert.deepEqual(raw, before);
  assert.equal(result.recorded_at, '2026-09-14T11:04:02+02:00');
  assert.equal(result.runs.length, 42);
  assert.equal(result.runs[0].context.commit, 'b'.repeat(40));
  assert.equal(result.runs[0].context.dirty, false);
  assert.equal(result.runs[0].context.display_protocol, 'native');
  assert.equal(result.runs[0].context.pixel_ratio, 2);
  assert.equal(result.runs[0].context.refresh_hz, 120);
  assert.deepEqual(result.runs[0].context.viewport_size, [1100, 820]);
  assert.equal(result.runs[0].context.headless, false);
  assert.equal(result.classification, 'benchmark');
  assert.equal(result.planned_runs, 42);
  assert.deepEqual(Object.keys(result.runs[0].config).length, 12);
  assert.doesNotMatch(JSON.stringify(result), /PRIVATE_|2030-01-01|generation/);
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
  // A changed library version on one frontend's runs is a new context; the campaign
  // stays benchmark-classified because every repetition of the case shares it.
  for (const r of raw.runs) if (r.frontend === 'pyqtgraph') r.metadata.versions.renderer = '2.0';
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

test('the exporter refuses every campaign that is not the unmodified baseline suite', async () => {
  const cases: [RegExp, (raw: RawSummary) => void][] = [
    [
      /cooldown 1 s; the baseline cools down 2 s between runs$/,
      (raw) => (raw.campaign.cooldown_seconds = 1),
    ],
    [/cooldown not recorded s/, (raw) => delete (raw.campaign as any).cooldown_seconds],
    [
      /repetitions 1; the baseline repeats every case 3 times$/,
      (raw) => (raw.campaign.repetitions = 1),
    ],
    [
      /modes \[stream, replay\]; the baseline uses \[stream\]$/,
      (raw) => (raw.campaign.modes = ['stream', 'replay']),
    ],
    [
      /backends \[python\]; the baseline uses \[rust\]$/,
      (raw) => (raw.campaign.backends = ['python']),
    ],
    [
      /case list \[waveform, multi-curve\] is not the 7 baseline sections; missing multi-plot, scalar-image, rgb-image, multi-image, large-image$/,
      (raw) => (raw.campaign.cases = raw.campaign.cases.slice(0, 2)),
    ],
    [
      /is not the 7 baseline sections; missing large-image; unexpected custom$/,
      (raw) => (raw.campaign.cases[6].name = 'custom'),
    ],
    [
      // The equivalent of `--limit`: the case list is intact but the runs stop early.
      /section "scalar-image" has no runs; all 7 sections are required$/,
      (raw) => {
        raw.runs = raw.runs.filter((r) =>
          ['waveform', 'multi-curve', 'multi-plot'].includes(r.scenario),
        );
        raw.campaign.runs_planned = raw.runs.length;
      },
    ],
    [
      /run-0001: workload \(waveform, 30 Hz.*\) is not a baseline section$/,
      (raw) => raw.runs.forEach((r) => (r.config.hz = 30)),
    ],
    [
      /run-0001: measured 10 s; the baseline measures 30 s$/,
      (raw) => raw.runs.forEach((r) => (r.measurement_seconds = 10)),
    ],
    [/planned_runs 189 differs from 42/, (raw) => (raw.campaign.runs_planned = 189)],
    [
      /run-0022: frontend other is not part of the baseline suite$/,
      (raw) =>
        raw.runs.forEach((r) => (r.frontend = r.frontend === 'matplotlib' ? 'other' : r.frontend)),
    ],
  ];
  for (const [pattern, mutate] of cases) {
    const raw = rawSummary();
    mutate(raw);
    await assert.rejects(exportSummary(raw, options), NOT_EXPORTABLE, pattern.source);
    await assert.rejects(exportSummary(raw, options), pattern);
  }
});

test('catalogue loader checks filenames, refuses symlinks and explains rejections', async () => {
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
    // One schema error per missing plot-count key and run; the first leads the summary.
    const more = 3 * stale.runs.length - 1;
    await assert.rejects(
      loadCatalog(directory),
      new RegExp(
        `stale-export\\.json: .*\\(\\+${more} more\\)\\. This file predates .*export it again`,
      ),
    );
    await rm(join(directory, 'stale-export.json'));
    const smoke = sample();
    smoke.id = 'smoke-export';
    for (const run of smoke.runs) run.measurement_seconds = 5;
    smoke.classification = 'smoke';
    await writeFile(join(directory, 'smoke-export.json'), JSON.stringify(smoke));
    await assert.rejects(
      loadCatalog(directory),
      /smoke-export\.json: Not a baseline campaign: classification is smoke; .*\. Only complete runs of scenarios\/baseline\.json are published; see website\/results\/README\.md\.$/,
    );
    await rm(join(directory, 'smoke-export.json'));
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
      id: 'test-cpu-test-os-20260914-plotbench-baseline',
      hostId: 'test-cpu-test-os',
      hostLabel: 'Test CPU · Test OS',
      notes: undefined,
    },
  );
  assert.equal(
    proposed.notes,
    'Official Plotbench baseline suite, 7 sections. 3 repetitions per case, 5 s warmup and 30 s measurement per run. Native desktop display at 120 Hz and 2× scaling.',
  );
  assert.doesNotMatch(JSON.stringify(proposed), /PRIVATE_/);
  assert.equal((await exportSummary(raw, proposed)).host.label, 'Test CPU · Test OS');

  // An edited suite name never changes the identifier; only baseline campaigns publish.
  raw.campaign.suite_name = 'A very long suite name '.repeat(8);
  raw.campaign.hardware.cpu_model = 'A very long CPU model name with many words '.repeat(3);
  raw.campaign.hardware.os = 'macOS 15.7.5 (24G624)';
  const runs: any[] = raw.runs;
  // Runs that report nothing do not split the context; a conflicting rate does.
  runs[0].metadata = { ...runs[0].metadata, pixel_ratio: undefined, display: undefined };
  assert.match(suggestSubmission(raw).notes, /Native desktop display at 120 Hz and 2× scaling\./);
  runs[1].metadata = { ...runs[1].metadata, display: { refresh_hz: 60 } };
  const long = suggestSubmission(raw);
  assert.match(long.id, /^[a-z0-9][a-z0-9-]{0,79}-plotbench-baseline$/);
  assert.ok(long.id.length <= 80 && !long.id.endsWith('-'));
  assert.ok(long.hostId.length <= 40 && !long.hostId.endsWith('-'));
  assert.equal(long.hostLabel, `${raw.campaign.hardware.cpu_model} · macOS`);
  assert.match(long.notes, /more than one display context/);
  for (const run of runs) run.metadata = runs[1].metadata;
  assert.match(suggestSubmission(raw).notes, /Native desktop display at 60 Hz and 2× scaling\./);
  // The run-level flag decides, as in the export; the campaign flag is the fallback.
  for (const run of runs) run.metadata = { ...run.metadata, headless: true };
  assert.match(suggestSubmission(raw).notes, /Headless or offscreen/);

  const empty = suggestSubmission({});
  assert.deepEqual(empty, {
    id: 'host-plotbench-baseline',
    hostId: 'host',
    hostLabel: 'Unknown CPU',
    notes: 'Official Plotbench baseline suite, 7 sections.',
  });
  assert.match(empty.id, /^[a-z0-9][a-z0-9-]{0,79}$/);
});

test('plot counts are kept, and summaries without counts mean one plot and one curve', async () => {
  const raw = rawSummary();
  const runs: any[] = raw.runs;
  // A pre-plot-count summary of the single-plot waveform section still is that section.
  for (const run of runs.filter((r) => r.scenario === 'waveform')) {
    run.config = { ...run.config };
    delete run.config.waveform_plots;
    delete run.config.curves;
    delete run.config.image_plots;
  }
  const result = await exportSummary(raw, options);
  const counts = (c: Submission['runs'][number]['config']) => [
    c.waveform_plots,
    c.curves,
    c.image_plots,
  ];
  assert.deepEqual(counts(result.runs[0].config), [1, 1, 1]);
  const multi = result.runs.find((r) => r.scenario === 'multi-plot')!.config;
  assert.deepEqual(counts(multi), [2, 5, 1]);
  assert.notEqual(workloadKey(multi), workloadKey({ ...multi, curves: 2 }));
  assert.match(workloadLabel({ ...multi, view: 'both' }), /2 plots × 5 curves/);
  assert.match(workloadLabel({ ...multi, image_plots: 3, view: 'both' }), /3 plots · /);
  assert.doesNotMatch(workloadLabel(result.runs[0].config), /plots/);
  // Other plot counts are another workload and therefore not publishable.
  runs[0].config = { ...runs[0].config, waveform_plots: 2, curves: 3, image_plots: 3 };
  await assert.rejects(
    exportSummary(raw, options),
    /Problem: run-0001: workload \(waveform, 60 Hz, 10000 points, 2 x 3 curves.*3 image plots.*\) is not a baseline section$/,
  );
});

test('interrupted, truncated or hand-merged campaigns are refused at the gate and at export', async () => {
  const interrupted = sample();
  interrupted.completion_status = 'interrupted';
  assert.throws(
    () => parseSubmission(interrupted),
    /Not a baseline campaign: completion status "interrupted"/,
  );
  const truncated = sample();
  truncated.runs[41].status = 'interrupted';
  assert.throws(
    () => parseSubmission(truncated),
    /Not a baseline campaign: run-0042: run was interrupted/,
  );
  const merged = sample();
  for (const r of merged.runs) if (r.frontend === 'matplotlib') r.context.commit = 'e'.repeat(40);
  assert.throws(
    () => parseSubmission(merged),
    /Not a baseline campaign: runs span 2 source commits/,
  );
  const raw = rawSummary();
  raw.campaign.completion_status = 'interrupted';
  await assert.rejects(exportSummary(raw, options), /Problem: completion status "interrupted"/);
  const mixed = rawSummary();
  for (const r of mixed.runs)
    if (r.frontend === 'matplotlib') r.provenance.git = { commit: 'e'.repeat(40), dirty: false };
  await assert.rejects(
    exportSummary(mixed, options),
    /Problem: run-\d+: recorded at commit eeeeeee while the campaign manifest records bbbbbbb/,
  );
});
