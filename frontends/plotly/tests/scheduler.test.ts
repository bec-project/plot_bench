import assert from 'node:assert/strict';
import test from 'node:test';
import { LatestFrameScheduler, replayTick, skippedBetween } from '../src/scheduler';

const turn = () => new Promise<void>((resolve) => setImmediate(resolve));

test('coalesces arrivals while an asynchronous drawing operation is pending', async () => {
  let release!: () => void;
  const blocked = new Promise<void>((resolve) => { release = resolve; });
  const received: number[] = [];
  let active = 0;
  const scheduler = new LatestFrameScheduler<number>(async (value) => {
    active += 1;
    assert.equal(active, 1, 'never overlap Plotly calls');
    received.push(value);
    if (value === 1) await blocked;
    active -= 1;
  }, (error) => { throw error; });
  scheduler.offer(1);
  await turn();
  for (let value = 2; value <= 100; value += 1) scheduler.offer(value);
  assert.deepEqual(received, [1]);
  release();
  await turn();
  assert.deepEqual(received, [1, 100]);
  await scheduler.close();
});

test('close waits for active work, drops mailbox and refuses future frames', async () => {
  let release!: () => void;
  const received: number[] = [];
  const scheduler = new LatestFrameScheduler<number>(async (value) => {
    received.push(value);
    await new Promise<void>((resolve) => { release = resolve; });
  }, (error) => { throw error; });
  scheduler.offer(1); await turn(); scheduler.offer(2);
  let closed = false;
  const closing = scheduler.close().then(() => { closed = true; });
  await turn(); assert.equal(closed, false);
  release(); await closing;
  scheduler.offer(3); await turn();
  assert.deepEqual(received, [1]);
});

test('drawing failures stop scheduling and surface exactly once', async () => {
  const errors: unknown[] = [];
  const scheduler = new LatestFrameScheduler<number>(async () => { throw new Error('GPU unavailable'); },
    (error) => errors.push(error));
  scheduler.offer(1); await turn(); scheduler.offer(2); await turn();
  assert.equal(errors.length, 1);
  assert.match(String(errors[0]), /GPU unavailable/);
  await scheduler.close();
});

test('skip counts reset across configuration generations', () => {
  assert.equal(skippedBetween(undefined, { seq: 999, generation: 0 }), 0);
  assert.equal(skippedBetween({ seq: 2, generation: 0 }, { seq: 7, generation: 0 }), 4);
  assert.equal(skippedBetween({ seq: 7, generation: 0 }, { seq: 0, generation: 1 }), 0);
});

test('replay advances according to elapsed time without a catch-up backlog', () => {
  assert.equal(replayTick(0, 120), 0);
  assert.equal(replayTick(500, 120), 60);
  assert.equal(replayTick(1025, 120), 123);
  assert.equal(replayTick(1000, 30), 30);
});
