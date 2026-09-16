import type { WinnerBoard } from './winners';

// Shared derivation for the winner-card profile radar: it reshapes a board's
// per-frontend records into three headline metrics plus a common "goodness" so
// the radar can plot throughput, RAM and CPU on one footing. Pure and
// side-effect free, so it is unit-tested on its own.

/** One frontend's three headline metrics plus their normalized "goodness". */
export interface ProfilePoint {
  frontend: string;
  rank: number;
  winner: boolean;
  /** In the top throughput band (rateBand 0) — the tie-break pool the ranking decides within. */
  inBand: boolean;
  throughput: number; // median submitted updates/s
  rss: number | null; // median peak RSS, MiB
  cpu: number | null; // median mean CPU, percent of one core
  /** Goodness in [0,1], 1 = best. Throughput is measured against the paced target. */
  gThroughput: number;
  /** null when the metric is missing for this frontend. */
  gRss: number | null;
  gCpu: number | null;
}

export interface ProfileData {
  target: number;
  points: ProfilePoint[];
  /** Per-axis worst goodness across the board — the inner hull drawn as a scale reference. */
  worstGoodness: { throughput: number; rss: number; cpu: number };
}

const clamp01 = (value: number) => (value < 0 ? 0 : value > 1 ? 1 : value);
const extent = (values: number[]): { min: number; max: number } | null =>
  values.length ? { min: Math.min(...values), max: Math.max(...values) } : null;

/**
 * Normalize a board's records to a common "outward = better" goodness so the
 * radar can plot throughput, RSS and CPU on one footing:
 *
 * - throughput goodness is the fraction of the paced target reached (capped at
 *   1), so hitting 60 Hz fills the axis and the tied pack sits near the rim;
 * - RSS and CPU goodness are ratio-to-best (bestValue / value), so the lightest
 *   frontend reaches the rim and one that is 12x hungrier reaches ~1/12 of it —
 *   the same absolute magnitudes the bar charts show, not a rank spread.
 */
export function profileData(board: WinnerBoard): ProfileData {
  const target = board.representative.run.config.hz;
  const rssValues = board.records.flatMap((r) => (r.memoryMib === null ? [] : [r.memoryMib]));
  const cpuValues = board.records.flatMap((r) => (r.cpuPercent === null ? [] : [r.cpuPercent]));
  const rss = extent(rssValues);
  const cpu = extent(cpuValues);
  const throughputValues = board.records.map((r) => r.score);

  const points: ProfilePoint[] = board.records.map((record) => ({
    frontend: record.frontend,
    rank: record.rank,
    winner: record.rank === 1,
    inBand: record.rateBand === 0,
    throughput: record.score,
    rss: record.memoryMib,
    cpu: record.cpuPercent,
    gThroughput: clamp01(target > 0 ? record.score / target : 0),
    gRss: record.memoryMib === null || rss === null ? null : rss.min / record.memoryMib,
    gCpu: record.cpuPercent === null || cpu === null ? null : cpu.min / record.cpuPercent,
  }));

  return {
    target,
    points,
    worstGoodness: {
      throughput: clamp01(target > 0 ? Math.min(...throughputValues) / target : 0),
      rss: rss ? rss.min / rss.max : 0,
      cpu: cpu ? cpu.min / cpu.max : 0,
    },
  };
}
