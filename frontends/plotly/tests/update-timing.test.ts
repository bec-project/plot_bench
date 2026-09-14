import assert from 'node:assert/strict';
import test from 'node:test';
import { submitUpdates } from '../src/update-timing';

test('completion elapsed includes deferred work and waits for every active plot', async (context) => {
  let clock = 15;
  context.mock.method(performance, 'now', () => clock);
  let finishWaveform!: () => void;
  let finishImage!: () => void;
  const waveform = new Promise<void>((resolve) => { finishWaveform = resolve; });
  const image = new Promise<void>((resolve) => { finishImage = resolve; });
  let returned = false;
  const result = submitUpdates(10, 12, () => [waveform, image]).then((value) => {
    returned = true;
    return value;
  });
  clock = 20;
  finishWaveform();
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.equal(returned, false);
  clock = 35;
  finishImage();
  assert.deepEqual(await result, {
    update_ms: 5, conversion_ms: 2, draw_ms: 3, update_complete_ms: 25,
  });
});

test('a failed deferred plot update produces no successful timing sample', async () => {
  await assert.rejects(submitUpdates(0, 0, () => [
    Promise.resolve(), Promise.reject(new Error('image rasterization failed')),
  ]), /image rasterization failed/);
});

test('a synchronous plotting exception also rejects the update', async () => {
  await assert.rejects(submitUpdates(0, 0, () => {
    throw new Error('invalid trace');
  }), /invalid trace/);
});
