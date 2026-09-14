import assert from 'node:assert/strict';
import test from 'node:test';
import { ConfigurationDraft } from '../src/config-draft';
import type { Configuration } from '../src/protocol';

const baseline: Configuration = {
  hz: 30, points: 10000, append_count: 1000, curves: 1, waveform_plots: 1, width: 512, height: 512, image_plots: 1,
  view: 'both', waveform_mode: 'replace', image_mode: 'scalar', seed: 42, generation: 1,
};

test('external single-plot selection and resolution survive a local rate-only submission', () => {
  const draft = new ConfigurationDraft();
  draft.receive(baseline);
  draft.change('hz', 60);
  const visible = draft.receive({ ...baseline, view: 'waveform', width: 1024, generation: 2 });
  assert.equal(visible?.hz, 60);
  assert.equal(visible?.view, 'waveform');
  assert.equal(visible?.width, 1024);
  assert.deepEqual(ConfigurationDraft.patch(draft.capture()), { hz: 60 });
});

test('active resolution edits survive polling while pristine fields follow the source', () => {
  const draft = new ConfigurationDraft();
  draft.receive(baseline);
  draft.change('width', 256);
  const visible = draft.receive({ ...baseline, width: 1024, height: 1024, hz: 120, generation: 2 });
  assert.equal(visible?.width, 256);
  assert.equal(visible?.height, 1024);
  assert.equal(visible?.hz, 120);
  assert.deepEqual(ConfigurationDraft.patch(draft.capture()), { width: 256 });
});

test('successful acknowledgement clears only submitted edits; in-flight edits remain pending', () => {
  const draft = new ConfigurationDraft();
  draft.receive(baseline);
  draft.change('hz', 60);
  const submitted = draft.capture();
  draft.change('hz', 90);
  draft.change('height', 256);
  draft.receive({ ...baseline, hz: 60, generation: 2 });
  assert.equal(draft.acknowledge(submitted)?.hz, 90);
  assert.deepEqual(ConfigurationDraft.patch(draft.capture()), { hz: 90, height: 256 });
  const retry = draft.capture();
  draft.receive({ ...baseline, hz: 90, height: 256, generation: 3 });
  draft.acknowledge(retry);
  assert.deepEqual(ConfigurationDraft.patch(draft.capture()), {});
});

test('failed requests retain edits, reverting an edit clears it, and stale generations cannot regress', () => {
  const draft = new ConfigurationDraft();
  draft.receive({ ...baseline, view: 'image', generation: 2 });
  draft.change('hz', 60);
  draft.capture(); // A failed request does not acknowledge its captured edits.
  assert.deepEqual(ConfigurationDraft.patch(draft.capture()), { hz: 60 });
  assert.equal(draft.receive(baseline)?.view, 'image');
  draft.change('hz', 30);
  assert.deepEqual(ConfigurationDraft.patch(draft.capture()), {});
});

test('plot-count fields are editable and patched sparsely like every other field', () => {
  const draft = new ConfigurationDraft();
  draft.receive(baseline);
  draft.change('curves', 3);
  draft.change('waveform_plots', 2);
  draft.change('image_plots', 4);
  draft.change('image_plots', 1);
  assert.deepEqual(ConfigurationDraft.patch(draft.capture()), { curves: 3, waveform_plots: 2 });
  const visible = draft.receive({ ...baseline, image_plots: 3, generation: 2 });
  assert.equal(visible?.curves, 3);
  assert.equal(visible?.image_plots, 3);
});

test('returning to the old confirmed value during a request is retained as a new edit', () => {
  const draft = new ConfigurationDraft();
  draft.receive(baseline);
  draft.change('hz', 60);
  const submitted = draft.capture();
  draft.change('hz', 30, true);
  draft.receive({ ...baseline, hz: 60, generation: 2 });
  assert.equal(draft.acknowledge(submitted)?.hz, 30);
  assert.deepEqual(ConfigurationDraft.patch(draft.capture()), { hz: 30 });
});
