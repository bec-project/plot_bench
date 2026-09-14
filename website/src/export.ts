import { classify, type Run, type Submission, type Workload } from './model';
import { parseSubmission } from './validation';

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
  const provenance = record(campaign.provenance);
  const runs: Run[] = await Promise.all(
    summary.runs.map(async (input: unknown) => {
      const r = record(input),
        m = record(r.metadata),
        p = record(r.provenance),
        config = record(r.config);
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
        config: c as Workload,
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
          display_protocol: ['native', 'wayland', 'x11', 'offscreen', 'headless'].includes(
            protocol ?? '',
          )
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
  const id = clip([stem, slug(string(campaign.suite_name) ?? '')].filter(Boolean).join('-'), 80);

  const sentences: string[] = [];
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
  const contexts = [
    ...new Set(
      runs.map((r) => {
        const m = record(r.metadata),
          display = record(m.display);
        const protocol = displayProtocol(m, record(r.provenance));
        const headless = boolean(m.headless) ?? boolean(campaign.headless);
        if (headless || protocol === 'offscreen' || protocol === 'headless')
          return 'Headless or offscreen run without a visible desktop.';
        const label =
          protocol === 'native'
            ? 'Native desktop'
            : protocol === 'wayland'
              ? 'Wayland'
              : protocol === 'x11'
                ? 'X11'
                : 'Visible';
        const refresh = numeric(display.refresh_hz),
          scale = numeric(m.pixel_ratio) ?? numeric(display.device_pixel_ratio);
        return `${label} display${refresh ? ` at ${refresh} Hz` : ''}${scale ? ` and ${scale}× scaling` : ''}.`;
      }),
    ),
  ];
  if (contexts.length === 1) sentences.push(contexts[0]);
  else if (contexts.length > 1)
    sentences.push('Runs were recorded in more than one display context.');
  return { id, hostId, hostLabel, notes: sentences.join(' ').slice(0, 2000) };
}
