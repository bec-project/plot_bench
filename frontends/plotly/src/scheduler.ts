/** One in-flight adapter call and one replaceable pending frame; no growing queue. */
export class LatestFrameScheduler<T> {
  private pending: T | undefined;
  private active: Promise<void> | undefined;
  private stopped = false;

  constructor(private consume: (frame: T) => Promise<void>, private onError: (error: unknown) => void) {}

  offer(frame: T): void {
    if (this.stopped) return;
    this.pending = frame;
    if (!this.active) {
      this.active = Promise.resolve().then(() => this.drain()).finally(() => {
        this.active = undefined;
        if (this.pending !== undefined && !this.stopped) this.offer(this.pending);
      });
    }
  }

  private async drain(): Promise<void> {
    try {
      while (!this.stopped && this.pending !== undefined) {
        const frame = this.pending;
        this.pending = undefined;
        await this.consume(frame);
      }
    } catch (error) {
      this.stopped = true;
      this.pending = undefined;
      this.onError(error);
    }
  }

  async close(): Promise<void> {
    this.stopped = true;
    this.pending = undefined;
    await this.active;
  }
}

export function skippedBetween(previous: { seq: number; generation: number } | undefined,
  next: { seq: number; generation: number }): number {
  if (!previous || previous.generation !== next.generation) return 0;
  return Math.max(0, next.seq - previous.seq - 1);
}

/** Advance from elapsed time, skipping missed ticks instead of replaying a backlog. */
export function replayTick(elapsedMs: number, hz: number): number {
  return Math.max(0, Math.floor(elapsedMs * hz / 1000));
}
