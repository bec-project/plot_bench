import type { Configuration } from './protocol';
import type { PlotKind } from './plot-selection';

/** Shared curve palette (protocol v2): curve `c` of every waveform plot uses CURVE_COLORS[c % 8]. */
export const CURVE_COLORS: readonly string[] = [
  '#64dccc', '#f5c76e', '#7aa6ff', '#ff9d7a', '#c39bff', '#9be564', '#ff7ab8', '#6ee7ff',
];

export function curveColor(index: number): string {
  return CURVE_COLORS[index % CURVE_COLORS.length];
}

export interface PlotCounts { waveform: number; image: number }

type LayoutConfig = Pick<Configuration, 'view' | 'waveform_plots' | 'image_plots'>;

/** Visible widget counts per kind; zero when `view` hides the kind. */
export function plotCounts(config: LayoutConfig): PlotCounts {
  return {
    waveform: config.view === 'image' ? 0 : config.waveform_plots,
    image: config.view === 'waveform' ? 0 : config.image_plots,
  };
}

export function visiblePlotCount(config: LayoutConfig): number {
  const counts = plotCounts(config);
  return counts.waveform + counts.image;
}

/** Shared layout rule: columns = ceil(sqrt(n)), rows = ceil(n / columns), filled row-major. */
export function gridColumns(n: number): number {
  return n <= 1 ? 1 : Math.ceil(Math.sqrt(n));
}

export function gridRows(n: number): number {
  return n <= 1 ? 1 : Math.ceil(n / gridColumns(n));
}

export function gridTemplateColumns(n: number): string {
  return `repeat(${gridColumns(n)}, minmax(0, 1fr))`;
}

/** `Waveform` / `Image` for a single widget of that kind, otherwise numbered from 1. */
export function plotTitle(kind: PlotKind, index: number, count: number): string {
  const base = kind === 'waveform' ? 'Waveform' : 'Image';
  return count === 1 ? base : `${base} ${index + 1}`;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

export function waveformSubtitle(config: Pick<Configuration, 'points' | 'waveform_mode' | 'curves'>): string {
  const base = `${config.points.toLocaleString()} points · ${config.waveform_mode}`;
  return config.curves > 1 ? `${base} · ${plural(config.curves, 'curve')}` : base;
}

export function imageSubtitle(config: Pick<Configuration, 'width' | 'height' | 'image_mode'>): string {
  return `${config.width} × ${config.height} · ${config.image_mode === 'rgb' ? 'RGB' : 'scalar · fixed [0, 1]'}`;
}

/** Workload-strip suffix such as `2 plots × 3 curves`; null when both counts are 1. */
export function waveformLayoutLabel(config: Pick<Configuration, 'waveform_plots' | 'curves'>): string | null {
  if (config.waveform_plots === 1 && config.curves === 1) return null;
  return `${plural(config.waveform_plots, 'plot')} × ${plural(config.curves, 'curve')}`;
}

/** Workload-strip suffix such as `3 plots`; null for a single image plot. */
export function imageLayoutLabel(config: Pick<Configuration, 'image_plots'>): string | null {
  return config.image_plots > 1 ? plural(config.image_plots, 'plot') : null;
}
