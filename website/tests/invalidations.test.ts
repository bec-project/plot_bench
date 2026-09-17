import assert from 'node:assert/strict';
import test from 'node:test';
import seed from './fixtures/baseline-campaign.json';
import { parseSubmission } from '../src/validation';
import { observations, type Submission } from '../src/model';
import { isInvalidated, validObservations, INVALIDATIONS } from '../src/invalidations';

const OLD_PLOTLY = 'Plotly scattergl (WebGL) + heatmap/image (Plotly raster traces)';
const NEW_PLOTLY = 'Plotly scattergl (WebGL) + precolored image.source (PNG raster traces)';

function withRuns(specs: { frontend: string; renderer: string | null }[]): Submission {
  const c = parseSubmission(structuredClone(seed));
  c.runs = specs.map((spec, i) => {
    const r = structuredClone(c.runs[0]);
    r.id = `run-${i + 1}`;
    r.frontend = spec.frontend;
    r.context = { ...r.context, renderer: spec.renderer };
    return r;
  });
  return c;
}

test('the pre-optimization plotly renderer is superseded; the optimized one is not', () => {
  const c = withRuns([
    { frontend: 'plotly', renderer: OLD_PLOTLY },
    { frontend: 'plotly', renderer: NEW_PLOTLY },
    { frontend: 'pyqtgraph', renderer: 'QPainter raster viewport' },
  ]);
  const [oldPlotly, newPlotly, pyqt] = observations([c]);
  assert.equal(isInvalidated(oldPlotly), true);
  assert.equal(isInvalidated(newPlotly), false);
  assert.equal(isInvalidated(pyqt), false);
});

test('validObservations drops only superseded plotly runs, keeping every other run', () => {
  const c = withRuns([
    { frontend: 'plotly', renderer: OLD_PLOTLY },
    { frontend: 'plotly', renderer: NEW_PLOTLY },
    { frontend: 'matplotlib', renderer: 'Matplotlib QtAgg with reusable artists and blitting' },
    { frontend: 'plotly', renderer: null },
  ]);
  const kept = validObservations(observations([c]));
  const renderers = kept.map((o) => o.run.context.renderer);
  assert.equal(kept.length, 3);
  assert.ok(!renderers.includes(OLD_PLOTLY));
  assert.ok(renderers.includes(NEW_PLOTLY));
  // An unknown renderer is not assumed superseded, only the recorded old one.
  assert.ok(kept.some((o) => o.run.frontend === 'plotly' && o.run.context.renderer === null));
});

test('the plotly rule matches the recorded pre-optimization renderer only', () => {
  const rule = INVALIDATIONS.find((r) => r.frontend === 'plotly');
  assert.ok(rule);
  assert.ok(OLD_PLOTLY.includes(rule.supersededRenderer));
  assert.ok(!NEW_PLOTLY.includes(rule.supersededRenderer));
});
