import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { fetchEnvironment, fetchInitial, fetchPresets, preview, previewRaw, saveSuite } from './api';
import { GROUP_TIPS, OPTION_TIPS } from './config-fields';
import { CommandLine } from './components/commands';
import { ChipGroup, NumberField, TextField } from './components/fields';
import { InfoTip } from './components/infotip';
import { Launcher } from './components/launcher';
import { PlanPreview } from './components/preview';
import { PresetGallery } from './components/presets';
import { RawJson } from './components/rawjson';
import { GroupCard, WorkloadCard } from './components/workloads';
import type { EnvironmentStatus, InitialData, Kind, Plan, Preset, SaveResult, Suite } from './types';

const TIMINGS: Array<{ key: keyof Suite; label: string; hint: string; decimal: boolean; tip: string }> = [
  { key: 'warmup_seconds', label: 'Warmup', hint: 'seconds', decimal: true, tip: 'Unmeasured seconds before each run so the renderer reaches steady state.' },
  { key: 'measurement_seconds', label: 'Measured', hint: 'seconds', decimal: true, tip: 'The measured window per run, in seconds.' },
  { key: 'cooldown_seconds', label: 'Cooldown', hint: 'seconds', decimal: true, tip: 'Idle seconds after each run before the next starts.' },
  { key: 'repetitions', label: 'Repetitions', hint: 'per combination', decimal: false, tip: 'How many times each workload combination runs.' },
  { key: 'order_seed', label: 'Run order seed', hint: 'shuffle', decimal: false, tip: 'Seed for the deterministic shuffle of run order across the campaign.' },
];

function timingDefaults(kind: Kind): Record<string, number> {
  const probe = kind === 'probe';
  return {
    warmup_seconds: probe ? 2 : 5,
    measurement_seconds: probe ? 10 : 30,
    cooldown_seconds: probe ? 0.5 : 1,
    repetitions: 3,
    order_seed: 42,
  };
}

function slugify(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

function uniqueName(suite: Suite, prefix: string): string {
  const names = new Set([...(suite.cases ?? []), ...(suite.case_groups ?? [])].map((item) => item.name));
  let n = 1;
  while (names.has(`${prefix}-${n}`)) n += 1;
  return `${prefix}-${n}`;
}

function blankSuite(): Suite {
  return {
    name: 'custom-suite',
    frontends: ['pyqtgraph'],
    backends: ['rust'],
    modes: ['stream'],
    repetitions: 1,
    cases: [{ name: 'workload-1', config: { view: 'waveform' } }],
  };
}

export function App() {
  const [options, setOptions] = useState<InitialData | null>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [env, setEnv] = useState<EnvironmentStatus | null>(null);
  const [suite, setSuite] = useState<Suite | null>(null);
  const [kind, setKind] = useState<Kind>('run');
  const [active, setActive] = useState<string | null>(null);
  // The suite/path a Save or preset-load established, so the live command can point
  // at an existing file when unchanged, or the pending save target once edited.
  const [loadedSuite, setLoadedSuite] = useState<Suite | null>(null);
  const [loadedPath, setLoadedPath] = useState<string | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [filename, setFilename] = useState('my-suite');
  const [saved, setSaved] = useState<SaveResult | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const revision = useRef(0);
  const importInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchInitial();
        setOptions(data);
        setSuite(data.suite);
        setPresets(await fetchPresets());
        setEnv(await fetchEnvironment());
      } catch (failure: any) {
        setLoadError(`${failure.message ?? failure} Restart the matrix editor and reload this page.`);
      }
    })();
  }, []);

  useEffect(() => {
    if (!suite) return;
    const rev = ++revision.current;
    setPending(true);
    const timer = setTimeout(async () => {
      try {
        const result = await preview(suite, kind);
        if (rev !== revision.current) return;
        setPlan(result);
        setPreviewError(null);
      } catch (failure: any) {
        if (rev !== revision.current) return;
        setPlan(null);
        setPreviewError(failure.message ?? String(failure));
      } finally {
        if (rev === revision.current) setPending(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [suite, kind]);

  // Any edit invalidates a previous save; the launcher panel must not go stale.
  useEffect(() => {
    setSaved(null);
    setSaveError(null);
  }, [suite, kind]);

  const defaults = options?.config ?? {};
  const tDefaults = useMemo(() => timingDefaults(kind), [kind]);

  if (loadError) {
    return (
      <main>
        <p class="alert" role="alert">{loadError}</p>
      </main>
    );
  }
  if (!options || !suite) {
    return <main><p class="muted">Loading the matrix editor…</p></main>;
  }

  const patch = (next: Partial<Suite>) => setSuite({ ...suite, ...next });

  const setSelection = (key: 'frontends' | 'backends' | 'modes', fallback: string[]) =>
    (value: string, checked: boolean) => {
      const current = new Set(suite[key] ?? fallback);
      if (checked) current.add(value);
      else current.delete(value);
      patch({ [key]: [...current] } as Partial<Suite>);
    };

  const setField = (key: keyof Suite, value: number | string | undefined) => {
    const next = { ...suite };
    if (value === undefined || value === '') delete next[key];
    else (next as any)[key] = value;
    setSuite(next);
  };

  const applyRaw = async (text: string): Promise<string | null> => {
    try {
      const result = await previewRaw(text, kind);
      setSuite(result.suite);
      setActive(null);
      setLoadedSuite(null);
      setLoadedPath(null);
      return null;
    } catch (failure: any) {
      return failure.message ?? String(failure);
    }
  };

  const pickPreset = (preset: Preset) => {
    setSuite(preset.suite);
    setKind(preset.kind);
    setActive(preset.path);
    setLoadedSuite(preset.suite);
    setLoadedPath(preset.path);
    if (preset.filename.endsWith('.json')) setFilename(preset.filename.replace(/\.json$/, ''));
  };

  const startBlank = () => {
    setSuite(blankSuite());
    setKind('run');
    setActive('blank');
    setLoadedSuite(null);
    setLoadedPath(null);
    setFilename('my-suite');
  };

  const exportJson = () => {
    const payload = plan?.suite ?? suite;
    const blob = new Blob([JSON.stringify(payload, null, 2) + '\n'], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${filename || 'my-suite'}.json`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const importJson = async (event: Event) => {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    if (file.size > 1024 * 1024) {
      setPreviewError('Suite JSON must be at most 1 MiB.');
      return;
    }
    const message = await applyRaw(await file.text());
    if (message) setPreviewError(message);
    if (importInput.current) importInput.current.value = '';
  };

  const save = async () => {
    if (!plan) return;
    try {
      const result = await saveSuite(plan.suite, filename, kind);
      setSaved(result);
      setSaveError(null);
      setActive(result.path);
      setLoadedSuite(suite);
      setLoadedPath(result.path);
      setPresets(await fetchPresets());
    } catch (failure: any) {
      setSaved(null);
      setSaveError(failure.message ?? String(failure));
    }
  };

  const probe = kind === 'probe';

  // The live command targets the loaded file while it is unchanged, otherwise the
  // pending save path derived from the file-name field.
  const unchanged = loadedPath !== null && loadedSuite !== null
    && JSON.stringify(suite) === JSON.stringify(loadedSuite);
  const slug = slugify(filename) || 'my-suite';
  const runPath = unchanged ? (loadedPath as string) : `scenarios_custom/${slug}.json`;
  const runStem = runPath.replace(/^.*\//, '').replace(/\.json$/, '') || 'my-suite';
  const command = kind === 'run' ? 'run' : 'probe';
  const liveCommands = [
    { label: 'Preview', command: `./scripts/plotbench ${command} --suite ${runPath} --dry-run` },
    { label: 'Full run', command: `./scripts/plotbench ${command} --suite ${runPath} --output results/${runStem}` },
  ];

  // Which selected components are not installed, and the command that installs them.
  const recheckEnv = async () => setEnv(await fetchEnvironment());
  const selectedFrontends = probe ? [] : suite.frontends ?? options.frontends;
  const selectedBackends = suite.backends ?? [options.default_backend];
  const missing: Array<{ name: string; setup: string | null }> = [];
  if (env) {
    for (const name of selectedFrontends) {
      const status = env.frontends[name];
      if (status && !status.installed) missing.push({ name, setup: status.setup });
    }
    for (const name of selectedBackends) {
      const status = env.backends[name];
      if (status && !status.installed) missing.push({ name, setup: status.setup });
    }
  }
  const setupNames = [...new Set(missing.map((item) => item.setup).filter(Boolean))] as string[];
  const installCommand = setupNames.length ? `./scripts/setup ${setupNames.join(' ')}` : '';

  return (
    <main>
      <header class="app-header">
        <p class="eyebrow">PLOTBENCH</p>
        <h1>Build a benchmark</h1>
        <p class="lede">
          Pick a starting point, shape the workloads, preview the exact run order, then save a suite for the CLI.
        </p>
        <p class="muted small">This editor runs locally and never launches measurements. Saving only writes JSON.</p>
      </header>

      <section class="panel">
        <div class="step"><span class="step-no">1</span><h2>Start from</h2></div>
        <p class="muted small">Presets are read-only starting points. Load one, then adjust — your changes are saved separately.</p>
        <PresetGallery presets={presets} active={active} onPick={pickPreset} onBlank={startBlank} />
      </section>

      <section class="panel">
        <div class="step"><span class="step-no">2</span><h2>Execution</h2></div>
        <div class="field-grid setup-grid">
          <TextField label="Suite name" value={suite.name ?? ''} placeholder="Describe this campaign" onInput={(v) => setField('name', v)} />
          <div class="field">
            <span class="field-label">Preview command<InfoTip text={GROUP_TIPS.kind} /></span>
            <select id="kind" value={kind} onChange={(e) => setKind((e.target as HTMLSelectElement).value as Kind)}>
              <option value="run">Frontend benchmark (run)</option>
              <option value="probe">Source receiver probe</option>
            </select>
          </div>
          <TextField label="Display context" hint="recorded with results" value={suite.display_context ?? ''} placeholder="Monitor, refresh rate, scaling, placement" onInput={(v) => setField('display_context', v)} />
        </div>

        <div class="selections">
          <ChipGroup legend="Frontends" legendTip={GROUP_TIPS.frontends} tips={OPTION_TIPS} status={env?.frontends} options={options.frontends} selected={suite.frontends ?? options.frontends} disabled={probe} onToggle={setSelection('frontends', options.frontends)} />
          <ChipGroup legend="Source backends" legendTip={GROUP_TIPS.backends} tips={OPTION_TIPS} status={env?.backends} options={options.backends} selected={suite.backends ?? [options.default_backend]} onToggle={setSelection('backends', [options.default_backend])} />
          <ChipGroup legend="Delivery modes" legendTip={GROUP_TIPS.modes} tips={OPTION_TIPS} options={options.modes} selected={suite.modes ?? options.modes} disabled={probe} onToggle={setSelection('modes', options.modes)} />
        </div>
        {probe ? <p class="muted small">Probe measures the source and delivery only; frontend and mode selections are ignored.</p> : null}
        {missing.length ? (
          <div class="install-hint">
            <div class="install-head">
              <span class="install-title">
                ⚠ Not installed: {missing.map((item) => item.name).join(', ')}
              </span>
              <button type="button" class="btn-soft" onClick={recheckEnv}>Re-check</button>
            </div>
            <CommandLine label="Install" command={installCommand} />
            <p class="muted small">Run this in your terminal, then Re-check. Verify with <code>./scripts/plotbench doctor</code>.</p>
          </div>
        ) : null}

        <div class="field-grid timings-grid">
          {TIMINGS.map((t) => (
            <NumberField
              label={t.label}
              hint={t.hint}
              tip={t.tip}
              allowDecimal={t.decimal}
              value={suite[t.key] as number | undefined}
              placeholder={tDefaults[t.key as string]}
              onChange={(v) => setField(t.key, v)}
            />
          ))}
        </div>
      </section>

      <section class="panel">
        <div class="step"><span class="step-no">3</span><h2>Workloads</h2></div>
        <div class="sub-head">
          <p class="muted small">Each workload is one named case. Empty fields use the source defaults shown as placeholders.</p>
          <button type="button" class="btn-soft" onClick={() => patch({ cases: [...(suite.cases ?? []), { name: uniqueName(suite, 'workload'), config: { view: 'waveform' } }] })}>+ Add workload</button>
        </div>
        <div id="cases">
          {(suite.cases ?? []).map((item, index) => (
            <WorkloadCard
              item={item}
              defaults={defaults}
              onChange={(next) => patch({ cases: (suite.cases ?? []).map((c, i) => (i === index ? next : c)) })}
              onRemove={() => patch({ cases: (suite.cases ?? []).filter((_, i) => i !== index) })}
            />
          ))}
        </div>

        <div class="sub-head groups-head">
          <p class="muted small">Groups expand every combination of their matrix axes. Axes override the base workload.</p>
          <button type="button" class="btn-soft" onClick={() => patch({ case_groups: [...(suite.case_groups ?? []), { name: uniqueName(suite, 'group'), base: { view: 'waveform' }, matrix: { points: [10000, 100000] } }] })}>+ Add group</button>
        </div>
        <div id="groups">
          {(suite.case_groups ?? []).map((group, index) => (
            <GroupCard
              group={group}
              defaults={defaults}
              onChange={(next) => patch({ case_groups: (suite.case_groups ?? []).map((g, i) => (i === index ? next : g)) })}
              onRemove={() => patch({ case_groups: (suite.case_groups ?? []).filter((_, i) => i !== index) })}
            />
          ))}
        </div>
      </section>

      <PlanPreview
        plan={plan}
        error={previewError}
        pending={pending}
        commands={liveCommands}
        needsSave={!unchanged}
      />

      {saved ? <Launcher result={saved} onDismiss={() => setSaved(null)} /> : null}

      <RawJson suite={suite} onApply={applyRaw} />

      <div class="action-bar">
        <div class="save-controls">
          <label class="field save-name">
            <span class="field-label">File name</span>
            <div class="save-name-row">
              <span class="prefix">scenarios_custom/</span>
              <input type="text" value={filename} aria-label="File name" onInput={(e) => setFilename((e.target as HTMLInputElement).value)} />
              <span class="suffix">.json</span>
            </div>
          </label>
          <button type="button" class="btn-primary" disabled={!plan || !filename.trim()} onClick={save} title={!plan ? 'Fix the preview errors first' : undefined}>Save to scenarios_custom</button>
        </div>
        <div class="action-right">
          <button type="button" class="btn-soft" disabled={!plan} onClick={exportJson}>Export JSON</button>
          <label class="btn-soft file-btn">
            Import JSON
            <input ref={importInput} type="file" accept=".json,application/json" onChange={importJson} />
          </label>
        </div>
      </div>
      {saveError ? <p class="alert action-alert" role="alert">{saveError}</p> : null}
    </main>
  );
}
