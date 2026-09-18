import { groupObservations, summarizeRates, type ResultGroup } from './aggregation';
import { workloadKey, type Observation } from './model';
import { BASELINE_VERSION, sectionOf, type Section } from './baseline';

export interface FrontendRecord {
  frontend: string;
  score: number;
  minimumScore: number;
  memoryMib: number;
  cpuPercent: number;
  rateBand: number;
  rank: number;
  groups: WinnerGroup[];
  /** One actual tied configuration supplies the headline metrics and radar. */
  representativeGroup: WinnerGroup;
  profile: PerformanceProfile;
}
export interface PerformanceProfile {
  /** Normalized axes in [0, 1], all outward = better. */
  throughput: number;
  rss: number;
  cpu: number;
  /** Fraction of the outer triangle, compared only within one throughput band. */
  area: number;
}
export interface ResourceUsage {
  memoryMib: number | null;
  cpuPercent: number | null;
}
export interface WinnerGroup extends ResultGroup {
  resources: { memoryMib: number; cpuPercent: number };
}
export interface WinnerBoard {
  key: string;
  /** The baseline section this board ranks, or null for a workload outside the suite. */
  section: Section | null;
  representative: Observation;
  records: FrontendRecord[];
  evaluatedGroups: number;
  hosts: number;
  /** Distinct source commits behind the board's groups; revisions share a board but never merge. */
  revisions: number;
  closeRatePercent: number;
}
export interface WinnerCollection {
  boards: WinnerBoard[];
  excludedGroups: number;
  /** Excluded groups per section slug (or workload key outside the suite). */
  excludedBySection: Record<string, number>;
}

// Display precision only; area ranking uses unrounded rates and resource medians.
export const recordScore = (rate: number) => Math.round(rate * 10) / 10;
export const CLOSE_RATE_PERCENTAGES = [0, 1, 2, 5] as const;
export const DEFAULT_CLOSE_RATE_PERCENT = 2;
export function closeRatePercent(value: string | null): number {
  return value !== null && CLOSE_RATE_PERCENTAGES.some((p) => String(p) === value)
    ? Number(value)
    : DEFAULT_CLOSE_RATE_PERCENT;
}

export function resourceUsage(group: ResultGroup): ResourceUsage {
  function metric(key: 'rss_peak_mib' | 'cpu_mean_percent'): number | null {
    const medians: number[] = [];
    for (const campaign of group.campaigns) {
      const valid = campaign.observations.filter(
        ({ run: r }) => r.status === 'ok' && r.samples > 0 && r.metrics.submitted_hz !== null,
      );
      if (!valid.length) continue;
      const values = valid.map((o) => o.run.metrics[key]);
      // Compare the same repetitions as throughput. Partial coverage cannot
      // produce an artificially favorable resource score.
      if (values.some((v) => v === null || !Number.isFinite(v) || v <= 0)) return null;
      medians.push(summarizeRates(values as number[]).median!);
    }
    return summarizeRates(medians).median;
  }
  return { memoryMib: metric('rss_peak_mib'), cpuPercent: metric('cpu_mean_percent') };
}

// A transitive tie key removes floating-point noise without rounding the input
// measurements to their display precision. One unit is 1e-12 of the outer area.
const areaKey = (profile: PerformanceProfile) => Math.round(profile.area * 1e12);
function performanceProfile(
  group: WinnerGroup,
  minRss: number,
  minCpu: number,
): PerformanceProfile {
  const target = group.representative.run.config.hz;
  const throughput = Math.min(1, Math.max(0, group.rates.median! / target));
  const rss = minRss / group.resources.memoryMib;
  const cpu = minCpu / group.resources.cpuPercent;
  return { throughput, rss, cpu, area: (throughput * rss + rss * cpu + cpu * throughput) / 3 };
}

// One board per baseline section. Source revisions and display contexts stay separate
// groups through compatibilityKey and are shown on every record; they do not fork boards.
export function winnerKey({ campaign: c, run: r }: Observation): string {
  return JSON.stringify([
    BASELINE_VERSION,
    sectionOf(r.config)?.slug ?? workloadKey(r.config),
    r.backend,
    r.mode,
    r.measurement_seconds,
    r.warmup_seconds,
    c.classification,
  ]);
}

export function collectWinners(
  observations: readonly Observation[],
  tolerance = DEFAULT_CLOSE_RATE_PERCENT,
): WinnerCollection {
  if (!CLOSE_RATE_PERCENTAGES.some((p) => p === tolerance))
    throw new Error('Unsupported close-rate threshold');
  const cases = new Map<string, WinnerGroup[]>();
  let excludedGroups = 0;
  const excludedBySection: Record<string, number> = {};
  for (const group of groupObservations(observations)) {
    const resources = resourceUsage(group);
    // Unknown display scale leaves the rasterised area of image sections unknowable.
    if (
      group.incompleteContext ||
      group.rates.median === null ||
      group.representative.run.context.pixel_ratio === null ||
      resources.memoryMib === null ||
      resources.cpuPercent === null
    ) {
      excludedGroups++;
      const config = group.representative.run.config;
      const slug = sectionOf(config)?.slug ?? workloadKey(config);
      excludedBySection[slug] = (excludedBySection[slug] ?? 0) + 1;
      continue;
    }
    const key = winnerKey(group.representative),
      groups = cases.get(key) ?? [];
    groups.push({
      ...group,
      resources: { memoryMib: resources.memoryMib, cpuPercent: resources.cpuPercent },
    });
    cases.set(key, groups);
  }
  const boards: WinnerBoard[] = [];
  for (const [key, groups] of cases) {
    const frontends = new Map<string, FrontendRecord>();
    // Anchor each band to its fastest remaining configuration. Pairwise "close"
    // comparators are non-transitive (100 ~ 98 ~ 96) and order-dependent.
    const ordered = [...groups].sort(
      (a, b) => b.rates.median! - a.rates.median! || a.key.localeCompare(b.key),
    );
    let cursor = 0,
      rateBand = 0;
    while (cursor < ordered.length) {
      const best = ordered[cursor].rates.median!,
        threshold = best * (1 - tolerance / 100);
      const band: WinnerGroup[] = [];
      while (cursor < ordered.length && ordered[cursor].rates.median! >= threshold)
        band.push(ordered[cursor++]);
      // Scale every eligible configuration before choosing one per frontend;
      // otherwise a memory-first choice could hide its better balanced record.
      const minRss = Math.min(...band.map((g) => g.resources.memoryMib));
      const minCpu = Math.min(...band.map((g) => g.resources.cpuPercent));
      const scored = band.map((group) => ({
        group,
        profile: performanceProfile(group, minRss, minCpu),
      }));
      scored.sort(
        (a, b) =>
          areaKey(b.profile) - areaKey(a.profile) ||
          b.group.rates.median! - a.group.rates.median! ||
          a.group.key.localeCompare(b.group.key),
      );
      for (const { group, profile } of scored) {
        const frontend = group.representative.run.frontend;
        const score = recordScore(group.rates.median!);
        const current = frontends.get(frontend);
        if (!current)
          frontends.set(frontend, {
            frontend,
            score,
            minimumScore: score,
            rank: 0,
            rateBand,
            groups: [group],
            representativeGroup: group,
            profile,
            memoryMib: group.resources.memoryMib,
            cpuPercent: group.resources.cpuPercent,
          });
        else if (current.rateBand === rateBand && areaKey(current.profile) === areaKey(profile)) {
          current.groups.push(group);
          current.minimumScore = Math.min(current.minimumScore, score);
        }
      }
      rateBand++;
    }
    const records = [...frontends.values()].sort(
      (a, b) =>
        a.rateBand - b.rateBand ||
        areaKey(b.profile) - areaKey(a.profile) ||
        a.frontend.localeCompare(b.frontend),
    );
    records.forEach((record, index) => {
      record.rank =
        index > 0 &&
        record.rateBand === records[index - 1].rateBand &&
        areaKey(record.profile) === areaKey(records[index - 1].profile)
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
      section: sectionOf(groups[0].representative.run.config),
      representative: groups[0].representative,
      records,
      evaluatedGroups: groups.length,
      hosts: new Set(groups.map((g) => g.representative.campaign.host.id)).size,
      revisions: new Set(groups.map((g) => g.representative.run.context.commit)).size,
      closeRatePercent: tolerance,
    });
  }
  return {
    boards: boards.sort(
      (a, b) =>
        (a.section?.index ?? Infinity) - (b.section?.index ?? Infinity) ||
        a.key.localeCompare(b.key),
    ),
    excludedGroups,
    excludedBySection,
  };
}
