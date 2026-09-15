import assert from 'node:assert/strict';
import test from 'node:test';
import seed from './fixtures/baseline-campaign.json';
import { boardChart } from '../src/chart';
import { observations, type Submission } from '../src/model';
import { parseSubmission } from '../src/validation';
import { collectWinners } from '../src/winners';

test('a section chart carries one bar per ranked record with the observed repetition range', () => {
  const fixture = parseSubmission(structuredClone(seed)) as Submission;
  const { boards } = collectWinners(observations([fixture]));
  const large = boards.find((b) => b.section?.slug === 'large-image')!;
  const chart = boardChart(large);
  assert.equal(chart.target, 60);
  assert.deepEqual(
    chart.bars.map((b) => [b.frontend, b.rank, b.winner]),
    [
      ['pyqtgraph', 1, true],
      ['matplotlib', 2, false],
    ],
  );
  const matplotlib = chart.bars[1];
  assert.equal(matplotlib.median, 5.6);
  assert.equal(matplotlib.low, 5.5);
  assert.equal(matplotlib.high, 5.7);
  assert.equal(matplotlib.valid, 3);
  assert.equal(matplotlib.attempted, 3);
  assert.equal(matplotlib.limited, 1);
  assert.equal(matplotlib.minimum, matplotlib.median);
  assert.ok(chart.max >= 60 && chart.max <= 63.1);
  // The failed multi-image run is counted as attempted but never as a rate.
  const multi = boardChart(boards.find((b) => b.section?.slug === 'multi-image')!);
  const bar = multi.bars.find((b) => b.frontend === 'matplotlib')!;
  assert.deepEqual([bar.valid, bar.attempted, bar.low, bar.high], [2, 3, 19.6, 19.8]);
});

test('a record merged from equally ranked groups spans its lowest to highest median', () => {
  const on = (id: string, host: string, rates: number[]) => {
    const c = parseSubmission(structuredClone(seed)) as Submission;
    c.id = id;
    c.host.id = host;
    c.host.label = host;
    c.planned_runs = rates.length;
    c.runs = rates.map((rate, i) => {
      const r = structuredClone(c.runs[0]);
      r.id = `run-${i + 1}`;
      r.repetition = i + 1;
      r.metrics.submitted_hz = rate;
      r.metrics.rss_peak_mib = 100;
      r.metrics.cpu_mean_percent = 20;
      return r;
    });
    return c;
  };
  const { boards } = collectWinners(
    observations([on('h1', 'host-1', [59.9, 60, 60.1]), on('h2', 'host-2', [59.7, 59.8, 59.9])]),
  );
  assert.equal(boards.length, 1);
  assert.equal(boards[0].records[0].groups.length, 2);
  const [bar] = boardChart(boards[0]).bars;
  assert.deepEqual([bar.minimum, bar.median, bar.low, bar.high], [59.8, 60, 59.7, 60.1]);
});

test('an empty board still yields a chart scaled to the target', () => {
  const chart = boardChart({
    key: 'k',
    section: null,
    representative: observations([parseSubmission(structuredClone(seed)) as Submission])[0],
    records: [],
    evaluatedGroups: 0,
    hosts: 0,
    revisions: 0,
    closeRatePercent: 2,
  });
  assert.deepEqual(chart.bars, []);
  assert.equal(chart.max, 63);
});
