import { useEffect, useRef, useState } from 'preact/hooks';
import { ConfigFields, Field } from './components/fields';
import { ViewSegmented } from './components/view-segmented';
import type { Config, SourceHealth } from './types';

// The workload fields this page owns; `generation` is source-managed and excluded.
const EDITABLE = [
  'hz',
  'view',
  'points',
  'waveform_mode',
  'append_count',
  'image_mode',
  'width',
  'height',
  'seed',
];

const RATE_PRESETS = [1, 5, 10, 15, 24, 30, 60, 90, 120];
const RESOLUTION_PRESETS: Array<{ group: string; items: Array<{ label: string; value: string }> }> = [
  {
    group: 'Square images',
    items: [
      { label: '256 × 256', value: '256x256' },
      { label: '512 × 512', value: '512x512' },
      { label: '1024 × 1024', value: '1024x1024' },
      { label: '2048 × 2048', value: '2048x2048' },
      { label: '4096 × 4096', value: '4096x4096' },
    ],
  },
  {
    group: 'Video sizes · width × height',
    items: [
      { label: '640 × 480 · VGA', value: '640x480' },
      { label: '1280 × 720 · HD', value: '1280x720' },
      { label: '1920 × 1080 · Full HD', value: '1920x1080' },
      { label: '3840 × 2160 · 4K UHD', value: '3840x2160' },
    ],
  },
];

async function getJSON(path: string): Promise<any> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function backendLabel(backend: string | undefined): string {
  const name = backend === 'rust' ? 'Rust' : backend === 'python' || !backend ? 'Python' : backend;
  return `${name} · shared deterministic source`;
}

export function ControlsApp() {
  const [confirmed, setConfirmed] = useState<Config | null>(null);
  const [draft, setDraft] = useState<Config | null>(null);
  const [health, setHealth] = useState<SourceHealth | null>(null);
  const [healthError, setHealthError] = useState('');
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState('');
  const [loadError, setLoadError] = useState('');
  const confirmedRef = useRef<Config | null>(null);

  // Adopt a server config: pristine (unedited or cleared) fields follow it; a
  // field the user has changed keeps its edit until applied.
  const applyServerConfig = (cfg: Config) => {
    const prev = confirmedRef.current;
    confirmedRef.current = cfg;
    setConfirmed(cfg);
    setDraft((current) => {
      const base = current ?? {};
      const next: Config = { ...base };
      for (const key of EDITABLE) {
        const value = base[key];
        const pristine = value === undefined || value === '' || (prev != null && value === prev[key]);
        if (pristine) next[key] = cfg[key];
      }
      return next;
    });
  };

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const result: SourceHealth = await getJSON('/api/health');
        if (!active) return;
        setHealth(result);
        setHealthError('');
        if (result.config) applyServerConfig(result.config);
      } catch (failure: any) {
        if (active) setHealthError(failure.message ?? String(failure));
      }
    };
    (async () => {
      try {
        applyServerConfig(await getJSON('/api/config'));
      } catch (failure: any) {
        if (active) setLoadError(failure.message ?? String(failure));
      }
    })();
    poll();
    const timer = setInterval(poll, 1000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  if (loadError) {
    return (
      <main>
        <p class="alert" role="alert">
          {loadError} Is a source running? Start one with{' '}
          <code>./scripts/plotbench serve</code>.
        </p>
      </main>
    );
  }
  if (!draft || !confirmed) {
    return (
      <main>
        <p class="muted">Connecting to the source…</p>
      </main>
    );
  }

  const dirty = EDITABLE.filter(
    (key) => draft[key] !== undefined && draft[key] !== '' && draft[key] !== confirmed[key]
  );

  const rate = String(Number(draft.hz));
  const resolution = `${Number(draft.width)}x${Number(draft.height)}`;
  const rateValue = RATE_PRESETS.map(String).includes(rate) ? rate : '';
  const resolutionValue = RESOLUTION_PRESETS.flatMap((group) => group.items).some(
    (item) => item.value === resolution
  )
    ? resolution
    : '';
  const backend = health?.backend === 'rust' ? 'rust' : 'python';
  const sourceUrl = `'${window.location.origin.replaceAll("'", "'\\''")}'`;

  const apply = async () => {
    if (!dirty.length || applying) return;
    const patch: Config = {};
    for (const key of dirty) patch[key] = draft[key];
    setApplying(true);
    setError('');
    try {
      const response = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
      // Keep edits made while the request was in flight; adopt the rest.
      setDraft((current) => {
        const next: Config = { ...(current ?? {}) };
        for (const key of Object.keys(patch)) if (next[key] === patch[key]) next[key] = result[key];
        return next;
      });
      confirmedRef.current = result;
      setConfirmed(result);
    } catch (failure: any) {
      setError(failure.message ?? String(failure));
    } finally {
      setApplying(false);
    }
  };

  return (
    <main>
      <header class="controls-header">
        <div>
          <p class="eyebrow">PLOTTING BENCHMARK</p>
          <h1>Source controls</h1>
        </div>
        <span class="backend-badge">{backendLabel(health?.backend)}</span>
      </header>
      <p class="lede">
        One workload for every frontend. Changes apply to connected streaming demos; restart replay
        demos to load the new workload.
      </p>

      <section class="panel">
        <div class="panel-head">
          <h2>Workload</h2>
          <span class="muted small">Waveforms &amp; images · up to 120 Hz</span>
        </div>

        <div class="field-grid preset-row">
          <Field label="Update rate preset" tip="Fills the target rate below. Choose Custom to type any value.">
            <select
              aria-label="Update rate preset"
              value={rateValue}
              onChange={(event) => {
                const value = (event.target as HTMLSelectElement).value;
                if (value) setDraft({ ...draft, hz: Number(value) });
              }}
            >
              <option value="">Custom rate</option>
              {RATE_PRESETS.map((value) => (
                <option value={String(value)}>{value} Hz</option>
              ))}
            </select>
          </Field>
          <Field label="Image resolution preset" tip="Fills image width and height below.">
            <select
              aria-label="Image resolution preset"
              value={resolutionValue}
              onChange={(event) => {
                const value = (event.target as HTMLSelectElement).value;
                if (!value) return;
                const [width, height] = value.split('x').map(Number);
                setDraft({ ...draft, width, height });
              }}
            >
              <option value="">Custom resolution</option>
              {RESOLUTION_PRESETS.map((group) => (
                <optgroup label={group.group}>
                  {group.items.map((item) => (
                    <option value={item.value}>{item.label}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </Field>
        </div>

        <div class="workload-view">
          <span class="field-label">Plots</span>
          <ViewSegmented value={String(draft.view)} onChange={(view) => setDraft({ ...draft, view })} />
        </div>

        <ConfigFields config={draft} defaults={confirmed} onChange={setDraft} />

        <div class="controls-actions">
          <button type="button" class="btn-primary" disabled={applying || !dirty.length} onClick={apply}>
            {applying ? 'Applying…' : dirty.length ? `Apply workload (${dirty.length})` : 'Apply workload'}
          </button>
          <span class="muted small">Use the benchmark CLI for recorded runs with fixed settings.</span>
          {error ? <span class="alert inline-alert" role="alert">{error}</span> : null}
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>Source activity</h2>
          <span class="muted small">Refreshes every second</span>
        </div>
        {healthError ? (
          <p class="alert" role="alert">{healthError}</p>
        ) : health ? (
          <div class="status-grid">
            <Stat label="Status" value={health.status.toUpperCase()} />
            <Stat label="Streaming clients" value={String(health.clients)} />
            <Stat label="Frames generated" value={health.generated.toLocaleString()} />
            <Stat label="Target rate" value={`${draft.hz} Hz`} />
            <Stat label="Missed deadlines" value={health.deadline_misses.toLocaleString()} />
            <Stat label="Replaced queued frames" value={health.mailbox_drops.toLocaleString()} />
          </div>
        ) : (
          <p class="muted">Connecting…</p>
        )}
        {health?.error ? <p class="alert" role="alert">{health.error}</p> : null}
        {health?.output ? <p class="muted small output-path">Raw measurements: <code>{health.output}</code></p> : null}
      </section>

      <footer class="controls-footer">
        <span>
          With Plotly installed, connect to this source with{' '}
          <code>./scripts/plotbench demo plotly --backend {backend} --url {sourceUrl}</code>.
        </span>
        <span>Source rate is independent of display refresh.</span>
      </footer>
    </main>
  );
}

function Stat(props: { label: string; value: string }) {
  return (
    <div class="stat">
      <span class="stat-label">{props.label}</span>
      <span class="stat-value">{props.value}</span>
    </div>
  );
}
