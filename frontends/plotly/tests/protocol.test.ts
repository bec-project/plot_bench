import assert from 'node:assert/strict';
import test from 'node:test';
import { acceptStreamPacket, parseConfiguration, parseFrame, parseReplay } from '../src/protocol';
import { LatestFrameScheduler } from '../src/scheduler';

const config = {
  hz: 120, points: 3, append_count: 1, width: 2, height: 1,
  waveform_mode: 'append', image_mode: 'rgb', view: 'both', seed: 42, generation: 2,
};

function packet(change: (header: Record<string, unknown>) => void = () => {}): ArrayBuffer {
  const header: Record<string, unknown> = {
    version: 1, seq: 7, generation: 2, emitted_at_ms: 12345, config,
    arrays: [
      { name: 'waveform', dtype: 'float32', shape: [3], offset: 0, nbytes: 12 },
      { name: 'image', dtype: 'uint8', shape: [1, 2, 3], offset: 12, nbytes: 6 },
    ],
  };
  change(header);
  const encoded = new TextEncoder().encode(JSON.stringify(header));
  const start = Math.ceil((encoded.length + 4) / 4) * 4;
  const buffer = new ArrayBuffer(start + 18);
  const view = new DataView(buffer);
  view.setUint32(0, encoded.length, true);
  new Uint8Array(buffer, 4, encoded.length).set(encoded);
  [-0.5, 0.25, 1].forEach((value, index) => view.setFloat32(start + 4 * index, value, true));
  new Uint8Array(buffer, start + 12).set([255, 0, 0, 0, 128, 255]);
  return buffer;
}

test('reads aligned little-endian waveform and interleaved RGB without copying', () => {
  const buffer = packet();
  const frame = parseFrame(buffer);
  assert.equal(frame.seq, 7);
  assert.equal(frame.config.waveform_mode, 'append');
  assert.deepEqual([...frame.waveform!], [-0.5, 0.25, 1]);
  assert.deepEqual([...frame.image!], [255, 0, 0, 0, 128, 255]);
  assert.equal(frame.waveform!.buffer, buffer);
  assert.equal(frame.image!.buffer, buffer);
});

test('rejects truncated headers and array payloads', () => {
  assert.throws(() => parseFrame(new ArrayBuffer(3)), /prefix/);
  assert.throws(() => parseFrame(packet().slice(0, 6)), /header/);
  assert.throws(() => parseFrame(packet().slice(0, -1)), /payload/);
});

test('rejects unsupported versions, mismatched generations, and malformed descriptors', () => {
  assert.throws(() => parseFrame(packet((header) => { header.version = 2; })), /version/);
  assert.throws(() => parseFrame(packet((header) => { header.generation = 3; })), /generation/);
  assert.throws(() => parseFrame(packet((header) => {
    (header.arrays as Record<string, unknown>[])[0].shape = [2];
  })), /shape/);
  assert.throws(() => parseFrame(packet((header) => {
    (header.arrays as Record<string, unknown>[])[0].dtype = 'float64';
  })), /dtype/);
  assert.throws(() => parseFrame(packet((header) => {
    (header.arrays as Record<string, unknown>[])[1].offset = 3;
  })), /Overlapping/);
});

test('required view payloads cannot silently disappear', () => {
  assert.throws(() => parseFrame(packet((header) => { header.arrays = []; })), /Missing waveform/);
});

test('validates control limits and append window', () => {
  assert.equal(parseConfiguration(config).hz, 120);
  for (const hz of [0, -1, 121, Infinity]) assert.throws(() => parseConfiguration({ ...config, hz }));
  assert.throws(() => parseConfiguration({ ...config, append_count: 4 }), /exceeds/);
  assert.throws(() => parseConfiguration({ ...config, image_mode: 'rgba' }), /image_mode/);
});

test('reads bounded replay container and rejects missing or trailing data', () => {
  const frame = packet();
  const buffer = new ArrayBuffer(8 + frame.byteLength);
  const view = new DataView(buffer);
  view.setUint32(0, 1, true);
  view.setUint32(4, frame.byteLength, true);
  new Uint8Array(buffer, 8).set(new Uint8Array(frame));
  assert.equal(parseReplay(buffer)[0].seq, 7);
  assert.throws(() => parseReplay(buffer.slice(0, -1)), /Truncated/);
  const trailing = new Uint8Array(buffer.byteLength + 1);
  trailing.set(new Uint8Array(buffer));
  assert.throws(() => parseReplay(trailing.buffer), /Trailing/);
  assert.throws(() => parseReplay(new ArrayBuffer(4)), /frame count/);
});

test('returns packet credit after mailbox offer and before asynchronous plotting', async () => {
  const events: string[] = [];
  const scheduler = new LatestFrameScheduler(async () => { events.push('plot'); },
    (error) => { throw error; });
  acceptStreamPacket(packet(), (frame) => { events.push('offer'); scheduler.offer(frame); },
    (message) => {
      events.push('ack');
      assert.deepEqual(JSON.parse(message), { ack: 7, generation: 2 });
    });
  assert.deepEqual(events, ['offer', 'ack']);
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.deepEqual(events, ['offer', 'ack', 'plot']);
  await scheduler.close();
});

test('malformed packets neither enter the mailbox nor return misleading credit', () => {
  let offered = false;
  let acknowledged = false;
  assert.throws(() => acceptStreamPacket(packet().slice(0, -1), () => { offered = true; },
    () => { acknowledged = true; }), /payload/);
  assert.equal(offered, false);
  assert.equal(acknowledged, false);
});
