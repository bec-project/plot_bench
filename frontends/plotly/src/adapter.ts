import Plotly from 'plotly.js-dist-min';
import { dataSlot } from './render-contract';
import type { Config, Data, Layout } from 'plotly.js';
import type { Configuration, Frame } from './protocol';
import type { PlotKind } from './plot-selection';
import {
  curveColor, gridTemplateColumns, imageSubtitle, plotCounts, plotTitle, visiblePlotCount, waveformSubtitle,
} from './plot-grid';
import { submitUpdates, type AdapterTiming } from './update-timing';

/** One grid cell: heading owned by this adapter, plot element owned by Plotly. */
interface PlotCell {
  article: HTMLElement;
  title: HTMLHeadingElement;
  subtitle: HTMLSpanElement;
  plot: HTMLDivElement;
}

/**
 * Owns the per-plot DOM below the two kind containers. React renders only the containers
 * (and the surrounding HUD); the adapter creates one `<article>` with a Plotly `<div>` per
 * waveform plot and per image plot from the frame configuration, so the widget set can never
 * lag behind the frame that needs it, and purges cells when counts shrink.
 */
export class PlotAdapter {
  private cells: Record<PlotKind, PlotCell[]> = { waveform: [], image: [] };
  private current: Configuration | null = null;
  private signature = '';
  private colorscale: [number, string][];

  constructor(private waveform: HTMLElement, private image: HTMLElement, colors: number[][]) {
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
      render_contract: 'data-area-v2',
      waveform_antialias: 'renderer-default (scattergl has no public disable switch)',
      renderer: 'Plotly scattergl (WebGL) + heatmap/image (Plotly raster traces)',
      versions: { plotly: (Plotly as typeof Plotly & { version: string }).version },
      update_strategy: 'One Plotly.react per plot widget per frame (waveform_plots + image_plots calls); every curve is a separate scattergl trace of the same plot; full authoritative array replacement for both replace and append modes; no decimation',
      measurement_stage: 'update_ms: elapsed conversion plus synchronous Plotly.react calls for every plot. draw_ms: synchronous Plotly.react calls, already included in update_ms. update_complete_ms: elapsed adapter call through settlement of all per-plot Plotly Promises, including deferred work and wait. Calls are serialized until settlement; none of these timings measures GPU completion or screen presentation.',
      image_interpolation: 'nearest neighbor (zsmooth: false)',
      image_levels: [0, 1],
      waveform_range: [-1.5, 1.5],
      waveform_stroke_physical_px: 1,
      scalar_colormap: '256 entries from central /api/colormap, fixed [0,1], discrete floor(value*255) lookup',
      curve_colors: 'shared CURVE_COLORS[c % 8] palette; curve 0 keeps the accent colour',
      plot_layout: 'columns = ceil(sqrt(visible plots)), row-major, waveform plots before image plots, equal cells',
    };
  }

  /** Build the widget set for a configuration before the first frame arrives. */
  prepare(config: Configuration): void {
    this.syncPlots(config);
  }

  private syncPlots(config: Configuration): void {
    const signature = [config.view, config.waveform_plots, config.curves, config.image_plots, config.points,
      config.waveform_mode, config.width, config.height, config.image_mode].join('|');
    this.current = config;
    if (signature === this.signature) return;
    this.signature = signature;
    this.waveform.hidden = config.view === 'image';
    this.image.hidden = config.view === 'waveform';
    const grid = this.waveform.parentElement;
    if (grid) grid.style.gridTemplateColumns = gridTemplateColumns(visiblePlotCount(config));
    this.resize('waveform', this.waveform, config.waveform_plots);
    this.resize('image', this.image, config.image_plots);
    this.cells.waveform.forEach((cell, index) => {
      cell.title.textContent = plotTitle('waveform', index, config.waveform_plots);
      cell.subtitle.textContent = waveformSubtitle(config);
    });
    this.cells.image.forEach((cell, index) => {
      cell.title.textContent = plotTitle('image', index, config.image_plots);
      cell.subtitle.textContent = imageSubtitle(config);
      cell.title.parentElement!.style.display = visiblePlotCount(config) > 1 ? 'none' : '';
    });
  }

  private resize(kind: PlotKind, container: HTMLElement, count: number): void {
    const cells = this.cells[kind];
    while (cells.length > count) {
      const cell = cells.pop()!;
      Plotly.purge(cell.plot);
      cell.article.remove();
    }
    while (cells.length < count) {
      const article = document.createElement('article');
      article.className = 'plot-cell';
      article.dataset.kind = kind;
      article.dataset.index = String(cells.length);
      const heading = document.createElement('div');
      heading.className = 'plot-heading';
      const title = document.createElement('h2');
      const subtitle = document.createElement('span');
      heading.append(title, subtitle);
      const plot = document.createElement('div');
      plot.className = 'plot';
      article.append(heading, plot);
      container.append(article);
      cells.push({ article, title, subtitle, plot });
    }
  }

  async update(frame: Frame): Promise<AdapterTiming> {
    const started = performance.now();
    const dpr = window.devicePixelRatio || 1;
    const config = frame.config;
    this.syncPlots(config);
    const jobs: { element: HTMLDivElement; traces: Data[]; layout: Partial<Layout> }[] = [];
    if (frame.waveform && config.view !== 'image') {
      const { curves, points } = config;
      this.cells.waveform.forEach((cell, plot) => {
        const traces: Data[] = [];
        for (let curve = 0; curve < curves; curve += 1) {
          const start = (plot * curves + curve) * points;
          traces.push({
            type: 'scattergl', mode: 'lines', y: frame.waveform!.subarray(start, start + points), x0: 0, dx: 1,
            line: { color: curveColor(curve), width: 1 / dpr }, hoverinfo: 'skip',
          } as Data);
        }
        jobs.push({ element: cell.plot, traces, layout: this.layout(cell.plot, frame, false) });
      });
    }
    if (frame.image && config.view !== 'waveform') {
      const pixels = frame.image;
      const { width, height } = config;
      this.cells.image.forEach((cell, plot) => {
        let trace: Data;
        if (config.image_mode === 'scalar') {
          const base = plot * height * width;
          const z: Float32Array[] = [];
          for (let row = 0; row < height; row += 1) {
            z.push((pixels as Float32Array).subarray(base + row * width, base + (row + 1) * width));
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
          const base = plot * height * width * 3;
          const z: number[][][] = new Array(height);
          for (let row = 0; row < height; row += 1) {
            const output: number[][] = new Array(width);
            for (let column = 0; column < width; column += 1) {
              const index = base + (row * width + column) * 3;
              output[column] = [pixels[index], pixels[index + 1], pixels[index + 2]];
            }
            z[row] = output;
          }
          trace = {
            type: 'image', z, colormodel: 'rgb', zsmooth: false, hoverinfo: 'skip',
            x0: 0, dx: 1, y0: 0, dy: 1,
          } as Data;
        }
        jobs.push({ element: cell.plot, traces: [trace], layout: this.layout(cell.plot, frame, true) });
      });
    }
    const converted = performance.now();
    const settings: Partial<Config> = {
      displayModeBar: false, responsive: false, staticPlot: true, plotGlPixelRatio: dpr,
    };
    return submitUpdates(started, converted, () => jobs.map(({ element, traces, layout }) =>
      Plotly.react(element, traces, layout, settings)));
  }

  private layout(element: HTMLDivElement, frame: Frame, image: boolean): Partial<Layout> {
    const config = frame.config;
    const [width, height] = dataSlot(innerWidth, innerHeight, visiblePlotCount(config), image);
    const bare = image && visiblePlotCount(config) > 1;
    const axis = { visible: !bare, automargin: false, fixedrange: true, showgrid: false, zeroline: false, color: '#8fa7b6',
      tickfont: { size: 10 }, linecolor: '#253745' };
    return {
      width: width + (bare ? 0 : 61),
      height: height + (bare ? 0 : 40),
      margin: bare ? {l: 0, r: 0, t: 0, b: 0, pad: 0} : { l: 46, r: 15, t: 8, b: 32, pad: 0 },
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
    const counts = this.current ? plotCounts(this.current) : { waveform: 0, image: 0 };
    // Every grid cell has the same size, so the first plot of each kind describes all of them.
    const first = (kind: PlotKind): HTMLDivElement | null =>
      counts[kind] > 0 ? this.cells[kind][0]?.plot ?? null : null;
    const containerSize = (element: HTMLDivElement | null) => {
      if (!element) return null;
      const { width, height } = element.getBoundingClientRect();
      return { logical: [width, height], physical: [width * ratio, height * ratio] };
    };
    const dataArea = (element: HTMLDivElement | null): [number, number] | null => {
      if (!element) return null;
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
    const logical = { waveform: dataArea(first('waveform')), image: dataArea(first('image')) };
    const physical = (area: [number, number] | null) => area?.map((size) => size * ratio) ?? null;
    return {
      render_contract: 'data-area-v2',
      plot_viewports_all: {
        waveform: counts.waveform ? this.cells.waveform.map(cell => physical(dataArea(cell.plot))) : [],
        image: counts.image ? this.cells.image.map(cell => physical(dataArea(cell.plot))) : [],
      },
      pixel_ratio: ratio,
      viewport: { logical: [innerWidth, innerHeight], physical: [innerWidth * ratio, innerHeight * ratio] },
      plot_viewport_units: 'physical pixels; data drawing area excluding axes and margins',
      plot_viewports: { waveform: physical(logical.waveform), image: physical(logical.image) },
      plot_viewports_logical: logical,
      plot_containers: { waveform: containerSize(first('waveform')), image: containerSize(first('image')) },
      plot_viewport_measurement: 'resolved Plotly 4 _fullLayout axis lengths of the first plot of each kind (all grid cells are equal); null when hidden or unavailable',
      plot_counts: counts,
      curves: this.current?.curves ?? 0,
    };
  }

  destroy(): void {
    this.resize('waveform', this.waveform, 0);
    this.resize('image', this.image, 0);
    this.signature = '';
  }
}
