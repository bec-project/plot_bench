export interface Sample {
  seq: number;
  generation: number;
  client_time_ms: number;
  update_ms: number;
  receive_age_ms: number | null;
  skipped: number;
  conversion_ms: number;
  draw_ms: number;
  update_complete_ms: number;
}

export class MetricsSink {
  private samples: Sample[] = [];
  private active: Promise<void> | undefined;
  error: string | null = null;
  dropped = 0;

  constructor(private url: string, private mode: string, private runId: string,
    readonly metadata: Record<string, unknown>) {}

  record(sample: Sample): void {
    this.samples.push(sample);
    if (this.samples.length > 512) {
      this.dropped += this.samples.length - 512;
      this.samples.splice(0, this.samples.length - 512);
    }
  }

  async flush(includeMetadata = false): Promise<void> {
    if (this.active) return this.active;
    if (!this.samples.length && !includeMetadata) return;
    const batch = this.samples;
    this.samples = [];
    this.active = (async () => {
      try {
        const response = await fetch(`${this.url}/api/metrics`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ frontend: 'plotly', mode: this.mode, run_id: this.runId,
            samples: batch, metadata: { ...this.metadata, dropped_metric_samples: this.dropped } }),
          signal: AbortSignal.timeout(10000),
        });
        if (!response.ok) throw new Error(`Metrics upload: HTTP ${response.status}`);
        this.error = null;
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error);
        this.samples = [...batch, ...this.samples];
        if (this.samples.length > 512) {
          this.dropped += this.samples.length - 512;
          this.samples.splice(0, this.samples.length - 512);
        }
      } finally {
        this.active = undefined;
      }
    })();
    await this.active;
  }

  async close(): Promise<void> {
    await this.active;
    await this.flush(true);
  }
}
