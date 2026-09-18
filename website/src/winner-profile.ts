import type { WinnerBoard } from './winners';

/** The radar uses the exact configuration and normalized axes used for ranking. */
export interface ProfilePoint {
  frontend: string;
  rank: number;
  winner: boolean;
  inBand: boolean;
  rateBand: number;
  throughput: number;
  rss: number;
  cpu: number;
  gThroughput: number;
  gRss: number;
  gCpu: number;
  area: number;
}

type Goodness = { throughput: number; rss: number; cpu: number };
export interface ProfileData {
  target: number;
  points: ProfilePoint[];
  /** Per-axis worst shown value in each band; different bands have different scales. */
  worstGoodness: Record<number, Goodness>;
}

export function profileData(board: WinnerBoard): ProfileData {
  const points: ProfilePoint[] = board.records.map((record) => ({
    frontend: record.frontend,
    rank: record.rank,
    winner: record.rank === 1,
    inBand: record.rateBand === 0,
    rateBand: record.rateBand,
    throughput: record.representativeGroup.rates.median!,
    rss: record.memoryMib,
    cpu: record.cpuPercent,
    gThroughput: record.profile.throughput,
    gRss: record.profile.rss,
    gCpu: record.profile.cpu,
    area: record.profile.area,
  }));
  const worstGoodness: Record<number, Goodness> = {};
  for (const p of points) {
    const previous = worstGoodness[p.rateBand];
    worstGoodness[p.rateBand] = {
      throughput: Math.min(previous?.throughput ?? 1, p.gThroughput),
      rss: Math.min(previous?.rss ?? 1, p.gRss),
      cpu: Math.min(previous?.cpu ?? 1, p.gCpu),
    };
  }
  return { target: board.representative.run.config.hz, points, worstGoodness };
}
