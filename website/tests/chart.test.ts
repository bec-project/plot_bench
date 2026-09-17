import assert from 'node:assert/strict';
import test from 'node:test';
import seed from './fixtures/baseline-campaign.json';
import { boardChart, resourceChart } from '../src/chart';
import { observations, type Submission } from '../src/model';
import { parseSubmission } from '../src/validation';
import { collectWinners, type WinnerBoard } from '../src/winners';

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
  assert.equal(matplotlib.sourceLimited, 1);
  assert.equal(matplotlib.frontendLimited, 1);
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

// A campaign carrying one frontend's runs with paired resource samples per
// repetition, so a board can rank memory and CPU alongside throughput.
function resourced(
  id: string,
  frontend: string,
  host: string,
  rates: (number | null)[],
  memory: (number | null)[],
  cpu: (number | null)[],
): Submission {
  const c = parseSubmission(structuredClone(seed)) as Submission;
  c.id = id;
  c.host.id = host;
  c.host.label = host;
  c.planned_runs = rates.length;
  c.runs = rates.map((rate, i) => {
    const r = structuredClone(c.runs[0]);
    r.id = `${id}-run-${i}`;
    r.frontend = frontend;
    r.repetition = i + 1;
    r.metrics.submitted_hz = rate;
    r.status = rate === null ? 'failed' : 'ok';
    r.samples = rate === null ? 0 : 100;
    r.metrics.rss_peak_mib = memory[i % memory.length];
    r.metrics.cpu_mean_percent = cpu[i % cpu.length];
    return r;
  });
  return c;
}
const memoryChart = (board: WinnerBoard) =>
  resourceChart(board, 'rss_peak_mib', (r) => r.memoryMib);
const cpuChart = (board: WinnerBoard) =>
  resourceChart(board, 'cpu_mean_percent', (r) => r.cpuPercent, 100);

test('resource charts carry the ranked value and the observed repetition range per frontend', () => {
  const board = collectWinners(
    observations([
      resourced('a', 'alpha', 'host-a', [60, 60, 60], [100, 110, 120], [20, 22, 24]),
      resourced('b', 'beta', 'host-b', [50, 50, 50], [300, 300, 300], [80, 80, 80]),
    ]),
  ).boards[0];
  const memory = memoryChart(board);
  assert.equal(memory.hasData, true);
  assert.equal(memory.reference, null);
  assert.deepEqual(
    memory.bars.map((b) => [b.frontend, b.rank, b.value, b.low, b.high, b.samples, b.winner]),
    [
      ['alpha', 1, 110, 100, 120, 3, true],
      ['beta', 2, 300, 300, 300, 3, false],
    ],
  );
  assert.ok(memory.max > 300 && memory.max <= 315);
  const cpu = cpuChart(board);
  // The one-core guide only shows when the axis reaches it; here the peak is 84%.
  assert.equal(cpu.reference, null);
  assert.deepEqual(
    cpu.bars.map((b) => [b.frontend, b.value, b.low, b.high]),
    [
      ['alpha', 22, 20, 24],
      ['beta', 80, 80, 80],
    ],
  );
});

test('the CPU one-core guide appears only when the axis reaches 100 percent', () => {
  const board = collectWinners(
    observations([
      resourced('a', 'alpha', 'host-a', [60, 60, 60], [100, 100, 100], [90, 95, 100]),
      resourced('b', 'beta', 'host-b', [60, 60, 60], [100, 100, 100], [130, 140, 150]),
    ]),
  ).boards[0];
  assert.equal(cpuChart(board).reference, 100);
});

test('an incomplete record shows no bar, and a board with no metric marks no data', () => {
  const board = collectWinners(
    observations([
      resourced('a', 'alpha', 'host-a', [60, 60, 60], [100, 110, 120], [20, 22, 24]),
      // A missing memory sample on a valid repetition leaves the record incomplete.
      resourced('b', 'beta', 'host-b', [60, 60, 60], [300, 300, null], [80, 80, 80]),
    ]),
  ).boards[0];
  const memory = memoryChart(board);
  assert.equal(memory.hasData, true);
  const beta = memory.bars.find((b) => b.frontend === 'beta')!;
  assert.deepEqual([beta.value, beta.low, beta.high, beta.samples], [null, null, null, 0]);
  // Memory unknown suppresses the record's CPU too, so beta's CPU bar is blank.
  assert.equal(cpuChart(board).bars.find((b) => b.frontend === 'beta')!.value, null);

  const none = collectWinners(
    observations([resourced('c', 'gamma', 'host-c', [60, 60, 60], [null], [null])]),
  ).boards[0];
  const empty = memoryChart(none);
  assert.equal(empty.hasData, false);
  assert.equal(empty.bars[0].value, null);
});

test('an empty board yields resource charts with no bars and no data', () => {
  const board: WinnerBoard = {
    key: 'k',
    section: null,
    representative: observations([parseSubmission(structuredClone(seed)) as Submission])[0],
    records: [],
    evaluatedGroups: 0,
    hosts: 0,
    revisions: 0,
    closeRatePercent: 2,
  };
  const memory = memoryChart(board);
  assert.deepEqual(memory.bars, []);
  assert.equal(memory.hasData, false);
  assert.equal(memory.reference, null);
});
