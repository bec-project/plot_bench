import assert from 'node:assert/strict';
import test from 'node:test';
import seed from './fixtures/baseline-campaign.json';
import { groupObservations } from '../src/aggregation';
import { observations, type Submission } from '../src/model';
import { compareGroups, compareRuns, groupOrder } from '../src/ordering';
import { parseSubmission } from '../src/validation';

type Rate = number | null | [string, number];
function campaign(id: string, day: string, rates: Rate[], frontend = 'pyqtgraph') {
  const c = structuredClone(parseSubmission(seed)) as Submission;
  c.id = id;
  c.recorded_at = `2026-09-${day}T12:00:00Z`;
  c.planned_runs = rates.length;
  c.runs = rates.map((entry, i) => {
    const r = structuredClone(c.runs[0]);
    const [status, rate] = Array.isArray(entry) ? entry : [entry === null ? 'failed' : 'ok', entry];
    r.id = `run-${i + 1}`;
    r.frontend = frontend;
    r.repetition = i + 1;
    r.metrics.submitted_hz = rate;
    r.status = status;
    r.samples = rate === null ? 0 : 100;
    return r;
  });
  return c;
}

test('unknown sort values fall back to the median-rate order', () => {
  assert.equal(groupOrder(null), 'rate');
  assert.equal(groupOrder('nope'), 'rate');
  assert.equal(groupOrder('recent'), 'recent');
  assert.equal(groupOrder('frontend'), 'frontend');
});

test('groups sort by median rate first, then recency; missing rates go last', () => {
  const groups = groupObservations(
    observations([
      campaign('slow-new', '20', [30, 30, 30], 'alpha'),
      campaign('fast-old', '10', [60, 60, 60], 'beta'),
      campaign('failed', '15', [null, null, null], 'gamma'),
      campaign('mid', '12', [45, 45, 45], 'delta'),
    ]),
  );
  const names = (order: 'rate' | 'recent' | 'frontend') =>
    [...groups].sort(compareGroups(order)).map((g) => g.representative.run.frontend);
  assert.deepEqual(names('rate'), ['beta', 'delta', 'alpha', 'gamma']);
  assert.deepEqual(names('recent'), ['alpha', 'gamma', 'delta', 'beta']);
  assert.deepEqual(names('frontend'), ['alpha', 'beta', 'delta', 'gamma']);
});

test('individual runs follow the same order; runs without a valid rate come last', () => {
  // A run downgraded after measuring keeps its recorded rate but is not valid.
  const runs = observations([
    campaign('one', '14', [50, null, 60, ['incomplete-telemetry', 59], 55], 'alpha'),
  ]);
  assert.deepEqual(
    [...runs].sort(compareRuns('rate')).map((o) => [o.run.status, o.run.metrics.submitted_hz]),
    [
      ['ok', 60],
      ['ok', 55],
      ['ok', 50],
      ['failed', null],
      ['incomplete-telemetry', 59],
    ],
  );
  assert.deepEqual(
    [...runs].sort(compareRuns('recent')).map((o) => o.run.repetition),
    [1, 2, 3, 4, 5],
  );
});
