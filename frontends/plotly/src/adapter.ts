import Plotly from 'plotly.js-dist-min';
import type { Config, Data, Layout } from 'plotly.js';
import type { Frame } from './protocol';
import { submitUpdates, type AdapterTiming } from './update-timing';

export class PlotAdapter {
  private initialized = new Set<HTMLDivElement>();
  private colorscale: [number, string][];

  constructor(private waveform: HTMLDivElement, private image: HTMLDivElement, colors: number[][]) {
    if (colors.length !== 256 || colors.some((rgb) => rgb.length !== 3 ||
        rgb.some((channel) => !Number.isInteger(channel) || channel < 0 || channel > 255))) {
      throw new Error('Source colormap must have 256 RGB entries');
    }
    // Repeated boundaries make Plotly match the shared floor(value * 255) lookup table.
    this.colorscale = colors.flatMap(([r, g, b], index): [number, string][] => {
      const color = `rgb(${r},${g},${b})`;
      return index < 255 ? [[index / 255, color], [(index + 1) / 255, color]] : [[1, color]];
    });
  }

  static metadata() {
    return {
      renderer: 'Plotly scattergl (WebGL) + heatmap/image (Plotly raster traces)',
      versions: { plotly: (Plotly as typeof Plotly & { version: string }).version },
      update_strategy: 'Full authoritative array replacement via Plotly.react for both replace and append modes; no decimation',
      measurement_stage: 'update_ms: elapsed conversion plus synchronous Plotly.react calls. draw_ms: synchronous Plotly.react calls, already included in update_ms. update_complete_ms: elapsed adapter call through settlement of both Plotly Promises, including deferred work and wait. Calls are serialized until settlement; none of these timings measures GPU completion or screen presentation.',
      image_interpolation: 'nearest neighbor (zsmooth: false)',
      image_levels: [0, 1],
      waveform_range: [-1.5, 1.5],
      waveform_stroke_physical_px: 1,
      scalar_colormap: '256 entries from central /api/colormap, fixed [0,1], discrete floor(value*255) lookup',
    };
  }

  async update(frame: Frame): Promise<AdapterTiming> {
    const started = performance.now();
    const dpr = window.devicePixelRatio || 1;
    const config = frame.config;
    this.waveform.parentElement!.hidden = config.view === 'image';
    this.image.parentElement!.hidden = config.view === 'waveform';
    const jobs: { element: HTMLDivElement; trace: Data; layout: Partial<Layout> }[] = [];
    if (frame.waveform && config.view !== 'image') {
      jobs.push({
        element: this.waveform,
        trace: {
          type: 'scattergl', mode: 'lines', y: frame.waveform, x0: 0, dx: 1,
          line: { color: '#64dccc', width: 1 / dpr }, hoverinfo: 'skip',
        } as Data,
        layout: this.layout(this.waveform, frame, false),
      });
    }
    if (frame.image && config.view !== 'waveform') {
      const pixels = frame.image;
      let trace: Data;
      if (config.image_mode === 'scalar') {
        const z: Float32Array[] = [];
        for (let row = 0; row < config.height; row += 1) {
          z.push((pixels as Float32Array).subarray(row * config.width, (row + 1) * config.width));
        }
        trace = {
          type: 'heatmap', z, zmin: 0, zmax: 1, zauto: false,
          colorscale: this.colorscale, zsmooth: false, showscale: false,
          hoverinfo: 'skip', x0: 0, dx: 1, y0: 0, dy: 1,
        // DefinitelyTyped does not describe Plotly's supported typed-array rows.
        } as unknown as Data;
      } else {
        // The image trace's z input uses RGB triples. This adapter measures that conversion;
        // a separately optimized source/data-URI adapter would have different preparation work.
        const z: number[][][] = new Array(config.height);
        for (let row = 0; row < config.height; row += 1) {
          const output: number[][] = new Array(config.width);
          for (let column = 0; column < config.width; column += 1) {
            const index = (row * config.width + column) * 3;
            output[column] = [pixels[index], pixels[index + 1], pixels[index + 2]];
          }
          z[row] = output;
        }
        trace = {
          type: 'image', z, colormodel: 'rgb', zsmooth: false, hoverinfo: 'skip',
          x0: 0, dx: 1, y0: 0, dy: 1,
        } as Data;
      }
      jobs.push({ element: this.image, trace, layout: this.layout(this.image, frame, true) });
    }
    const converted = performance.now();
    const settings: Partial<Config> = {
      displayModeBar: false, responsive: false, staticPlot: true, plotGlPixelRatio: dpr,
    };
    return submitUpdates(started, converted, () => jobs.map(({ element, trace, layout }) => {
      this.initialized.add(element);
      return Plotly.react(element, [trace], layout, settings);
    }));
  }

  private layout(element: HTMLDivElement, frame: Frame, image: boolean): Partial<Layout> {
    const config = frame.config;
    const bounds = element.getBoundingClientRect();
    const axis = { fixedrange: true, showgrid: false, zeroline: false, color: '#8fa7b6',
      tickfont: { size: 10 }, linecolor: '#253745' };
    return {
      width: Math.max(120, Math.floor(bounds.width)),
      height: Math.max(100, Math.floor(bounds.height)),
      margin: { l: 46, r: 15, t: 8, b: 32, pad: 0 },
      paper_bgcolor: '#111e28', plot_bgcolor: '#111e28',
      font: { family: 'ui-monospace, SFMono-Regular, monospace', color: '#8fa7b6', size: 10 },
      showlegend: false, hovermode: false, dragmode: false, autosize: false,
      datarevision: frame.seq, uirevision: frame.generation,
      xaxis: { ...axis, range: image ? [-0.5, config.width - 0.5] : [0, config.points - 1],
        ...(image ? { constrain: 'domain' } : {}) },
      yaxis: { ...axis, range: image ? [config.height - 0.5, -0.5] : [-1.5, 1.5],
        ...(image ? { scaleanchor: 'x', scaleratio: 1, constrain: 'domain' } : {}) },
    };
  }

  viewport() {
    const ratio = window.devicePixelRatio || 1;
    const containerSize = (element: HTMLDivElement) => {
      if (element.parentElement!.hidden) return null;
      const { width, height } = element.getBoundingClientRect();
      return { logical: [width, height], physical: [width * ratio, height * ratio] };
    };
    const dataArea = (element: HTMLDivElement): [number, number] | null => {
      if (element.parentElement!.hidden) return null;
      // Plotly 4's resolved axis lengths account for margins and constrained image domains.
      // Preserve null if a future Plotly version removes these diagnostic fields.
      const layout = (element as HTMLDivElement & {
        _fullLayout?: { xaxis?: { _length?: number }; yaxis?: { _length?: number } };
      })._fullLayout;
      const width = layout?.xaxis?._length;
      const height = layout?.yaxis?._length;
      return typeof width === 'number' && typeof height === 'number' &&
        Number.isFinite(width) && Number.isFinite(height) ? [width, height] : null;
    };
    const logical = { waveform: dataArea(this.waveform), image: dataArea(this.image) };
    const physical = (area: [number, number] | null) => area?.map((size) => size * ratio) ?? null;
    return {
      pixel_ratio: ratio,
      viewport: { logical: [innerWidth, innerHeight], physical: [innerWidth * ratio, innerHeight * ratio] },
      plot_viewport_units: 'physical pixels; data drawing area excluding axes and margins',
      plot_viewports: { waveform: physical(logical.waveform), image: physical(logical.image) },
      plot_viewports_logical: logical,
      plot_containers: { waveform: containerSize(this.waveform), image: containerSize(this.image) },
      plot_viewport_measurement: 'resolved Plotly 4 _fullLayout axis lengths; null when hidden or unavailable',
    };
  }

  destroy(): void {
    for (const element of this.initialized) Plotly.purge(element);
    this.initialized.clear();
  }
}
