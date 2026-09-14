import { workloadKey, sourceLimited, type Observation, type Submission } from './model';

export interface RateSummary {
  median: number | null;
  q1: number | null;
  q3: number | null;
  min: number | null;
  max: number | null;
  count: number;
}
export interface CampaignGroup {
  campaign: Submission;
  observations: Observation[];
  rates: RateSummary;
  limited: number;
}
export interface ResultGroup {
  key: string;
  representative: Observation;
  campaigns: CampaignGroup[];
  rates: RateSummary;
  attempted: number;
  successful: number;
  limited: number;
  first: string;
  last: string;
  incompleteContext: boolean;
}

// Linear interpolation at (n - 1) * q, matching NumPy's default percentile.
// A single observation has a median but cannot show observed spread.
export function summarizeRates(values: readonly number[]): RateSummary {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  const quantile = (q: number) => {
    const position = (sorted.length - 1) * q,
      lower = Math.floor(position);
    return sorted[lower] + (sorted[Math.ceil(position)] - sorted[lower]) * (position - lower);
  };
  return {
    median: sorted.length ? quantile(0.5) : null,
    q1: sorted.length > 1 ? quantile(0.25) : null,
    q3: sorted.length > 1 ? quantile(0.75) : null,
    min: sorted.length ? sorted[0] : null,
    max: sorted.length ? sorted[sorted.length - 1] : null,
    count: sorted.length,
  };
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object')
    return (
      '{' +
      Object.entries(value)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, item]) => JSON.stringify(key) + ':' + canonical(item))
        .join(',') +
      '}'
    );
  return JSON.stringify(value ?? null);
}

function incompleteContext({ run: r }: Observation): boolean {
  return (
    r.context.source_hash === null ||
    r.context.renderer === null ||
    r.context.measurement_stage === null ||
    !Object.keys(r.context.versions).length ||
    r.context.display_protocol === null ||
    r.context.headless === null
  );
}

export function compatibilityKey(o: Observation): string {
  const { campaign: c, run: r } = o;
  // Friendly labels and scenario names can change without changing the experiment.
  const { label: _label, ...hardware } = c.host;
  return canonical({
    hardware,
    frontend: r.frontend,
    backend: r.backend,
    mode: r.mode,
    workload: workloadKey(r.config),
    context: r.context,
    measurement: r.measurement_seconds,
    warmup: r.warmup_seconds,
    classification: c.classification,
    // Unknown provenance must not imply compatibility between different runs.
    incomplete: incompleteContext(o) ? [c.id, r.id] : null,
  });
}

export function inDateRange(recordedAt: string, from: string, to: string): boolean {
  // Inclusive acquisition dates in UTC, independent of the viewer's timezone.
  const day = new Date(recordedAt).toISOString().slice(0, 10);
  return (!from || day >= from) && (!to || day <= to);
}

export function groupObservations(observations: readonly Observation[]): ResultGroup[] {
  const groups = new Map<string, Map<string, Observation[]>>();
  for (const o of observations) {
    const key = compatibilityKey(o),
      campaigns = groups.get(key) ?? new Map();
    const runs = campaigns.get(o.campaign.id) ?? [];
    runs.push(o);
    campaigns.set(o.campaign.id, runs);
    groups.set(key, campaigns);
  }
  const result: ResultGroup[] = [];
  for (const [key, entries] of groups) {
    const campaigns: CampaignGroup[] = [...entries.values()]
      .map((runs) => ({
        campaign: runs[0].campaign,
        observations: [...runs].sort(
          (a, b) => a.run.repetition - b.run.repetition || a.run.id.localeCompare(b.run.id),
        ),
        rates: summarizeRates(
          runs
            .filter((o) => o.run.status === 'ok' && o.run.samples > 0)
            .flatMap((o) =>
              o.run.metrics.submitted_hz === null ? [] : [o.run.metrics.submitted_hz],
            ),
        ),
        limited: runs.filter((o) => sourceLimited(o.run)).length,
      }))
      .sort(
        (a, b) =>
          Date.parse(b.campaign.recorded_at) - Date.parse(a.campaign.recorded_at) ||
          a.campaign.id.localeCompare(b.campaign.id),
      );
    const representative = campaigns[0].observations[0];
    result.push({
      key,
      representative,
      campaigns,
      rates: summarizeRates(
        campaigns.flatMap((c) => (c.rates.median === null ? [] : [c.rates.median])),
      ),
      attempted: campaigns.reduce((sum, c) => sum + c.observations.length, 0),
      successful: campaigns.reduce((sum, c) => sum + c.rates.count, 0),
      limited: campaigns.reduce((sum, c) => sum + c.limited, 0),
      first: campaigns[campaigns.length - 1].campaign.recorded_at,
      last: campaigns[0].campaign.recorded_at,
      incompleteContext: incompleteContext(representative),
    });
  }
  return result.sort(
    (a, b) => Date.parse(b.last) - Date.parse(a.last) || a.key.localeCompare(b.key),
  );
}
