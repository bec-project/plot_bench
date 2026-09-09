import assert from 'node:assert/strict';
import test from 'node:test';
import { metricHints } from '../src/metric-hints';

test('metric targets follow source periods at integer and fractional rates', () => {
  assert.deepEqual(metricHints(120, false), {
    submitted: '(target 120/s)', update: '(budget ≤8.33 ms)',
    skipped: '(target 0)', age: '(goal <8.33 ms)',
  });
  assert.equal(metricHints(30, false).update, '(budget ≤33.33 ms)');
  assert.equal(metricHints(29.5, false).submitted, '(target 29.5/s)');
});

test('replay age is inapplicable and unknown rates never produce infinite budgets', () => {
  assert.equal(metricHints(120, true).age, '(N/A in replay)');
  for (const hz of [undefined, 0, NaN, Infinity]) {
    assert.equal(metricHints(hz, false).submitted, '(target —/s)');
    assert.equal(metricHints(hz, false).update, '(budget ≤— ms)');
  }
});
