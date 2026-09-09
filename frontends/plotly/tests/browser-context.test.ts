import assert from 'node:assert/strict';
import test from 'node:test';
import { observeTimer } from '../src/browser-context';

test('clock observation is bounded and distinguishes repeated reads from positive increments', () => {
  let reads = 0;
  const result = observeTimer(() => Math.floor(reads++ / 4) / 10);
  assert.equal(reads, 2048);
  assert.ok(Math.abs(result.minimum_positive_observed_delta_ms! - 0.1) < 1e-10);
  assert.match(result.method, /not a guaranteed resolution/);
});

test('a clock that does not advance reports unknown increment instead of zero resolution', () => {
  assert.equal(observeTimer(() => 10).minimum_positive_observed_delta_ms, null);
});
