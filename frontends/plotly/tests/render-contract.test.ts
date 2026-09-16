import assert from 'node:assert/strict';
import { test } from 'node:test';
import { dataSlot } from '../src/render-contract';
test('data-area-v1 common geometry vectors', () => {
  for (const [count, expected] of [[1,[932,340]], [2,[398,340]], [4,[398,92]], [6,[220,92]]] as const) {
    assert.deepEqual(dataSlot(1100,820,count), expected);
  }
});
