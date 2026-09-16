export interface Host {
  id: string;
  label: string;
  cpu: string;
  gpu: string | null;
  memory_gib: number | null;
  os: string;
  architecture: string;
}
export interface Workload {
  hz: number;
  points: number;
  append_count: number;
  width: number;
  height: number;
  waveform_mode: 'replace' | 'append';
  image_mode: 'scalar' | 'rgb';
  view: 'waveform' | 'image' | 'both';
  seed: number;
  waveform_plots: number;
  curves: number;
  image_plots: number;
}
export interface Run {
  id: string;
  scenario: string;
  frontend: string;
  backend: 'rust' | 'python';
  mode: 'stream' | 'replay';
  repetition: number;
  status: string;
  config: Workload;
  measurement_seconds: number;
  warmup_seconds: number;
  samples: number;
  context: {
    fingerprint: string;
    source_hash: string | null;
    commit: string | null;
    dirty: boolean | null;
    renderer: string | null;
    measurement_stage: string | null;
    versions: Record<string, string>;
    pixel_ratio: number | null;
    viewport_size: [number, number] | null;
    plot_viewports: { waveform: [number, number] | null; image: [number, number] | null };
    display_protocol: string | null;
    refresh_hz: number | null;
    headless: boolean | null;
  };
  metrics: {
    submitted_hz: number | null;
    update_p50_ms: number | null;
    update_p95_ms: number | null;
    cpu_mean_percent: number | null;
    rss_peak_mib: number | null;
    gap_percent: number | null;
    source_hz: number | null;
    source_deadline_misses: number | null;
    source_mailbox_drops: number | null;
  };
}
export interface Submission {
  schema_version: 1;
  id: string;
  title: string;
  recorded_at: string;
  input_sha256: string;
  host: Host;
  notes: string;
  classification: 'smoke' | 'benchmark' | 'diagnostic';
  completion_status: string;
  planned_runs: number;
  runs: Run[];
  links: { report: string | null; extended_report: string | null; raw_data: string | null };
}
export interface Catalog {
  schema_version: 1;
  campaigns: Submission[];
}
export type Observation = { campaign: Submission; run: Run };
export const REPOSITORY = 'https://github.com/bec-project/plot_bench';
export function observations(campaigns: Submission[]): Observation[] {
  return campaigns.flatMap((campaign) => campaign.runs.map((run) => ({ campaign, run })));
}
export function workloadKey(config: Workload): string {
  // Property order in submitted JSON cannot create different workload identities.
  return JSON.stringify([
    config.view,
    config.hz,
    config.points,
    config.append_count,
    config.waveform_mode,
    config.width,
    config.height,
    config.image_mode,
    config.seed,
    config.waveform_plots,
    config.curves,
    config.image_plots,
  ]);
}
export function workloadLabel(c: Workload): string {
  const parts = [];
  if (c.view !== 'image') {
    const layout =
      c.waveform_plots > 1 || c.curves > 1
        ? `${c.waveform_plots} plot${c.waveform_plots === 1 ? '' : 's'} × ${c.curves} curve${c.curves === 1 ? '' : 's'} · `
        : '';
    parts.push(`${layout}${c.points.toLocaleString()} points · ${c.waveform_mode}`);
  }
  if (c.view !== 'waveform') {
    const layout = c.image_plots > 1 ? `${c.image_plots} plots · ` : '';
    parts.push(`${layout}${c.width} × ${c.height} · ${c.image_mode}`);
  }
  return `${parts.join(' / ')} · ${c.hz} Hz`;
}
export function sourceLimited(run: Run): boolean {
  return (
    (run.metrics.source_deadline_misses ?? 0) > 0 || (run.metrics.source_mailbox_drops ?? 0) > 0
  );
}
export function classify(runs: Run[]): Submission['classification'] {
  if (
    runs.some(
      (r) =>
        r.context.headless !== false ||
        !(
          ['native', 'wayland'].includes(r.context.display_protocol ?? '') ||
          (r.frontend === 'jfreechart' && r.context.display_protocol === 'xwayland')
        ),
    )
  )
    return 'diagnostic';
  const groups = new Map<string, Set<number>>();
  for (const r of runs) {
    const key = JSON.stringify([
      r.frontend,
      r.backend,
      r.mode,
      workloadKey(r.config),
      r.context.fingerprint,
      r.measurement_seconds,
      r.warmup_seconds,
    ]);
    const reps = groups.get(key) ?? new Set();
    reps.add(r.repetition);
    groups.set(key, reps);
  }
  return runs.every((r) => r.measurement_seconds >= 10) &&
    [...groups.values()].every((reps) => reps.size >= 3)
    ? 'benchmark'
    : 'smoke';
}
