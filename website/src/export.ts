import { classify, type Run, type Submission, type Workload } from './model';
import { parseSubmission } from './validation';
import { BASELINE, SECTIONS, baselineProblems, type BaselineRun } from './baseline';

type RecordValue = Record<string, any>;
function record(value: unknown): RecordValue {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value as RecordValue;
}
const numeric = (v: unknown): number | null =>
  typeof v === 'number' && Number.isFinite(v) ? v : null;
const string = (v: unknown): string | null => (typeof v === 'string' && v.length ? v : null);
const boolean = (v: unknown): boolean | null => (typeof v === 'boolean' ? v : null);
const pair = (v: unknown): [number, number] | null =>
  Array.isArray(v) &&
  v.length === 2 &&
  v.every((x) => typeof x === 'number' && Number.isFinite(x) && x > 0)
    ? [v[0], v[1]]
    : null;
function canonical(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object')
    return (
      '{' +
      Object.entries(value)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => JSON.stringify(k) + ':' + canonical(v))
        .join(',') +
      '}'
    );
  return JSON.stringify(value ?? null);
}
export async function digest(value: string): Promise<string> {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, '0')).join('');
}
// Normalize the reported windowing system to the submission's protocol names.
function displayProtocol(metadata: RecordValue, provenance: RecordValue): string | null {
  const runtime = record(record(provenance.preflight).runtime);
  const reported =
    string(metadata.qt_platform_plugin) ??
    string(metadata.display_protocol) ??
    string(record(runtime.display).display_protocol);
  return reported === 'cocoa' || reported === 'windows'
    ? 'native'
    : reported === 'xcb'
      ? 'x11'
      : reported;
}
// summary.json rows carry the workload plus a `generation` counter; only the published
// fields are exported, and summaries written before plot counts existed mean one plot.
function publishedConfig(value: unknown): Workload {
  const config = record(value);
  const c: RecordValue = {};
  for (const key of [
    'hz',
    'points',
    'append_count',
    'width',
    'height',
    'waveform_mode',
    'image_mode',
    'view',
    'seed',
  ])
    c[key] = config[key];
  for (const key of ['waveform_plots', 'curves', 'image_plots']) c[key] = numeric(config[key]) ?? 1;
  return c as Workload;
}
const sameList = (value: unknown, expected: readonly string[]) =>
  Array.isArray(value) &&
  value.length === expected.length &&
  value.every((v, i) => v === expected[i]);
const shown = (value: unknown) => (Array.isArray(value) ? `[${value.join(', ')}]` : 'not recorded');
// Campaign-level facts that only the raw summary can prove (cooldown, the suite's repetition
// count, its mode/backend lists and its case list), then the structural run rule shared
// with the submission gate. Returns the refusal message, or null for a baseline campaign.
function baselineRefusal(summary: RecordValue, campaign: RecordValue): string | null {
  const slugs = SECTIONS.map((s) => s.slug);
  const problem = (() => {
    if (numeric(campaign.cooldown_seconds) !== BASELINE.cooldownSeconds)
      return `cooldown ${numeric(campaign.cooldown_seconds) ?? 'not recorded'} s; the baseline cools down ${BASELINE.cooldownSeconds} s between runs`;
    if (numeric(campaign.repetitions) !== BASELINE.repetitions)
      return `repetitions ${numeric(campaign.repetitions) ?? 'not recorded'}; the baseline repeats every case ${BASELINE.repetitions} times`;
    if (!sameList(campaign.modes, [BASELINE.mode]))
      return `modes ${shown(campaign.modes)}; the baseline uses [${BASELINE.mode}]`;
    if (!sameList(campaign.backends, [BASELINE.backend]))
      return `backends ${shown(campaign.backends)}; the baseline uses [${BASELINE.backend}]`;
    const names = Array.isArray(campaign.cases)
      ? campaign.cases
          .map((c: unknown) => record(c).name)
          .filter((n): n is string => typeof n === 'string')
      : [];
    const missing = slugs.filter((s) => !names.includes(s)),
      extra = names.filter((n) => !slugs.includes(n));
    if (missing.length || extra.length || names.length !== slugs.length)
      return (
        `case list [${names.join(', ')}] is not the ${slugs.length} baseline sections` +
        (missing.length ? `; missing ${missing.join(', ')}` : '') +
        (extra.length ? `; unexpected ${extra.join(', ')}` : '')
      );
    const manifestGit = record(record(campaign.provenance).git);
    const rows = (Array.isArray(summary.runs) ? summary.runs : []).map((input) => record(input));
    // Every row must carry the manifest's own revision: rows patched in from another
    // acquisition are refused here, before the structural rule counts them.
    for (const r of rows) {
      const p = record(r.provenance),
        git = record(p.git);
      const rowCommit = string(git.commit),
        rowSource = string(p.source_sha256);
      if (rowCommit && string(manifestGit.commit) && rowCommit !== manifestGit.commit)
        return `${String(r.run_id ?? '')}: recorded at commit ${rowCommit.slice(0, 7)} while the campaign manifest records ${String(manifestGit.commit).slice(0, 7)}; export each acquisition separately`;
      if (
        rowSource &&
        string(record(campaign.provenance).source_sha256) &&
        rowSource !== record(campaign.provenance).source_sha256
      )
        return `${String(r.run_id ?? '')}: source hash differs from the campaign manifest; export each acquisition separately`;
    }
    const runs: BaselineRun[] = rows.map((r) => {
      return {
        id: String(r.run_id ?? ''),
        status: String(r.status ?? ''),
        commit: string(record(record(r.provenance).git).commit),
        source_hash: string(record(r.provenance).source_sha256),
        scenario: String(r.scenario ?? ''),
        frontend: String(r.frontend ?? ''),
        backend: String(r.backend ?? ''),
        mode: String(r.mode ?? ''),
        repetition: numeric(r.repetition) ?? 0,
        measurement_seconds: numeric(r.measurement_seconds) ?? 0,
        warmup_seconds: numeric(r.warmup_seconds) ?? 0,
        config: publishedConfig(r.config),
      };
    });
    return (
      baselineProblems({
        planned_runs: numeric(campaign.runs_planned) ?? 0,
        completion_status:
          typeof campaign.completion_status === 'string'
            ? campaign.completion_status
            : 'not recorded',
        runs,
      })[0] ?? null
    );
  })();
  return (
    problem &&
    `Only campaigns of the official baseline suite can be published. Run ./scripts/plotbench run --baseline without timing, repetition, mode, backend or limit overrides. Problem: ${problem}`
  );
}
export interface ExportOptions {
  id: string;
  hostId: string;
  hostLabel: string;
  notes?: string;
}
export async function exportSummary(raw: unknown, options: ExportOptions): Promise<Submission> {
  const summary = record(raw),
    campaign = record(summary.campaign),
    hardware = record(campaign.hardware);
  if (campaign.manifest_present !== true || !Array.isArray(summary.runs) || !summary.runs.length)
    throw new Error('Choose a Plotbench summary.json with a recorded campaign manifest and runs.');
  if (
    Object.keys(record(record(summary.diagnostics).entries)).length > 0 ||
    (Array.isArray(summary.diagnostics) && summary.diagnostics.length > 0) ||
    (campaign.merged_extension_runs ?? 0) > 0 ||
    (campaign.extensions?.length ?? 0) > 0 ||
    summary.runs.some((r: RecordValue) => r.extension)
  )
    throw new Error(
      'Export the original campaign summaries separately; merged extensions and diagnostic bundles can contain other hosts.',
    );
  const refusal = baselineRefusal(summary, campaign);
  if (refusal) throw new Error(refusal);
  const provenance = record(campaign.provenance);
  const runs: Run[] = await Promise.all(
    summary.runs.map(async (input: unknown) => {
      const r = record(input),
        m = record(r.metadata),
        p = record(r.provenance);
      const c = publishedConfig(r.config);
      const metrics: RecordValue = {};
      for (const key of [
        'submitted_hz',
        'update_p50_ms',
        'update_p95_ms',
        'cpu_mean_percent',
        'rss_peak_mib',
        'gap_percent',
        'source_hz',
        'source_deadline_misses',
        'source_mailbox_drops',
      ])
        metrics[key] = numeric(r[key]);
      const display = record(m.display);
      const headless = boolean(m.headless) ?? boolean(campaign.headless);
      const protocol = displayProtocol(m, p);
      const versions: Record<string, string> = {};
      for (const [name, value] of Object.entries(record(m.versions)))
        if (typeof value === 'string') versions[name] = value;
      // Retain a hash of the full acquisition/build/display context without publishing
      // its local paths, display names, environment values or other private metadata.
      const fingerprint = await digest(
        canonical({
          source: p.source_sha256,
          git: p.git,
          artifacts: Object.fromEntries(
            Object.entries(record(p.artifacts)).map(([k, v]) => [k, record(v).files]),
          ),
          preflight: p.preflight,
          display_contexts: r.observed_display_contexts,
          renderer: m.renderer,
          stage: m.measurement_stage,
          versions: m.versions,
          renderer_environment: m.renderer_environment,
          backend: r.backend,
        }),
      );
      return {
        id: r.run_id,
        scenario: r.scenario,
        frontend: r.frontend,
        backend: r.backend,
        mode: r.mode,
        repetition: r.repetition,
        status: r.status,
        config: c,
        measurement_seconds: r.measurement_seconds,
        warmup_seconds: r.warmup_seconds,
        samples: r.samples ?? 0,
        context: {
          fingerprint,
          source_hash: string(p.source_sha256 ?? provenance.source_sha256),
          commit: string(record(p.git).commit ?? record(provenance.git).commit),
          dirty: boolean(record(p.git).dirty ?? record(provenance.git).dirty),
          renderer: string(m.renderer),
          measurement_stage: string(m.measurement_stage),
          versions,
          pixel_ratio: numeric(m.pixel_ratio),
          viewport_size: pair(m.viewport_size),
          plot_viewports: {
            waveform: pair(record(m.plot_viewports).waveform),
            image: pair(record(m.plot_viewports).image),
          },
          display_protocol: [
            'native',
            'wayland',
            'xwayland',
            'x11',
            'offscreen',
            'headless',
          ].includes(protocol ?? '')
            ? protocol
            : null,
          refresh_hz: numeric(display.refresh_hz),
          headless,
        },
        metrics: metrics as Run['metrics'],
      };
    }),
  );
  // A regenerated report's timestamp is not its acquisition date. Normalize the
  // ISO prefix from report.py's human-readable "local (UTC)" timestamp.
  const recordedAt = string(campaign.started_at)?.split(' (')[0];
  const graphics = Array.isArray(hardware.graphics)
    ? hardware.graphics
        .map((g: RecordValue) => g.model)
        .filter((g: unknown) => typeof g === 'string')
        .join(' / ')
    : '';
  const result = {
    schema_version: 1,
    id: options.id,
    title: campaign.suite_name,
    recorded_at: recordedAt,
    input_sha256: await digest(
      canonical({
        started_at: recordedAt,
        hardware,
        source: provenance.source_sha256,
        runs: runs.map(({ context, ...run }) => ({
          ...run,
          source: context.source_hash,
          commit: context.commit,
        })),
      }),
    ),
    host: {
      id: options.hostId,
      label: options.hostLabel,
      cpu: hardware.cpu_model ?? 'Not recorded',
      gpu: graphics || null,
      memory_gib: numeric(hardware.memory_gib),
      os: hardware.os ?? 'Not recorded',
      architecture: hardware.architecture ?? 'Not recorded',
    },
    notes: options.notes ?? '',
    classification: classify(runs),
    completion_status: campaign.completion_status,
    planned_runs: campaign.runs_planned,
    runs,
    links: { report: null, extended_report: null, raw_data: null },
  };
  return parseSubmission(result);
}

const slug = (value: string) =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
// Shorten a slug at a hyphen so a clipped identifier never ends mid-word.
function clip(value: string, limit: number): string {
  if (value.length <= limit) return value;
  const cut = value.slice(0, limit + 1).lastIndexOf('-');
  return (cut > 0 ? value.slice(0, cut) : value.slice(0, limit)).replace(/-+$/, '');
}
// "macOS 15.7.5 (24G624)" -> "macOS", "Ubuntu 24.04.1 LTS" -> "Ubuntu".
function osFamily(os: string | null, platform: string | null): string | null {
  const text = (os ?? platform ?? '').split(/\s*\d/)[0].replace(/-.*$/, '').trim();
  return text.toLowerCase() === 'darwin' ? 'macOS' : text || null;
}
const seconds = (values: number[]): string | null =>
  values.length === 0
    ? null
    : values.length === 1
      ? `${values[0]} s`
      : `${Math.min(...values)}–${Math.max(...values)} s`;
const distinctNumbers = (values: Array<number | null>) => [
  ...new Set(values.filter((v): v is number => v !== null)),
];
const distinctStrings = (values: Array<string | null>) => [
  ...new Set(values.filter((v): v is string => v !== null)),
];

export type SubmissionDefaults = Required<ExportOptions>;

// Propose the contributor-supplied fields from data the export publishes anyway:
// CPU model, OS family, acquisition date, suite name, run timings and display
// context. Hostnames, machine identifiers, display names and paths are never
// used. Contributors review and adjust the proposal before publishing.
export function suggestSubmission(raw: unknown): SubmissionDefaults {
  const summary = record(raw),
    campaign = record(summary.campaign),
    hardware = record(campaign.hardware),
    runs = (Array.isArray(summary.runs) ? summary.runs : []).map(record);
  const cpu = string(hardware.cpu_model),
    family = osFamily(string(hardware.os), string(hardware.platform));
  const hostId = clip(slug(`${cpu ?? 'host'} ${family ?? ''}`) || 'host', 40);
  const hostLabel = [cpu ?? 'Unknown CPU', family].filter(Boolean).join(' · ');
  const date = (string(campaign.started_at) ?? '').slice(0, 10).replace(/-/g, '');
  const stem = [hostId, /^\d{8}$/.test(date) ? date : ''].filter(Boolean).join('-');
  // Only baseline campaigns are published, so the identifier names the suite, not the
  // summary's editable suite_name; a second same-day campaign needs a manual suffix.
  const id = clip([stem, slug(BASELINE.name)].filter(Boolean).join('-'), 80);

  const sentences: string[] = [`Official ${BASELINE.name} suite, ${SECTIONS.length} sections.`];
  const repetitions = Math.max(
    numeric(campaign.repetitions) ?? 0,
    ...runs.map((r) => numeric(r.repetition) ?? 0),
  );
  const warmup = seconds(distinctNumbers(runs.map((r) => numeric(r.warmup_seconds)))),
    measurement = seconds(distinctNumbers(runs.map((r) => numeric(r.measurement_seconds))));
  const timing = [warmup && `${warmup} warmup`, measurement && `${measurement} measurement`]
    .filter(Boolean)
    .join(' and ');
  const setup = [
    repetitions > 0 ? `${repetitions} repetition${repetitions === 1 ? '' : 's'} per case` : '',
    timing ? `${timing} per run` : '',
  ].filter(Boolean);
  if (setup.length) sentences.push(setup.join(', ') + '.');
  // Frontends that report no refresh rate or scale do not create a second display
  // context; only conflicting reported values, or a headless run, change the sentence.
  const contexts = runs.map((r) => {
    const m = record(r.metadata),
      display = record(m.display);
    const protocol = displayProtocol(m, record(r.provenance));
    return {
      headless:
        (boolean(m.headless) ?? boolean(campaign.headless)) === true ||
        protocol === 'offscreen' ||
        protocol === 'headless',
      protocol,
      refresh: numeric(display.refresh_hz),
      scale: numeric(m.pixel_ratio) ?? numeric(display.device_pixel_ratio),
    };
  });
  const protocols = distinctStrings(contexts.map((c) => c.protocol)),
    refreshes = distinctNumbers(contexts.map((c) => c.refresh)),
    scales = distinctNumbers(contexts.map((c) => c.scale));
  if (contexts.some((c) => c.headless))
    sentences.push('Headless or offscreen run without a visible desktop.');
  else if (protocols.length > 1 || refreshes.length > 1 || scales.length > 1)
    sentences.push('Runs were recorded in more than one display context.');
  else if (contexts.length) {
    const label =
      protocols[0] === 'native'
        ? 'Native desktop'
        : protocols[0] === 'wayland'
          ? 'Wayland'
          : protocols[0] === 'xwayland'
            ? 'XWayland'
            : protocols[0] === 'x11'
              ? 'X11'
              : 'Visible';
    sentences.push(
      `${label} display${refreshes[0] ? ` at ${refreshes[0]} Hz` : ''}${scales[0] ? ` and ${scales[0]}× scaling` : ''}.`,
    );
  }
  return { id, hostId, hostLabel, notes: sentences.join(' ').slice(0, 2000) };
}
