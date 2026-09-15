// Display order of the Results page. It changes what is shown first, never what
// is grouped or measured; the choice persists in the URL as `sort`.
import type { ResultGroup } from './aggregation';
import type { Observation } from './model';

export const GROUP_ORDERS = [
  ['rate', 'Median updates/s'],
  ['recent', 'Latest acquisition'],
  ['frontend', 'Frontend name'],
] as const;
export type GroupOrder = (typeof GROUP_ORDERS)[number][0];
export const ORDER_NOTES: Record<GroupOrder, string> = {
  rate: 'highest median updates/s first; groups and runs without a valid rate last',
  recent: 'latest acquisition first',
  frontend: 'by frontend name, then highest median updates/s',
};

export function groupOrder(value: string | null | undefined): GroupOrder {
  return GROUP_ORDERS.some(([key]) => key === value) ? (value as GroupOrder) : 'rate';
}

// Higher rates first; a missing rate sorts after every recorded one.
function byRate(a: number | null, b: number | null): number {
  if (a === b) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return b - a;
}

export function compareGroups(order: GroupOrder): (a: ResultGroup, b: ResultGroup) => number {
  return (a, b) => {
    const rate = byRate(a.rates.median, b.rates.median),
      recent = Date.parse(b.last) - Date.parse(a.last),
      name = a.representative.run.frontend.localeCompare(b.representative.run.frontend),
      key = a.key.localeCompare(b.key);
    switch (order) {
      case 'recent':
        return recent || rate || key;
      case 'frontend':
        return name || rate || recent || key;
      default:
        return rate || recent || key;
    }
  };
}

// The same validity gate as the group medians: a run that was downgraded after
// measuring keeps a recorded rate but never ranks as a valid one.
const validRate = ({ run: r }: Observation): number | null =>
  r.status === 'ok' && r.samples > 0 ? r.metrics.submitted_hz : null;

export function compareRuns(order: GroupOrder): (a: Observation, b: Observation) => number {
  return (a, b) => {
    const rate = byRate(validRate(a), validRate(b)),
      recent =
        Date.parse(b.campaign.recorded_at) - Date.parse(a.campaign.recorded_at) ||
        a.campaign.id.localeCompare(b.campaign.id),
      name = a.run.frontend.localeCompare(b.run.frontend),
      repetition = a.run.repetition - b.run.repetition;
    switch (order) {
      case 'recent':
        return recent || name || repetition;
      case 'frontend':
        return name || recent || repetition;
      default:
        return rate || name || recent || repetition;
    }
  };
}
