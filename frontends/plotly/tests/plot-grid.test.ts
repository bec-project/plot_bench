import assert from 'node:assert/strict';
import test from 'node:test';
import {
  CURVE_COLORS, curveColor, gridColumns, gridRows, gridTemplateColumns, imageLayoutLabel, imageSubtitle,
  plotCounts, plotTitle, visiblePlotCount, waveformLayoutLabel, waveformSubtitle,
} from '../src/plot-grid';
import type { Configuration } from '../src/protocol';

const base: Configuration = {
  hz: 30, points: 10000, append_count: 1000, curves: 1, waveform_plots: 1, width: 512, height: 512, image_plots: 1,
  waveform_mode: 'replace', image_mode: 'scalar', view: 'both', seed: 42, generation: 0,
};

test('grid columns follow ceil(sqrt(n)) with rows filled row-major', () => {
  const expected: [number, number, number][] = [
    [0, 1, 1], [1, 1, 1], [2, 2, 1], [3, 2, 2], [4, 2, 2], [5, 3, 2], [6, 3, 2], [7, 3, 3],
    [9, 3, 3], [10, 4, 3], [16, 4, 4], [17, 5, 4], [32, 6, 6],
  ];
  for (const [n, columns, rows] of expected) {
    assert.equal(gridColumns(n), columns, `columns for ${n}`);
    assert.equal(gridRows(n), rows, `rows for ${n}`);
    assert.ok(columns * rows >= n);
  }
  assert.equal(gridTemplateColumns(5), 'repeat(3, minmax(0, 1fr))');
});

test('visible plot counts follow the view and the configured widget counts', () => {
  const config = { ...base, waveform_plots: 2, image_plots: 3 };
  assert.deepEqual(plotCounts(config), { waveform: 2, image: 3 });
  assert.deepEqual(plotCounts({ ...config, view: 'waveform' }), { waveform: 2, image: 0 });
  assert.deepEqual(plotCounts({ ...config, view: 'image' }), { waveform: 0, image: 3 });
  assert.equal(visiblePlotCount(config), 5);
  assert.equal(visiblePlotCount({ ...config, view: 'image' }), 3);
});

test('titles are plain for a single widget and numbered from one otherwise', () => {
  assert.equal(plotTitle('waveform', 0, 1), 'Waveform');
  assert.equal(plotTitle('image', 0, 1), 'Image');
  assert.equal(plotTitle('waveform', 0, 2), 'Waveform 1');
  assert.equal(plotTitle('waveform', 1, 2), 'Waveform 2');
  assert.equal(plotTitle('image', 2, 3), 'Image 3');
});

test('subtitles keep the size and mode and add the curve count only above one curve', () => {
  assert.equal(waveformSubtitle(base), '10,000 points · replace');
  assert.equal(waveformSubtitle({ ...base, curves: 3, waveform_mode: 'append' }), '10,000 points · append · 3 curves');
  assert.equal(imageSubtitle(base), '512 × 512 · scalar · fixed [0, 1]');
  assert.equal(imageSubtitle({ ...base, image_mode: 'rgb', width: 256, height: 128 }), '256 × 128 · RGB');
});

test('workload strip suffixes appear only when plots or curves exceed one', () => {
  assert.equal(waveformLayoutLabel(base), null);
  assert.equal(waveformLayoutLabel({ ...base, waveform_plots: 2, curves: 3 }), '2 plots × 3 curves');
  assert.equal(waveformLayoutLabel({ ...base, curves: 3 }), '1 plot × 3 curves');
  assert.equal(waveformLayoutLabel({ ...base, waveform_plots: 4 }), '4 plots × 1 curve');
  assert.equal(imageLayoutLabel(base), null);
  assert.equal(imageLayoutLabel({ ...base, image_plots: 3 }), '3 plots');
});

test('curve colours cycle through the shared eight-entry palette starting at the accent', () => {
  assert.equal(CURVE_COLORS.length, 8);
  assert.equal(curveColor(0), '#64dccc');
  assert.equal(curveColor(7), '#6ee7ff');
  assert.equal(curveColor(8), '#64dccc');
  assert.equal(curveColor(13), CURVE_COLORS[5]);
});
