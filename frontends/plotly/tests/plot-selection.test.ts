import assert from 'node:assert/strict';
import test from 'node:test';
import { nextPlotView, plotToggleState, type PlotKind, type PlotView } from '../src/plot-selection';

test('plot transitions cover both single workloads and restore the combined source', () => {
  const transitions: [PlotView, PlotKind, PlotView][] = [
    ['both', 'image', 'waveform'], ['both', 'waveform', 'image'],
    ['waveform', 'image', 'both'], ['image', 'waveform', 'both'],
  ];
  for (const [view, plot, expected] of transitions) assert.equal(nextPlotView(view, plot), expected);
});

test('the final enabled array cannot be removed, but the other can be enabled first', () => {
  for (const plot of ['waveform', 'image'] as const) {
    assert.equal(nextPlotView(plot, plot), plot);
    const active = plotToggleState(plot, plot, false, false, true);
    assert.equal(active.selected, true);
    assert.equal(active.disabled, true);
    assert.match(active.title, /At least one plot/);
    const other = plot === 'waveform' ? 'image' : 'waveform';
    assert.equal(plotToggleState(plot, other, false, false, true).disabled, false);
  }
});

test('pending requests, missing configuration, stopped demos and recorded runs lock controls', () => {
  for (const plot of ['waveform', 'image'] as const) {
    assert.equal(plotToggleState(undefined, plot, false, false, true).disabled, true);
    assert.equal(plotToggleState('both', plot, true, false, true).disabled, true);
    assert.equal(plotToggleState('both', plot, false, false, false).disabled, true);
    const recorded = plotToggleState('both', plot, false, true, true);
    assert.equal(recorded.disabled, true);
    assert.match(recorded.title, /recorded run/);
    assert.equal(plotToggleState('both', plot, false, false, true).disabled, false);
  }
});

test('pressed state comes from confirmed source view and recovers after request failure', () => {
  assert.equal(plotToggleState('image', 'waveform', false, false, true).selected, false);
  assert.equal(plotToggleState('waveform', 'image', false, false, true).selected, false);
  assert.equal(plotToggleState('both', 'waveform', true, false, true).selected, true);
  assert.equal(plotToggleState('both', 'waveform', false, false, true).disabled, false);
});
