import assert from 'node:assert/strict';
import test from 'node:test';
import seed from './fixtures/baseline-campaign.json';
import { observations, type Submission } from '../src/model';
import { parseSubmission } from '../src/validation';
import { collectWinners } from '../src/winners';
import { profileData } from '../src/winner-profile';

// Build a campaign of repetitions carrying a rate, RSS and CPU each, so a board
// derived from it exercises the profile normalization end to end.
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

const byName = (data: ReturnType<typeof profileData>, frontend: string) =>
  data.points.find((p) => p.frontend === frontend)!;

test('profile normalizes throughput to the target and resources to the lightest frontend', () => {
  const board = collectWinners(
    observations([
      resourced('a', 'alpha', 'host-a', [60, 60, 60], [100, 100, 100], [20, 20, 20]),
      resourced('b', 'beta', 'host-b', [60, 60, 60], [200, 200, 200], [40, 40, 40]),
      resourced('c', 'gamma', 'host-c', [30, 30, 30], [400, 400, 400], [80, 80, 80]),
    ]),
  ).boards[0];
  const data = profileData(board);

  assert.equal(data.target, 60);
  const alpha = byName(data, 'alpha');
  assert.deepEqual([alpha.gThroughput, alpha.gRss, alpha.gCpu], [1, 1, 1]);
  assert.equal(alpha.winner, true);

  const beta = byName(data, 'beta');
  assert.deepEqual([beta.gThroughput, beta.gRss, beta.gCpu], [1, 0.5, 0.5]);
  assert.equal(beta.inBand, true);

  const gamma = byName(data, 'gamma');
  assert.deepEqual([gamma.gThroughput, gamma.gRss, gamma.gCpu], [0.5, 0.25, 0.25]);
  // 30/60 Hz falls outside the top throughput band.
  assert.equal(gamma.inBand, false);

  // The inner hull is the worst goodness seen on each axis.
  assert.deepEqual(data.worstGoodness, { throughput: 0.5, rss: 0.25, cpu: 0.25 });
});

test('a frontend missing a resource is null-normalized so the radar plots it at the centre', () => {
  const board = collectWinners(
    observations([
      resourced('a', 'alpha', 'host-a', [60, 60, 60], [100, 100, 100], [20, 20, 20]),
      resourced('b', 'beta', 'host-b', [60, 60, 60], [80, 80, null], [10, 10, 10]),
    ]),
  ).boards[0];
  const data = profileData(board);
  const beta = byName(data, 'beta');
  // A missing RSS repetition leaves the record's RSS unknown, and an unknown RSS
  // suppresses the record's CPU too, so both axes go to null (the radar plots
  // them at the centre). Throughput still normalizes.
  assert.deepEqual([beta.rss, beta.gRss], [null, null]);
  assert.deepEqual([beta.cpu, beta.gCpu], [null, null]);
  assert.equal(beta.gThroughput, 1);
});
