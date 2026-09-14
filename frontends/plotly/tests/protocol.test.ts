import assert from 'node:assert/strict';
import test from 'node:test';
import { acceptStreamPacket, parseConfiguration, parseFrame, parseReplay } from '../src/protocol';
import { LatestFrameScheduler } from '../src/scheduler';

// Two waveform plots with two curves of three points and two 1×2 RGB image plots.
const config = {
  hz: 120, points: 3, append_count: 1, curves: 2, waveform_plots: 2, width: 2, height: 1, image_plots: 2,
  waveform_mode: 'append', image_mode: 'rgb', view: 'both', seed: 42, generation: 2,
};
const WAVEFORM = [-0.5, 0.25, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const IMAGE = [255, 0, 0, 0, 128, 255, 1, 2, 3, 4, 5, 6];

function packet(change: (header: Record<string, unknown>) => void = () => {}): ArrayBuffer {
  const header: Record<string, unknown> = {
    version: 2, seq: 7, generation: 2, emitted_at_ms: 12345, config,
    arrays: [
      { name: 'waveform', dtype: 'float32', shape: [2, 2, 3], offset: 0, nbytes: 48 },
      { name: 'image', dtype: 'uint8', shape: [2, 1, 2, 3], offset: 48, nbytes: 12 },
    ],
  };
  change(header);
  const encoded = new TextEncoder().encode(JSON.stringify(header));
  const start = Math.ceil((encoded.length + 4) / 4) * 4;
  const buffer = new ArrayBuffer(start + 60);
  const view = new DataView(buffer);
  view.setUint32(0, encoded.length, true);
  new Uint8Array(buffer, 4, encoded.length).set(encoded);
  WAVEFORM.forEach((value, index) => view.setFloat32(start + 4 * index, value, true));
  new Uint8Array(buffer, start + 48).set(IMAGE);
  return buffer;
}

test('reads aligned little-endian multi-plot waveform and interleaved RGB without copying', () => {
  const buffer = packet();
  const frame = parseFrame(buffer);
  assert.equal(frame.seq, 7);
  assert.equal(frame.config.waveform_mode, 'append');
  assert.equal(frame.config.curves, 2);
  assert.equal(frame.config.waveform_plots, 2);
  assert.equal(frame.config.image_plots, 2);
  assert.deepEqual([...frame.waveform!], WAVEFORM);
  assert.deepEqual([...frame.image!], IMAGE);
  assert.equal(frame.waveform!.buffer, buffer);
  assert.equal(frame.image!.buffer, buffer);
});

test('plot-major row-major slices address every waveform plot, curve and image plot', () => {
  const frame = parseFrame(packet());
  const { curves, points, width, height } = frame.config;
  const curve = (plot: number, index: number) =>
    [...frame.waveform!.subarray((plot * curves + index) * points, (plot * curves + index + 1) * points)];
  assert.deepEqual(curve(0, 0), [-0.5, 0.25, 1]);
  assert.deepEqual(curve(0, 1), [2, 3, 4]);
  assert.deepEqual(curve(1, 0), [5, 6, 7]);
  assert.deepEqual(curve(1, 1), [8, 9, 10]);
  const pixels = width * height * 3;
  assert.deepEqual([...frame.image!.subarray(0, pixels)], [255, 0, 0, 0, 128, 255]);
  assert.deepEqual([...frame.image!.subarray(pixels, 2 * pixels)], [1, 2, 3, 4, 5, 6]);
});

test('scalar images are three-dimensional float32 arrays with one block per image plot', () => {
  const scalar = { ...config, image_mode: 'scalar', view: 'image' };
  const frame = parseFrame(packet((header) => {
    header.config = scalar;
    header.arrays = [{ name: 'image', dtype: 'float32', shape: [2, 1, 2], offset: 0, nbytes: 16 }];
  }));
  assert.equal(frame.waveform, undefined);
  assert.ok(frame.image instanceof Float32Array);
  assert.deepEqual([...frame.image!], [-0.5, 0.25, 1, 2]);
  assert.throws(() => parseFrame(packet((header) => {
    header.config = scalar;
    header.arrays = [{ name: 'image', dtype: 'float32', shape: [1, 2, 2], offset: 0, nbytes: 16 }];
  })), /image shape/);
});

test('rejects truncated headers and array payloads', () => {
  assert.throws(() => parseFrame(new ArrayBuffer(3)), /prefix/);
  assert.throws(() => parseFrame(packet().slice(0, 6)), /header/);
  assert.throws(() => parseFrame(packet().slice(0, -1)), /payload/);
});

test('rejects protocol v1 and other versions, mismatched generations, and malformed descriptors', () => {
  for (const version of [1, 3, '2', undefined]) {
    assert.throws(() => parseFrame(packet((header) => { header.version = version; })), /version/);
  }
  assert.throws(() => parseFrame(packet((header) => { header.generation = 3; })), /generation/);
  // Flattened, transposed, v1-style and count-mismatched waveform shapes are all wrong.
  for (const shape of [[12], [2, 3, 2], [3], [1, 2, 3], [2, 2, 3, 1], [4, 3]]) {
    assert.throws(() => parseFrame(packet((header) => {
      (header.arrays as Record<string, unknown>[])[0].shape = shape;
    })), /waveform shape/);
  }
  assert.throws(() => parseFrame(packet((header) => {
    (header.arrays as Record<string, unknown>[])[1].shape = [1, 2, 3];
  })), /image shape/);
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
  assert.equal(parseConfiguration({ ...config, curves: 64, waveform_plots: 16, image_plots: 16 }).curves, 64);
  for (const curves of [0, 65, 1.5, true, '2', undefined]) {
    assert.throws(() => parseConfiguration({ ...config, curves }), /curves/);
  }
  assert.throws(() => parseConfiguration({ ...config, curves: 65 }), /curves must be between 1 and 64/);
  for (const key of ['waveform_plots', 'image_plots'] as const) {
    for (const value of [0, 17, -1, 2.5, false, undefined]) {
      assert.throws(() => parseConfiguration({ ...config, [key]: value }), new RegExp(key));
    }
    assert.throws(() => parseConfiguration({ ...config, [key]: 17 }), new RegExp(`${key} must be between 1 and 16`));
  }
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
