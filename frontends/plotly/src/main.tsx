import { useEffect, useRef, useState, type FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import { BenchmarkEngine, readOptions, type Options, type Status } from './engine';
import type { Configuration } from './protocol';
import { nextPlotView, plotToggleState, type PlotKind } from './plot-selection';
import { gridTemplateColumns, imageLayoutLabel, visiblePlotCount, waveformLayoutLabel } from './plot-grid';
import { ConfigurationDraft } from './config-draft';
import { metricHints } from './metric-hints';
import './style.css';

function App({ options }: { options: Options }) {
  const wave = useRef<HTMLDivElement>(null);
  const image = useRef<HTMLDivElement>(null);
  const controls = useRef<HTMLDetailsElement>(null);
  const engine = useRef<BenchmarkEngine | null>(null);
  const requestPending = useRef(false);
  const draft = useRef(new ConfigurationDraft());
  const [status, setStatus] = useState<Status | null>(null);
  const [config, setConfig] = useState<Configuration | null>(null);
  const [form, setForm] = useState<Configuration | null>(null);
  const [applying, setApplying] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    const instance = new BenchmarkEngine(options, wave.current!, image.current!, setStatus, (next) => {
      setConfig(previous => previous && previous.generation > next.generation ? previous : next);
      setForm(draft.current.receive(next));
    });
    engine.current = instance;
    void instance.start();
    const stop = () => { void instance.stop('dispose'); };
    window.addEventListener('pagehide', stop);
    return () => { window.removeEventListener('pagehide', stop); void instance.dispose(); };
  }, [options]);

  async function updateConfig(changes: Partial<Configuration>): Promise<boolean> {
    if (requestPending.current || !engine.current) return false;
    requestPending.current = true;
    setApplying(true); setFormError(null);
    try {
      await engine.current.applyConfig(changes);
      return true;
    } catch (error) {
      setFormError(error instanceof Error ? error.message : String(error));
      return false;
    }
    finally { requestPending.current = false; setApplying(false); }
  }

  async function apply(event: FormEvent) {
    event.preventDefault();
    if (!form) return;
    const submission = draft.current.capture();
    if (!submission.size) return;
    if (await updateConfig(ConfigurationDraft.patch(submission))) {
      setForm(draft.current.acknowledge(submission));
      if (!draft.current.capture().size && controls.current) controls.current.open = false;
    }
  }

  function togglePlot(plot: PlotKind) {
    if (!config || plotToggleState(config.view, plot, applying, options.duration > 0,
      Boolean(status?.running)).disabled) return;
    void updateConfig({ view: nextPlotView(config.view, plot) });
  }

  const change = <K extends Exclude<keyof Configuration, 'generation' | 'view'>>(key: K, value: Configuration[K]) => {
    setForm(draft.current.change(key, value, requestPending.current));
  };
  const number = (value: number | null | undefined, digits = 1) => value == null ? '—' : value.toFixed(digits);
  const activeView = config?.view ?? 'both';
  const waveformLayout = config ? waveformLayoutLabel(config) : null;
  const imageLayout = config ? imageLayoutLabel(config) : null;
  const error = formError || status?.error || status?.metrics_error;
  const hints = metricHints(config?.hz, options.mode === 'replay');

  return <main style={{ maxWidth: options.width }}>
    <header>
      <div className="identity"><span className="eyebrow">PLOTTING BENCHMARK</span>
        <div className="title-row"><h1>Plotly <span>+</span> React</h1><span className="renderer-badge">WebGL / browser</span><span className="input-badge">{options.mode === 'stream' ? 'Stream' : 'Replay'}</span></div>
      </div>
      <div className="header-right"><span className={`status ${status?.error ? 'error' : ''}`}>
        <i />{status?.connection ?? 'Starting'}</span>
        <details className="source-controls" ref={controls}>
          <summary>Source controls</summary>
          <section className="controls" aria-label="Workload configuration">
            <div className="control-heading"><h2>Source controls</h2><a href={options.url} target="_blank" rel="noopener noreferrer">Open source ↗</a></div>
            <p className="control-description">Updates the shared workload for connected demos.</p>
            <div className="control-source"><code>{options.url}</code>
        <label className="mode">Input <select aria-label="Input mode" value={options.mode} onChange={(event) => {
          const url = new URL(window.location.href); url.searchParams.set('mode', event.target.value); window.location.assign(url);
        }}><option value="stream">Live stream</option><option value="replay">Preloaded replay</option></select></label>
      </div>
      {form && <form id="workload-form" onSubmit={(event) => void apply(event)}>
        <label>Source Hz<input aria-label="Source Hz" type="number" min="0.1" max="120" step="0.1" required value={form.hz} onChange={(event) => change('hz', Number(event.target.value))} /></label>
        <label>Points<input aria-label="Points" type="number" min="2" step="1" required value={form.points} onChange={(event) => change('points', Number(event.target.value))} /></label>
        <label>Waveform<select aria-label="Waveform mode" value={form.waveform_mode} onChange={(event) => change('waveform_mode', event.target.value as Configuration['waveform_mode'])}><option value="replace">Replace window</option><option value="append">Append / rolling</option></select></label>
        <label>Append samples<input aria-label="Append samples" type="number" min="1" max={form.points} step="1" required value={form.append_count} onChange={(event) => change('append_count', Number(event.target.value))} /></label>
        <label>Curves per plot<input aria-label="Curves per plot" type="number" min="1" max="64" step="1" required value={form.curves} onChange={(event) => change('curves', Number(event.target.value))} /></label>
        <label>Waveform plots<input aria-label="Waveform plots" type="number" min="1" max="16" step="1" required value={form.waveform_plots} onChange={(event) => change('waveform_plots', Number(event.target.value))} /></label>
        <label>Image width<input aria-label="Image width" type="number" min="1" step="1" required value={form.width} onChange={(event) => change('width', Number(event.target.value))} /></label>
        <label>Image height<input aria-label="Image height" type="number" min="1" step="1" required value={form.height} onChange={(event) => change('height', Number(event.target.value))} /></label>
        <label className="image-mode-field">Image mode<select aria-label="Image mode" value={form.image_mode} onChange={(event) => change('image_mode', event.target.value as Configuration['image_mode'])}><option value="scalar">Scalar + colormap</option><option value="rgb">RGB</option></select></label>
        <label>Image plots<input aria-label="Image plots" type="number" min="1" max="16" step="1" required value={form.image_plots} onChange={(event) => change('image_plots', Number(event.target.value))} /></label>
        <div className="control-actions">
          <button type="button" className="secondary" onClick={() => {
            if (controls.current) controls.current.open = false;
            if (status?.running) void engine.current?.stop(); else window.location.reload();
          }}>{status?.running ? 'Stop & save' : 'Restart demo'}</button>
          <button type="submit" disabled={applying || !status?.running || !draft.current.capture().size}>{applying ? 'Applying…' : 'Apply workload'}</button>
        </div>
      </form>}
          </section>
        </details>
      </div>
    </header>
    {error && <p role="alert" className="error-message">{error}</p>}
    <section className="workload" aria-label="Current workload">
      <div><span>TARGET RATE</span><strong>{number(status?.target_hz)} Hz</strong></div>
      <div><span>WAVEFORM</span><strong>{config?.points.toLocaleString() ?? '—'}{waveformLayout ? '' : ' points'} <b>·</b> {config?.waveform_mode ?? 'replace'}{waveformLayout && <> <b>·</b> {waveformLayout}</>}</strong></div>
      <div><span>IMAGE</span><strong>{config?.width ?? '—'} × {config?.height ?? '—'} <b>·</b> {config?.image_mode === 'rgb' ? 'RGB' : 'scalar'}{imageLayout && <> <b>·</b> {imageLayout}</>}</strong></div>
      <div className="plot-selection"><span>PLOTS</span><div className="plot-buttons" role="group" aria-label="Visible plots">
        {(['waveform', 'image'] as const).map((plot) => {
          const state = plotToggleState(config?.view, plot, applying, options.duration > 0, Boolean(status?.running));
          return <button key={plot} type="button" className="plot-toggle" aria-label={state.label}
            aria-pressed={state.selected} title={state.title} disabled={state.disabled}
            onClick={() => togglePlot(plot)}>{plot === 'waveform' ? '1D' : '2D'}</button>;
        })}
      </div></div>
    </section>
    <section className="metrics" aria-label="Live benchmark metrics">
      <div title={`${status?.submitted.toLocaleString() ?? '0'} updates submitted; target follows the source rate, not display refresh`}><span>Submitted</span><strong>{number(status?.updates_hz)} <em>/s</em></strong><small>{hints.submitted}</small></div>
      <div title="CPU conversion and synchronous Plotly submission. One source period is a heuristic budget, not a GPU or display guarantee."><span>Update time</span><strong>{number(status?.update_ms, 2)} <em>ms</em></strong><small>{hints.update}</small></div>
      <div title="Source updates skipped"><span>Skipped</span><strong>{status?.skipped.toLocaleString() ?? '0'}</strong><small>{hints.skipped}</small></div>
      <div title={options.mode === 'replay' ? 'Not applicable to replay' : 'Approximate receive age from the same-host wall clock. One source period is a freshness goal, not measured presentation latency.'}><span>Receive age</span><strong>{number(status?.receive_age_ms)}{status?.receive_age_ms != null && <em> ms</em>}</strong><small>{hints.age}</small></div>
    </section>
    {/* The adapter owns one <article> per waveform/image plot inside these two containers; the grid
        columns follow the shared layout rule (waveform plots first, then image plots). */}
    <section className={`plots ${activeView}`} aria-label="Plots"
      style={{ gridTemplateColumns: gridTemplateColumns(config ? visiblePlotCount(config) : 0) }}>
      <div className="plot-group" aria-label="Waveform plots" ref={wave} hidden={activeView === 'image'} />
      <div className="plot-group" aria-label="Image plots" ref={image} hidden={activeView === 'waveform'} />
    </section>
    <footer><span>Submitted updates · not displayed FPS</span><span>scattergl · heatmap / image</span></footer>
  </main>;
}

try {
  const options = readOptions();
  createRoot(document.getElementById('root')!).render(<App options={options} />);
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  document.getElementById('root')!.textContent = `Cannot start benchmark: ${message}`;
  window.__plotbenchStatus = { running: false, complete: true, error: message, stop_reason: 'error', connection: 'Error',
    submitted: 0, updates_hz: 0, update_ms: 0, receive_age_ms: null, skipped: 0, target_hz: 0,
    metrics_error: null, dropped_metrics: 0, metadata: {} };
}
