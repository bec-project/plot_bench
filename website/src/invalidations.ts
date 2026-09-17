import type { Observation } from './model';

/**
 * Results that stay in the raw campaign files but are excluded from every
 * aggregation and ranking because the frontend's rendering implementation
 * changed and the earlier numbers are no longer comparable. Each rule marks the
 * superseded runs of one frontend by the `context.renderer` they were recorded
 * with, so re-measured runs on the new implementation are unaffected.
 */
export interface Invalidation {
  frontend: string;
  /** A run is superseded when its `context.renderer` contains this text. */
  supersededRenderer: string;
  reason: string;
}

export const INVALIDATIONS: readonly Invalidation[] = [
  {
    frontend: 'plotly',
    supersededRenderer: 'heatmap/image (Plotly raster traces)',
    reason:
      'Plotly image rendering was optimized to precolored image.source PNG traces; ' +
      'the earlier heatmap/image results are not comparable and are superseded.',
  },
];

/** Whether an observation belongs to a superseded implementation of its frontend. */
export function isInvalidated({ run }: Observation): boolean {
  return INVALIDATIONS.some(
    (rule) =>
      rule.frontend === run.frontend &&
      (run.context.renderer ?? '').includes(rule.supersededRenderer),
  );
}

/**
 * Every observation except those a frontend's implementation change has
 * superseded. Applied once to the whole catalogue before grouping, so no page
 * ranks or averages an invalidated run while the raw files stay intact.
 */
export function validObservations(all: readonly Observation[]): Observation[] {
  return all.filter((o) => !isInvalidated(o));
}
