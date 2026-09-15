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
  /** Source-limited repetitions among the record's groups. */
  limited: number;
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
      limited: record.groups.reduce((n, g) => n + g.limited, 0),
      winner: record.rank === 1,
    };
  });
  const max = Math.max(target, ...bars.flatMap((b) => [b.median, b.high ?? 0])) * 1.05;
  return { target, max, bars };
}
