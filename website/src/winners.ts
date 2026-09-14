import { groupObservations, type ResultGroup } from './aggregation';
import { workloadKey, type Observation } from './model';

export interface FrontendRecord {
  frontend: string;
  score: number;
  rank: number;
  groups: ResultGroup[];
}
export interface WinnerBoard {
  key: string;
  representative: Observation;
  records: FrontendRecord[];
  evaluatedGroups: number;
  hosts: number;
}
export interface WinnerCollection {
  boards: WinnerBoard[];
  excludedGroups: number;
}

// Rank at the precision shown in the UI, retaining all tied configurations.
// This is a record table, not an inference of statistical significance.
export const recordScore = (rate: number) => Math.round(rate * 10) / 10;

export function winnerKey({ campaign: c, run: r }: Observation): string {
  return JSON.stringify([
    workloadKey(r.config),
    r.backend,
    r.mode,
    r.measurement_seconds,
    r.warmup_seconds,
    c.classification,
    r.context.source_hash,
    r.context.commit,
    r.context.dirty,
  ]);
}

export function collectWinners(observations: readonly Observation[]): WinnerCollection {
  const cases = new Map<string, ResultGroup[]>();
  let excludedGroups = 0;
  for (const group of groupObservations(observations)) {
    if (group.incompleteContext || group.rates.median === null) {
      excludedGroups++;
      continue;
    }
    const key = winnerKey(group.representative),
      groups = cases.get(key) ?? [];
    groups.push(group);
    cases.set(key, groups);
  }
  const boards: WinnerBoard[] = [];
  for (const [key, groups] of cases) {
    const frontends = new Map<string, FrontendRecord>();
    for (const group of groups) {
      const frontend = group.representative.run.frontend;
      const score = recordScore(group.rates.median!);
      const current = frontends.get(frontend);
      if (!current || score > current.score)
        frontends.set(frontend, { frontend, score, rank: 0, groups: [group] });
      else if (score === current.score) current.groups.push(group);
    }
    const records = [...frontends.values()].sort(
      (a, b) => b.score - a.score || a.frontend.localeCompare(b.frontend),
    );
    records.forEach((record, index) => {
      record.rank =
        index > 0 && record.score === records[index - 1].score
          ? records[index - 1].rank
          : index + 1;
      record.groups.sort(
        (a, b) =>
          a.representative.campaign.host.id.localeCompare(b.representative.campaign.host.id) ||
          a.key.localeCompare(b.key),
      );
    });
    boards.push({
      key,
      representative: groups[0].representative,
      records,
      evaluatedGroups: groups.length,
      hosts: new Set(groups.map((g) => g.representative.campaign.host.id)).size,
    });
  }
  return { boards: boards.sort((a, b) => a.key.localeCompare(b.key)), excludedGroups };
}
