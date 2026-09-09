import type { Preset } from '../types';

function scope(preset: Preset): string {
  const runs = preset.run_count.toLocaleString();
  const cases = preset.case_count.toLocaleString();
  return `${cases} workload${preset.case_count === 1 ? '' : 's'} · ${runs} run${preset.run_count === 1 ? '' : 's'} · ~${preset.minimum_minutes.toFixed(1)} min`;
}

function PresetCard(props: { preset: Preset; active: string | null; onPick: (preset: Preset) => void }) {
  const { preset } = props;
  const custom = preset.source === 'custom';
  const fallback = custom ? 'Saved from the editor.' : 'No description.';
  return (
    <button
      type="button"
      class={
        (custom ? 'preset preset-custom' : 'preset') +
        (props.active === preset.path ? ' preset-on' : '')
      }
      disabled={Boolean(preset.error)}
      onClick={() => props.onPick(preset)}
      title={preset.error ? preset.error : preset.path}
    >
      <span class="preset-name">
        {preset.name}
        {custom ? <span class="badge badge-custom">custom</span> : null}
        {preset.kind === 'probe' ? <span class="badge">probe</span> : null}
      </span>
      <span class="preset-desc">
        {preset.error ? `Unavailable: ${preset.error}` : preset.description || fallback}
      </span>
      <span class="preset-scope">{preset.error ? preset.filename : scope(preset)}</span>
    </button>
  );
}

export function PresetGallery(props: {
  presets: Preset[];
  active: string | null;
  onPick: (preset: Preset) => void;
  onBlank: () => void;
}) {
  const custom = props.presets.filter((preset) => preset.source === 'custom');
  const bundled = props.presets.filter((preset) => preset.source !== 'custom');
  return (
    <>
      {custom.length ? (
        <details class="custom-box" open>
          <summary>
            <span class="custom-summary">Your saved suites</span>
            <span class="badge badge-custom">scenarios_custom</span>
            <span class="custom-count">{custom.length}</span>
          </summary>
          <div class="preset-grid">
            {custom.map((preset) => (
              <PresetCard preset={preset} active={props.active} onPick={props.onPick} />
            ))}
          </div>
        </details>
      ) : null}
      <div class="preset-grid">
        <button
          type="button"
          class={props.active === 'blank' ? 'preset preset-on preset-blank' : 'preset preset-blank'}
          onClick={props.onBlank}
        >
          <span class="preset-name">Blank</span>
          <span class="preset-desc">Start empty: one waveform workload at the source defaults.</span>
          <span class="preset-scope">Build from scratch</span>
        </button>
        {bundled.map((preset) => (
          <PresetCard preset={preset} active={props.active} onPick={props.onPick} />
        ))}
      </div>
    </>
  );
}
