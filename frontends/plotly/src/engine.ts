import { version as reactVersion } from 'react';
import { PlotAdapter } from './adapter';
import { MetricsSink, type Sample } from './metrics';
import { acceptStreamPacket, parseConfiguration, parseReplay, type Configuration, type Frame } from './protocol';
import { LatestFrameScheduler, replayTick, skippedBetween } from './scheduler';
import { browserContext } from './browser-context';

export interface Options {
  url: string;
  mode: 'stream' | 'replay';
  runId: string;
  duration: number;
  width: number;
  height: number;
}

export interface Status {
  running: boolean;
  complete: boolean;
  error: string | null;
  stop_reason: 'duration' | 'user' | 'error' | 'dispose' | null;
  connection: string;
  submitted: number;
  updates_hz: number;
  update_ms: number;
  receive_age_ms: number | null;
  skipped: number;
  target_hz: number;
  metrics_error: string | null;
  dropped_metrics: number;
  metadata: Record<string, unknown>;
}

declare global {
  interface Window {
    __plotbenchStatus?: Status;
    __plotbenchLifecycle?: (message: {
      event: 'started' | 'stopped';
      state: Pick<Status, 'running' | 'complete' | 'error' | 'stop_reason' |
        'submitted' | 'metrics_error' | 'dropped_metrics'>;
    }) => Promise<void>;
  }
}

export function readOptions(): Options {
  const query = new URLSearchParams(window.location.search);
  const numeric = (key: string, fallback: number) => {
    const value = Number(query.get(key) ?? fallback);
    if (!Number.isFinite(value) || value < 0) throw new Error(`Invalid ${key} query parameter`);
    return value;
  };
  const mode = query.get('mode') ?? 'stream';
  if (mode !== 'stream' && mode !== 'replay') throw new Error('mode must be stream or replay');
  const endpoint = new URL(query.get('url') ?? 'http://127.0.0.1:8765');
  if (!['http:', 'https:'].includes(endpoint.protocol)) throw new Error('url must use HTTP or HTTPS');
  return {
    url: endpoint.href.replace(/\/$/, ''), mode, runId: query.get('run_id') ?? 'demo',
    duration: numeric('duration', 0), width: Math.max(640, numeric('width', 1100)),
    height: Math.max(600, numeric('height', 820)),
  };
}

export class BenchmarkEngine {
  private adapter?: PlotAdapter;
  private sink?: MetricsSink;
  private socket?: WebSocket;
  private replayTimer?: ReturnType<typeof setTimeout>;
  private hudTimer?: ReturnType<typeof setInterval>;
  private metricsTimer?: ReturnType<typeof setInterval>;
  private durationTimer?: ReturnType<typeof setTimeout>;
  private abort = new AbortController();
  private closing?: Promise<void>;
  private stopped = false;
  private startedMeasuring = false;
  private replayGeneration = 0;
  private replayRequest = 0;
  private previous?: Frame;
  private recent: { time: number; sample: Sample }[] = [];
  private scheduler: LatestFrameScheduler<Frame>;
  private status: Status;

  constructor(readonly options: Options, private waveElement: HTMLDivElement,
    private imageElement: HTMLDivElement, private onStatus: (status: Status) => void,
    private onConfig: (config: Configuration) => void) {
    this.status = {
      running: true, complete: false, error: null, stop_reason: null, connection: 'Connecting', submitted: 0,
      updates_hz: 0, update_ms: 0, receive_age_ms: null, skipped: 0, target_hz: 0,
      metrics_error: null, dropped_metrics: 0, metadata: {},
    };
    this.scheduler = new LatestFrameScheduler((frame) => this.consume(frame), (error) => this.fail(error));
  }

  async start(): Promise<void> {
    this.publish();
    try {
      const [rawConfig, colormap] = await Promise.all([
        this.request('/api/config').then((response) => response.json()),
        this.request('/api/colormap').then((response) => response.json()),
      ]);
      if (this.stopped) return;
      const config = parseConfiguration(rawConfig);
      this.onConfig(config);
      this.status.target_hz = config.hz;
      this.adapter = new PlotAdapter(this.waveElement, this.imageElement, colormap);
      const metadata = {
        ...PlotAdapter.metadata(), frontend: 'plotly',
        versions: { ...PlotAdapter.metadata().versions, react: reactVersion },
        pixel_ratio: devicePixelRatio,
        viewport: { logical: [innerWidth, innerHeight], physical: [innerWidth * devicePixelRatio, innerHeight * devicePixelRatio] },
        requested_window: [this.options.width, this.options.height],
        user_agent: navigator.userAgent, platform: navigator.platform,
        browser_context: browserContext(),
        decoder_thread: 'page main thread; WebSocket onmessage parses and acknowledges before deferred plotting',
        source_url: this.options.url, scheduling: 'one active Plotly update and one latest-frame mailbox; one server packet in flight until decode/offer ACK; no requestAnimationFrame cap',
        transport: this.options.mode === 'stream' ? 'single-in-flight acknowledgements' : 'bounded HTTP preload',
        hud_overhead: 'React HUD refreshes at 2Hz outside update_ms; its layout/paint work competes for the main thread and contributes to process CPU and achieved throughput. Per-update plot geometry reads are included in conversion_ms.',
        replay: this.options.mode === 'replay' ? 'bounded central CPU frame cycle; no GPU preloading' : null,
      };
      this.status.metadata = metadata;
      this.sink = new MetricsSink(this.options.url, this.options.mode, this.options.runId, metadata);
      this.hudTimer = setInterval(() => this.publish(), 500);
      this.metricsTimer = setInterval(() => { void this.sink?.flush(); }, 1000);
      if (this.options.mode === 'stream') this.openSocket();
      else await this.reloadReplay();
    } catch (error) {
      if (!this.stopped) this.fail(error);
    }
  }

  private async request(path: string, init?: RequestInit): Promise<Response> {
    const response = await fetch(`${this.options.url}${path}`, {
      ...init, signal: AbortSignal.any([this.abort.signal, AbortSignal.timeout(60000)]),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`${path}: HTTP ${response.status} ${text.slice(0, 300)}`);
    }
    return response;
  }

  private openSocket(): void {
    const address = new URL(`${this.options.url}/ws`);
    address.protocol = address.protocol === 'https:' ? 'wss:' : 'ws:';
    this.socket = new WebSocket(address);
    this.socket.binaryType = 'arraybuffer';
    this.socket.onopen = () => { this.status.connection = 'Streaming'; this.publish(); };
    this.socket.onmessage = ({ data }: MessageEvent<ArrayBuffer>) => {
      if (this.stopped) return;
      try {
        if (!(data instanceof ArrayBuffer)) throw new Error('Expected binary WebSocket packet');
        acceptStreamPacket(data, (frame) => this.scheduler.offer(frame), (message) => {
          if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(message);
        });
      } catch (error) { this.fail(error); }
    };
    this.socket.onerror = () => { if (!this.stopped) this.fail(new Error('WebSocket connection failed')); };
    this.socket.onclose = ({ code, reason }) => {
      if (!this.stopped) this.fail(new Error(`WebSocket closed (${code}): ${reason || 'source disconnected'}`));
    };
  }

  private async reloadReplay(): Promise<void> {
    const requestId = ++this.replayRequest;
    const previousConnection = this.status.connection;
    this.status.connection = 'Preloading replay';
    this.publish();
    let buffer: ArrayBuffer;
    let frames: Frame[];
    try {
      buffer = await this.request('/api/replay?count=16').then((response) => response.arrayBuffer());
      if (this.stopped || requestId !== this.replayRequest) return;
      frames = parseReplay(buffer);
    } catch (error) {
      if (!this.stopped && requestId === this.replayRequest) {
        this.status.connection = previousConnection;
        this.publish();
      }
      throw error;
    }
    // Keep playing the current CPU sequence until a replacement is fully validated.
    clearTimeout(this.replayTimer);
    const playbackId = ++this.replayGeneration;
    this.sink!.metadata.replay_frames = frames.length;
    this.sink!.metadata.replay_bytes = buffer.byteLength;
    this.status.connection = `Replay · ${frames.length} CPU frames`;
    const start = performance.now();
    const hz = frames[0].config.hz;
    let last = -1;
    const tick = () => {
      if (this.stopped || playbackId !== this.replayGeneration) return;
      const elapsed = performance.now() - start;
      const sequence = replayTick(elapsed, hz);
      if (sequence !== last) {
        last = sequence;
        this.scheduler.offer({ ...frames[sequence % frames.length], seq: sequence });
      }
      this.replayTimer = setTimeout(tick, Math.max(1, (sequence + 1) * 1000 / hz - (performance.now() - start)));
    };
    tick();
  }

  async applyConfig(changes: Partial<Configuration>): Promise<Configuration> {
    if (this.stopped) throw new Error('Restart the demo before changing its configuration');
    const config = parseConfiguration(await this.request('/api/config', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes),
    }).then((response) => response.json()));
    if (this.options.mode === 'replay') {
      // Replay controls describe the cached frames actually in use. A failed preload
      // leaves that selection intact even though the shared source accepted the change.
      await this.reloadReplay();
    } else {
      this.onConfig(config);
      this.status.target_hz = config.hz;
    }
    return config;
  }

  private async consume(frame: Frame): Promise<void> {
    if (this.stopped) return;
    if (this.previous?.generation !== frame.generation) this.onConfig(frame.config);
    this.status.target_hz = frame.config.hz;
    const client_time_ms = Date.now();
    const timing = await this.adapter!.update(frame);
    const firstUpdate = !this.startedMeasuring;
    if (firstUpdate) {
      this.startedMeasuring = true;
      if (this.options.duration > 0 && !this.stopped) {
        this.durationTimer = setTimeout(() => { void this.stop('duration'); }, this.options.duration * 1000);
      }
    }
    const sample: Sample = {
      seq: frame.seq, generation: frame.generation, client_time_ms,
      receive_age_ms: this.options.mode === 'replay' ? null : client_time_ms - frame.emitted_at_ms,
      skipped: skippedBetween(this.previous, frame), ...timing,
    };
    this.previous = frame;
    this.sink!.metadata.config = frame.config;
    this.sink!.metadata.target_hz = frame.config.hz;
    Object.assign(this.sink!.metadata, this.adapter!.viewport());
    this.sink!.record(sample);
    this.status.submitted += 1;
    this.status.skipped += sample.skipped;
    this.recent.push({ time: performance.now(), sample });
    if (this.recent.length > 512) this.recent.splice(0, this.recent.length - 512);
    if (firstUpdate) this.notifyLifecycle('started');
  }

  private notifyLifecycle(event: 'started' | 'stopped'): void {
    const notify = window.__plotbenchLifecycle;
    if (!notify) return;
    const { running, complete, error, stop_reason, submitted, metrics_error, dropped_metrics } = this.status;
    // The automation bridge is optional and used only twice per run, never per frame or HUD tick.
    void notify({ event, state: {
      running, complete, error, stop_reason, submitted, metrics_error, dropped_metrics,
    } }).catch((failure: unknown) => {
      // Surface a broken bridge to Playwright's pageerror handler rather than silently timing out.
      queueMicrotask(() => { throw failure; });
    });
  }

  private fail(error: unknown): void {
    this.status.error = error instanceof Error ? error.message : String(error);
    this.status.connection = 'Error';
    this.publish();
    void this.stop('error');
  }

  private publish(): void {
    const cutoff = performance.now() - 1000;
    this.recent = this.recent.filter(({ time }) => time >= cutoff);
    this.status.updates_hz = this.recent.length;
    if (this.recent.length) {
      this.status.update_ms = this.recent.reduce((sum, { sample }) => sum + sample.update_ms, 0) / this.recent.length;
      this.status.receive_age_ms = this.recent.at(-1)!.sample.receive_age_ms;
    }
    this.status.metrics_error = this.sink?.error ?? null;
    this.status.dropped_metrics = this.sink?.dropped ?? 0;
    const snapshot = { ...this.status, metadata: { ...this.status.metadata } };
    window.__plotbenchStatus = snapshot;
    this.onStatus(snapshot);
  }

  stop(reason: NonNullable<Status['stop_reason']> = 'user'): Promise<void> {
    if (this.closing) return this.closing;
    this.stopped = true;
    this.status.stop_reason = reason;
    if (this.sink) this.sink.metadata.stop_reason = reason;
    this.abort.abort();
    this.socket?.close(1000, 'Benchmark stopped');
    clearTimeout(this.replayTimer);
    clearTimeout(this.durationTimer);
    clearInterval(this.metricsTimer);
    clearInterval(this.hudTimer);
    this.closing = (async () => {
      await this.scheduler.close();
      await this.sink?.close();
      this.status.running = false;
      this.status.complete = true;
      if (!this.status.error) this.status.connection = 'Stopped · metrics flushed';
      if (this.sink?.error) {
        this.status.error = this.sink.error;
        this.status.connection = 'Stopped · metrics upload failed';
      }
      this.publish();
      this.notifyLifecycle('stopped');
    })();
    return this.closing;
  }

  async dispose(): Promise<void> {
    await this.stop('dispose');
    this.adapter?.destroy();
  }
}
