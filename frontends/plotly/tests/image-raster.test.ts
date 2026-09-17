import assert from 'node:assert/strict';
import test from 'node:test';
import { createPalette, ImageRasterCache } from '../src/image-raster';

const colors = Array.from({ length: 256 }, (_, index) => [index, (index * 37 + 19) % 256, 255 - index]);
const rgba = (index: number) => [...colors[index], 255];

function fakeCanvas() {
  const created: ImageData[] = [];
  const presented: { image: ImageData; bytes: number[] }[] = [];
  const encoded: string[] = [];
  let contexts = 0;
  const context = {
    createImageData: (width: number, height: number): ImageData => {
      const image = { width, height, data: new Uint8ClampedArray(width * height * 4) } as ImageData;
      created.push(image);
      return image;
    },
    putImageData: (image: ImageData, x: number, y: number) => {
      assert.equal(x, 0);
      assert.equal(y, 0);
      presented.push({ image, bytes: Array.from(image.data) });
    },
  };
  const canvas = {
    width: 0,
    height: 0,
    getContext: (kind: string) => {
      assert.equal(kind, '2d');
      contexts += 1;
      return context;
    },
    toDataURL: (mime: string) => {
      assert.equal(mime, 'image/png');
      // Serialize the actual RGBA content as a deterministic stand-in for PNG.
      const result = `data:image/png;base64,${Buffer.from(presented.at(-1)!.bytes).toString('base64')}`;
      encoded.push(result);
      return result;
    },
  };
  return { canvas, context, created, presented, encoded, contexts: () => contexts };
}

test('palette packing preserves all RGBA bytes without assuming Uint32 byte order', () => {
  const packed = createPalette(colors);
  assert.equal(packed.length, 256);
  assert.deepEqual(Array.from(new Uint8Array(packed.buffer)), colors.flatMap((color) => [...color, 255]));
  assert.throws(() => createPalette(colors.slice(1)), /256 RGB entries/);
  assert.throws(() => createPalette(colors.map((color, index) => index === 7 ? [0, 256, 1] : color)), /256 RGB entries/);
  assert.throws(() => createPalette(colors.map((color, index) => index === 7 ? [0, NaN, 1] : color)), /256 RGB entries/);
});

test('scalar palette lookup matches floor, clamping and NaN conventions for every pixel', () => {
  const fake = fakeCanvas();
  const cache = new ImageRasterCache(createPalette(colors), () => fake.canvas as unknown as HTMLCanvasElement);
  const values = new Float32Array([-Infinity, -1, -0, NaN, 0, 0.5, 1, Infinity, 0.25, 0.75, 0.0039, 0.00393]);
  cache.encode(values, 4, 3, 'scalar', 0);
  const expected = [0, 0, 0, 0, 0, 127, 255, 255, 63, 191, 0, 1];
  assert.deepEqual(fake.presented[0].bytes, expected.flatMap(rgba));
  assert.equal(fake.encoded.length, 1);
});

test('scalar and RGB use the complete requested plot-major source block', () => {
  const fake = fakeCanvas();
  const cache = new ImageRasterCache(createPalette(colors), () => fake.canvas as unknown as HTMLCanvasElement);
  cache.encode(new Float32Array([0, 0, 0, 0, 0.25, 0.5, 0.75, 1]), 2, 2, 'scalar', 1);
  assert.deepEqual(fake.presented[0].bytes, [63, 127, 191, 255].flatMap(rgba));
  const rgb = new Uint8Array([
    0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3,
    4, 19, 233, 55, 67, 89, 101, 123, 145, 201, 230, 255,
  ]);
  cache.encode(rgb, 2, 2, 'rgb', 1);
  assert.deepEqual(fake.presented[1].bytes, [
    4, 19, 233, 255, 55, 67, 89, 255, 101, 123, 145, 255, 201, 230, 255, 255,
  ]);
  assert.equal(fake.created.length, 1, 'mode changes do not allocate another raster');
});

test('same dimensions reuse resources while every call rewrites and encodes the current frame', () => {
  const fake = fakeCanvas();
  let factories = 0;
  const cache = new ImageRasterCache(createPalette(colors), () => {
    factories += 1;
    return fake.canvas as unknown as HTMLCanvasElement;
  });
  const source = new Float32Array([0, 1]);
  const first = cache.encode(source, 2, 1, 'scalar', 0);
  source.set([1, 0]);
  const second = cache.encode(source, 2, 1, 'scalar', 0);
  const third = cache.encode(source, 2, 1, 'scalar', 0);
  assert.notEqual(first, second, 'mutated source data must be adopted');
  assert.equal(second, third);
  assert.equal(factories, 1);
  assert.equal(fake.contexts(), 1);
  assert.equal(fake.created.length, 1);
  assert.equal(fake.presented.length, 3);
  assert.equal(fake.encoded.length, 3, 'even repeated replay input is encoded again');
  assert.equal(fake.presented[0].image, fake.presented[2].image);
  assert.deepEqual(fake.presented[0].bytes, [...rgba(0), ...rgba(255)]);
  assert.deepEqual(fake.presented[1].bytes, [...rgba(255), ...rgba(0)]);
});

test('dimension changes rebuild pixel storage, including changed shape with equal pixel count', () => {
  const fake = fakeCanvas();
  const cache = new ImageRasterCache(createPalette(colors), () => fake.canvas as unknown as HTMLCanvasElement);
  cache.encode(new Float32Array([0, 1]), 2, 1, 'scalar', 0);
  const first = fake.created[0];
  cache.encode(new Float32Array([1, 0]), 1, 2, 'scalar', 0);
  assert.equal(fake.created.length, 2);
  assert.notEqual(fake.created[1].data.buffer, first.data.buffer);
  assert.deepEqual([fake.canvas.width, fake.canvas.height], [1, 2]);
  assert.deepEqual(fake.presented[1].bytes, [...rgba(255), ...rgba(0)]);
});

test('clear releases the cached workspace and permits a fresh encode', () => {
  const canvases: ReturnType<typeof fakeCanvas>[] = [];
  const cache = new ImageRasterCache(createPalette(colors), () => {
    const fake = fakeCanvas();
    canvases.push(fake);
    return fake.canvas as unknown as HTMLCanvasElement;
  });
  cache.encode(new Float32Array([0]), 1, 1, 'scalar', 0);
  cache.clear();
  cache.encode(new Float32Array([1]), 1, 1, 'scalar', 0);
  assert.equal(canvases.length, 2);
  assert.deepEqual(canvases[1].presented[0].bytes, rgba(255));
});

test('invalid input and rasterization failures propagate instead of returning a stale image', () => {
  const fake = fakeCanvas();
  const cache = new ImageRasterCache(createPalette(colors), () => fake.canvas as unknown as HTMLCanvasElement);
  assert.throws(() => cache.encode(new Float32Array(3), 2, 2, 'scalar', 0), /Truncated/);
  assert.throws(() => cache.encode(new Float32Array(4), 2, 2, 'scalar', 1), /Truncated/);
  assert.throws(() => cache.encode(new Uint8Array(4), 2, 2, 'scalar', 0), /dtype/);
  assert.throws(() => cache.encode(new Float32Array(4), 0, 2, 'scalar', 0), /dimensions/);
  assert.equal(fake.created.length, 0);
  fake.context.putImageData = () => { throw new Error('raster failed'); };
  assert.throws(() => cache.encode(new Float32Array(4), 2, 2, 'scalar', 0), /raster failed/);
  assert.equal(fake.encoded.length, 0);
  fake.context.putImageData = () => {};
  fake.canvas.toDataURL = () => { throw new Error('PNG encoding failed'); };
  assert.throws(() => cache.encode(new Float32Array(4), 2, 2, 'scalar', 0), /PNG encoding failed/);
  for (const invalid of ['', 'data:,', 'data:image/png;base64,', 'data:image/jpeg;base64,AAAA']) {
    fake.canvas.toDataURL = () => invalid;
    assert.throws(() => cache.encode(new Float32Array(4), 2, 2, 'scalar', 0), /failed to encode a PNG/);
  }
  const unsupported = new ImageRasterCache(createPalette(colors), () => ({
    getContext: () => null,
  } as unknown as HTMLCanvasElement));
  assert.throws(() => unsupported.encode(new Float32Array(1), 1, 1, 'scalar', 0), /2D context/);
});
