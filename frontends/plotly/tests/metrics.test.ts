import assert from 'node:assert/strict';
import test from 'node:test';
import { MetricsSink, type Sample } from '../src/metrics';

const sample = (seq: number): Sample => ({ seq, generation: 0, client_time_ms: 1000,
  update_ms: 2, conversion_ms: 0.5, draw_ms: 1.5, update_complete_ms: 10,
  receive_age_ms: -0.25, skipped: 0 });

test('failed batches retry with new samples and preserve signed receive ages', async () => {
  const originalFetch = globalThis.fetch;
  const bodies: { samples: Sample[] }[] = [];
  try {
    let calls = 0;
    globalThis.fetch = async (_input, init) => {
      bodies.push(JSON.parse(String(init!.body)));
      return new Response('', { status: ++calls === 1 ? 503 : 200 });
    };
    const sink = new MetricsSink('http://localhost', 'stream', 'test', {});
    sink.record(sample(1)); await sink.flush();
    assert.match(sink.error!, /503/);
    sink.record(sample(2)); await sink.close();
    assert.deepEqual(bodies[1].samples.map((item) => item.seq), [1, 2]);
    assert.equal(bodies[1].samples[0].receive_age_ms, -0.25);
    assert.equal(bodies[1].samples[0].update_complete_ms, 10);
    assert.equal(sink.error, null);
  } finally { globalThis.fetch = originalFetch; }
});

test('close exports final metadata when the last periodic flush already drained the samples', async () => {
  const originalFetch = globalThis.fetch;
  const bodies: { samples: Sample[]; metadata: Record<string, unknown> }[] = [];
  try {
    globalThis.fetch = async (_input, init) => {
      bodies.push(JSON.parse(String(init!.body)));
      return new Response('', { status: 200 });
    };
    const sink = new MetricsSink('http://localhost', 'stream', 'test', {});
    sink.record(sample(1));
    await sink.flush();
    sink.metadata.stop_reason = 'duration';
    await sink.close();
    assert.equal(bodies.length, 2);
    assert.deepEqual(bodies[1].samples, []);
    assert.equal(bodies[1].metadata.stop_reason, 'duration');
  } finally { globalThis.fetch = originalFetch; }
});

test('metric outage has bounded memory with explicit dropped-sample accounting', async () => {
  const originalFetch = globalThis.fetch;
  try {
    let body: { samples: Sample[]; metadata: { dropped_metric_samples: number } } | undefined;
    globalThis.fetch = async (_input, init) => {
      body = JSON.parse(String(init!.body)); return new Response('', { status: 200 });
    };
    const sink = new MetricsSink('http://localhost', 'stream', 'test', {});
    for (let index = 0; index < 520; index += 1) sink.record(sample(index));
    await sink.close();
    assert.equal(body!.samples.length, 512);
    assert.equal(body!.samples[0].seq, 8);
    assert.equal(body!.metadata.dropped_metric_samples, 8);
  } finally { globalThis.fetch = originalFetch; }
});
