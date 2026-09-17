/** Pack the source's discrete LUT into the host's native Uint32 representation. */
export function createPalette(colors: number[][]): Uint32Array {
  if (colors.length !== 256 || colors.some((rgb) => !Array.isArray(rgb) || rgb.length !== 3 ||
      rgb.some((channel) => !Number.isInteger(channel) || channel < 0 || channel > 255))) {
    throw new Error('Source colormap must have 256 RGB entries');
  }
  // Fill RGBA bytes first: bit shifting would assume a particular byte order.
  const bytes = new Uint8Array(256 * 4);
  colors.forEach(([red, green, blue], index) => {
    bytes.set([red, green, blue, 255], index * 4);
  });
  return new Uint32Array(bytes.buffer);
}

/** One reusable CPU raster workspace; each call converts and encodes a fresh frame. */
export class ImageRasterCache {
  private canvas?: HTMLCanvasElement;
  private context?: CanvasRenderingContext2D;
  private image?: ImageData;
  private packed?: Uint32Array;

  constructor(private readonly palette: Uint32Array,
    private readonly canvasFactory: () => HTMLCanvasElement = () => document.createElement('canvas')) {
    if (palette.length !== 256) throw new Error('Image raster requires a 256-entry palette');
  }

  encode(pixels: Float32Array | Uint8Array, width: number, height: number,
    mode: 'scalar' | 'rgb', plot: number): string {
    if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) || width < 1 || height < 1 ||
        !Number.isSafeInteger(plot) || plot < 0) throw new Error('Invalid image raster dimensions or plot');
    if ((mode === 'scalar' && !(pixels instanceof Float32Array)) ||
        (mode === 'rgb' && !(pixels instanceof Uint8Array)) ||
        (mode !== 'scalar' && mode !== 'rgb')) throw new Error('Invalid image raster dtype or mode');
    const count = width * height;
    const block = count * (mode === 'rgb' ? 3 : 1);
    const base = plot * block;
    if (!Number.isSafeInteger(count) || !Number.isSafeInteger(base + block) ||
        base + block > pixels.length) throw new Error('Truncated image raster plot');

    if (!this.canvas) {
      const canvas = this.canvasFactory();
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Image raster requires a canvas 2D context');
      this.canvas = canvas;
      this.context = context;
    }
    if (!this.image || this.image.width !== width || this.image.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
      this.image = this.context!.createImageData(width, height);
      this.packed = new Uint32Array(this.image.data.buffer, this.image.data.byteOffset, count);
    }

    if (mode === 'scalar') {
      const output = this.packed!;
      for (let index = 0; index < count; index += 1) {
        const value = pixels[base + index];
        // NaN and values <= 0 use LUT[0]; +Infinity and values >= 1 use LUT[255].
        const color = value > 0 ? (value >= 1 ? 255 : Math.floor(value * 255)) : 0;
        output[index] = this.palette[color];
      }
    } else {
      const output = this.image.data;
      for (let index = 0; index < count; index += 1) {
        const input = base + index * 3;
        const offset = index * 4;
        output[offset] = pixels[input];
        output[offset + 1] = pixels[input + 1];
        output[offset + 2] = pixels[input + 2];
        output[offset + 3] = 255;
      }
    }
    this.context!.putImageData(this.image, 0, 0);
    const source = this.canvas.toDataURL('image/png');
    const prefix = 'data:image/png;base64,';
    if (!source.startsWith(prefix) || source.length === prefix.length) {
      throw new Error('Canvas failed to encode a PNG image');
    }
    return source;
  }

  clear(): void {
    this.canvas = undefined;
    this.context = undefined;
    this.image = undefined;
    this.packed = undefined;
  }
}
