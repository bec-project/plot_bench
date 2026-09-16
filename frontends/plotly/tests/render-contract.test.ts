import assert from 'node:assert/strict';
import { test } from 'node:test';
import { dataSlot } from '../src/render-contract';
test('data-area-v2 common geometry vectors', () => {
  for (const [count, expected] of [[1,[952,480]], [2,[418,480]], [4,[418,172]], [6,[240,172]]] as const) {
    assert.deepEqual(dataSlot(1100,820,count), expected);
  }
});

test('compact image slots preserve room for native axes', () => {
  for (const [count, expected] of [[1,[956,500]], [2,[502,584]], [4,[502,276]], [6,[324,276]]] as const) {
    assert.deepEqual(dataSlot(1100,820,count,true), expected);
  }
});
