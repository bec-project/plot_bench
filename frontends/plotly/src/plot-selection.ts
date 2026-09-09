import type { Configuration } from './protocol';

export type PlotKind = 'waveform' | 'image';
export type PlotView = Configuration['view'];

/** Toggle one channel while preserving at least one source array. */
export function nextPlotView(view: PlotView, plot: PlotKind): PlotView {
  if (view === 'both') return plot === 'waveform' ? 'image' : 'waveform';
  return view === plot ? view : 'both';
}

export function plotToggleState(view: PlotView | undefined, plot: PlotKind,
  pending: boolean, recorded: boolean, running: boolean) {
  const label = plot === 'waveform' ? '1D waveform' : '2D image';
  const selected = view === 'both' || view === plot;
  let reason: string | null = null;
  if (recorded) reason = 'Plot selection is locked during a recorded run.';
  else if (!view) reason = 'Waiting for source configuration.';
  else if (pending) reason = 'Updating the shared source.';
  else if (!running) reason = 'Restart the demo to change plots.';
  else if (view === plot) reason = 'At least one plot must remain enabled. Enable the other plot first.';
  return { selected, disabled: reason !== null, label, title: reason ? `${label} — ${reason}` : label };
}
