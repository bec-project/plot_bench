// The overall ranking adds each frontend's competition rank across the seven section
// boards exactly as those boards display them. It combines placements, never rates,
// memory or CPU, and ranks only frontends with an eligible record in every section.
import { SECTIONS, type Section } from './baseline';
import type { Observation } from './model';
import {
  collectWinners,
  DEFAULT_CLOSE_RATE_PERCENT,
  type FrontendRecord,
  type WinnerBoard,
} from './winners';

export interface SectionPlacement {
  section: Section;
  rank: number;
  record: FrontendRecord;
  board: WinnerBoard;
}
export interface OverallEntry {
  frontend: string;
  rank: number;
  /** Sum of the section competition ranks; lower is better. */
  total: number;
  /** Sections where the frontend holds rank 1 (joint wins count). */
  wins: number;
  placements: SectionPlacement[];
  hosts: string[];
  revisions: number;
  sourceLimitedGroups: number;
  frontendLimitedGroups: number;
}
export interface IncompleteFrontend {
  frontend: string;
  present: Section[];
  missing: Section[];
}
export interface OverallRanking {
  entries: OverallEntry[];
  incomplete: IncompleteFrontend[];
  /** One board per section in suite order (sections without eligible records are absent). */
  boards: WinnerBoard[];
  excludedGroups: number;
  closeRatePercent: number;
}

export function collectOverall(
  observations: readonly Observation[],
  tolerance = DEFAULT_CLOSE_RATE_PERCENT,
): OverallRanking {
  const { boards, excludedGroups } = collectWinners(observations, tolerance);
  // Under the submission rule every section has exactly one board; if several
  // exist (only possible with unpublished data), the first in board order counts.
  const bySection = new Map<string, WinnerBoard>();
  for (const board of boards)
    if (board.section && !bySection.has(board.section.slug))
      bySection.set(board.section.slug, board);
  const sectionBoards = SECTIONS.flatMap((s) => {
    const b = bySection.get(s.slug);
    return b ? [b] : [];
  });
  const presence = new Map<string, Map<string, SectionPlacement>>();
  for (const board of sectionBoards)
    for (const record of board.records) {
      const placements = presence.get(record.frontend) ?? new Map<string, SectionPlacement>();
      placements.set(board.section!.slug, {
        section: board.section!,
        rank: record.rank,
        record,
        board,
      });
      presence.set(record.frontend, placements);
    }
  const entries: OverallEntry[] = [],
    incomplete: IncompleteFrontend[] = [];
  for (const [frontend, placementsBySlug] of presence) {
    const present = SECTIONS.filter((s) => placementsBySlug.has(s.slug));
    if (present.length !== SECTIONS.length) {
      incomplete.push({
        frontend,
        present,
        missing: SECTIONS.filter((s) => !placementsBySlug.has(s.slug)),
      });
      continue;
    }
    const placements = SECTIONS.map((s) => placementsBySlug.get(s.slug)!);
    const groups = placements.flatMap((p) => p.record.groups);
    entries.push({
      frontend,
      rank: 0,
      total: placements.reduce((sum, p) => sum + p.rank, 0),
      wins: placements.filter((p) => p.rank === 1).length,
      placements,
      hosts: [...new Set(groups.map((g) => g.representative.campaign.host.id))].sort(),
      revisions: new Set(groups.map((g) => g.representative.run.context.commit)).size,
      sourceLimitedGroups: groups.filter((g) => g.sourceLimited > 0).length,
      frontendLimitedGroups: groups.filter((g) => g.frontendLimited > 0).length,
    });
  }
  entries.sort(
    (a, b) => a.total - b.total || b.wins - a.wins || a.frontend.localeCompare(b.frontend),
  );
  entries.forEach((entry, index) => {
    const previous = entries[index - 1];
    entry.rank =
      previous && previous.total === entry.total && previous.wins === entry.wins
        ? previous.rank
        : index + 1;
  });
  incomplete.sort(
    (a, b) => b.present.length - a.present.length || a.frontend.localeCompare(b.frontend),
  );
  return {
    entries,
    incomplete,
    boards: sectionBoards,
    excludedGroups,
    closeRatePercent: tolerance,
  };
}
