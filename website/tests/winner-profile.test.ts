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

test('profile shares the ranking normalization, separately for each throughput band', () => {
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
  assert.equal(alpha.area, 1);

  const beta = byName(data, 'beta');
  assert.deepEqual([beta.gThroughput, beta.gRss, beta.gCpu], [1, 0.5, 0.5]);
  assert.equal(beta.inBand, true);
  assert.equal(beta.area, 5 / 12);

  const gamma = byName(data, 'gamma');
  assert.deepEqual([gamma.gThroughput, gamma.gRss, gamma.gCpu], [0.5, 1, 1]);
  // 30/60 Hz falls outside the top throughput band.
  assert.equal(gamma.inBand, false);

  // Each inner hull uses only records in the highlighted band.
  assert.deepEqual(data.worstGoodness, {
    0: { throughput: 1, rss: 0.5, cpu: 0.5 },
    1: { throughput: 0.5, rss: 1, cpu: 1 },
  });
});

test('a frontend missing a resource is excluded from the radar and its scales', () => {
  const board = collectWinners(
    observations([
      resourced('a', 'alpha', 'host-a', [60, 60, 60], [100, 100, 100], [20, 20, 20]),
      resourced('b', 'beta', 'host-b', [60, 60, 60], [80, 80, null], [10, 10, 10]),
    ]),
  ).boards[0];
  const data = profileData(board);
  assert.deepEqual(
    data.points.map((p) => p.frontend),
    ['alpha'],
  );
  assert.equal(data.points[0].area, 1);
});

test('equal-area ties show one real configuration rather than combined best metrics', () => {
  const board = collectWinners(
    observations([
      resourced('a', 'alpha', 'host-a', [60], [100], [20]),
      resourced('z', 'alpha', 'host-z', [60.1], [200], [10]),
      resourced('b', 'beta', 'host-b', [60], [100], [20]),
    ]),
  ).boards[0];
  const record = board.records.find((r) => r.frontend === 'alpha')!;
  assert.equal(record.groups.length, 2);
  assert.equal(record.representativeGroup.representative.campaign.host.id, 'host-z');
  assert.equal(record.groups[0].representative.campaign.host.id, 'host-a');
  const p = byName(profileData(board), 'alpha');
  assert.deepEqual([p.throughput, p.rss, p.cpu], [60.1, 200, 10]);
  assert.deepEqual([p.gThroughput, p.gRss, p.gCpu], [1, 0.5, 1]);
  assert.equal(p.area, 2 / 3);
  assert.deepEqual(
    board.records.map((r) => r.rank),
    [1, 1],
  );

  // Geometric area of its rendered polygon must match the ranking score.
  const points = [p.gThroughput, p.gRss, p.gCpu].map((g, i) => {
    const angle = ((-90 + 120 * i) * Math.PI) / 180;
    return [g * Math.cos(angle), g * Math.sin(angle)];
  });
  const area =
    Math.abs(
      points.reduce((sum, point, i) => {
        const next = points[(i + 1) % points.length];
        return sum + point[0] * next[1] - point[1] * next[0];
      }, 0),
    ) / 2;
  assert.ok(Math.abs(area / ((3 * Math.sqrt(3)) / 4) - p.area) < 1e-12);
});
