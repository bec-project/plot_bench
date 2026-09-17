// Data behind a section board's bar chart. Every bar is the record the ranking
// already selected; the chart adds no statistic of its own.
import type { FrontendRecord, WinnerBoard } from './winners';

export interface ChartBar {
  frontend: string;
  rank: number;
  /** Highest campaign-weighted median among the record's tied groups (the record's score). */
  median: number;
  /** Lowest tied-group median; equals `median` unless equally ranked groups were merged. */
  minimum: number;
  /** Observed range of the valid repetition rates behind the record. */
  low: number | null;
  high: number | null;
  valid: number;
  attempted: number;
  /** Repetitions the data source could not feed at target among the record's groups. */
  sourceLimited: number;
  /** Repetitions the frontend could not consume at target among the record's groups. */
  frontendLimited: number;
  winner: boolean;
}
export interface BoardChartData {
  target: number;
  /** Axis maximum: the target or the highest observed value, with headroom. */
  max: number;
  bars: ChartBar[];
}

function repetitionRates(record: FrontendRecord): number[] {
  return record.groups.flatMap((g) =>
    g.campaigns.flatMap((c) =>
      c.observations.flatMap(({ run: r }) =>
        r.status === 'ok' && r.samples > 0 && r.metrics.submitted_hz !== null
          ? [r.metrics.submitted_hz]
          : [],
      ),
    ),
  );
}

export function boardChart(board: WinnerBoard): BoardChartData {
  const target = board.representative.run.config.hz;
  const bars = board.records.map((record): ChartBar => {
    const rates = repetitionRates(record);
    return {
      frontend: record.frontend,
      rank: record.rank,
      median: record.score,
      minimum: record.minimumScore,
      low: rates.length ? Math.min(...rates) : null,
      high: rates.length ? Math.max(...rates) : null,
      valid: record.groups.reduce((n, g) => n + g.successful, 0),
      attempted: record.groups.reduce((n, g) => n + g.attempted, 0),
      sourceLimited: record.groups.reduce((n, g) => n + g.sourceLimited, 0),
      frontendLimited: record.groups.reduce((n, g) => n + g.frontendLimited, 0),
      winner: record.rank === 1,
    };
  });
  const max = Math.max(target, ...bars.flatMap((b) => [b.median, b.high ?? 0])) * 1.05;
  return { target, max, bars };
}

// Resource metric behind a board's memory/CPU charts. The bar is the same
// ranked value the record card shows; whiskers add the observed spread only.
export type ResourceMetric = 'rss_peak_mib' | 'cpu_mean_percent';
export interface ResourceBar {
  frontend: string;
  rank: number;
  /** The record's ranked value (median peak RSS or median mean CPU), or null when incomplete. */
  value: number | null;
  /** Observed range of that metric across the record's valid repetitions. */
  low: number | null;
  high: number | null;
  samples: number;
  winner: boolean;
}
export interface ResourceChartData {
  /** Axis maximum: the highest observed value with headroom (never below 1). */
  max: number;
  bars: ResourceBar[];
  /** Optional guide line (CPU one-core mark), only when it falls within the axis. */
  reference: number | null;
  /** True when at least one record reports the metric. */
  hasData: boolean;
}

// The same valid-repetition gate as throughput: a repetition contributes its
// resource sample only when it produced a rate. Negatives and non-finite drop.
function repetitionValues(record: FrontendRecord, metric: ResourceMetric): number[] {
  return record.groups.flatMap((g) =>
    g.campaigns.flatMap((c) =>
      c.observations.flatMap(({ run: r }) => {
        if (r.status !== 'ok' || r.samples <= 0 || r.metrics.submitted_hz === null) return [];
        const value = r.metrics[metric];
        return value !== null && Number.isFinite(value) && value >= 0 ? [value] : [];
      }),
    ),
  );
}

export function resourceChart(
  board: WinnerBoard,
  metric: ResourceMetric,
  valueOf: (record: FrontendRecord) => number | null,
  reference: number | null = null,
): ResourceChartData {
  const bars = board.records.map((record): ResourceBar => {
    const value = valueOf(record);
    // Only chart the spread when the ranked value exists, so a missing bar never
    // carries a stray whisker.
    const values = value === null ? [] : repetitionValues(record, metric);
    return {
      frontend: record.frontend,
      rank: record.rank,
      value,
      low: values.length ? Math.min(...values) : null,
      high: values.length ? Math.max(...values) : null,
      samples: values.length,
      winner: record.rank === 1,
    };
  });
  const max = Math.max(1, ...bars.flatMap((b) => [b.value ?? 0, b.high ?? 0])) * 1.05;
  return {
    max,
    bars,
    reference: reference !== null && reference <= max ? reference : null,
    hasData: bars.some((b) => b.value !== null),
  };
}
