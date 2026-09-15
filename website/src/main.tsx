import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { exportSummary, suggestSubmission, type SubmissionDefaults } from './export';
import { MAX_SUBMISSION_BYTES, validateCatalog } from './validation';
import { BASELINE, SECTIONS, sectionOf } from './baseline';
import { OverallPage } from './overall-page';
import { Empty, ResultsPage, coveredSections } from './results-page';
import { SuitePage } from './suite-page';
import { WinnersPage } from './winners-page';
import { Field, Pill, date, format } from './presentation';
import { SectionCoverage, refreshLabel, scaleLabel } from './section-rail';
import {
  REPOSITORY,
  observations,
  workloadLabel,
  type Observation,
  type Submission,
} from './model';
import './style.css';

const VIEWS = [
  ['results', 'Results'],
  ['winners', 'Winners'],
  ['overall', 'Overall'],
  ['hosts', 'Hosts'],
  ['suite', 'Suite'],
  ['contribute', 'Contribute'],
] as const;
type View = (typeof VIEWS)[number][0];
const FILTER_KEYS = ['section', 'host', 'frontend', 'from', 'to', 'layout', 'close', 'scale'];
const HEADINGS: Record<View, { title: string; lede: string }> = {
  results: {
    title: 'Baseline results, in context.',
    lede: 'Every published campaign is one unmodified run of the official seven-section suite. Browse by section and host; every record keeps its machine, revision and display context.',
  },
  winners: {
    title: 'Best observed records, per section.',
    lede: 'For each of the seven sections, the best record of every frontend across all hosts: update rate first, then memory and CPU when rates are close.',
  },
  overall: {
    title: 'Placements across all seven sections.',
    lede: 'Section placements added up for the frontends that hold a record in every section. No measurement is pooled.',
  },
  hosts: {
    title: 'The hosts behind the records',
    lede: 'Hardware, platforms and section coverage of every machine that contributed a baseline campaign.',
  },
  suite: {
    title: 'The official baseline suite',
    lede: 'Seven sections, one set of fixed conditions, three 30-second repetitions each. The only suite the site publishes.',
  },
  contribute: {
    title: 'Add your baseline campaign',
    lede: 'Run the official suite unmodified on a visible desktop, export it here, and open a pull request. Every submission keeps its own context.',
  },
};

const distinct = (values: string[]) => [...new Set(values)].sort();
function download(campaign: Submission) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(campaign, null, 2) + '\n'], { type: 'application/json' }),
  );
  const a = document.createElement('a');
  a.href = url;
  a.download = campaign.id + '.json';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
// Unknown keys and unknown section slugs are dropped, so old links degrade to the
// unfiltered page instead of breaking.
function readLocation(): { view: View; filters: URLSearchParams } {
  const [view, query = ''] = location.hash.slice(1).split('?');
  const raw = new URLSearchParams(query),
    filters = new URLSearchParams();
  for (const key of FILTER_KEYS) if (raw.get(key)) filters.set(key, raw.get(key)!);
  return {
    view: VIEWS.some(([v]) => v === view) ? (view as View) : 'results',
    filters,
  };
}
function App() {
  const [campaigns, setCampaigns] = useState<Submission[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState('');
  const [route, setRoute] = useState(readLocation),
    [selected, setSelected] = useState<Observation | null>(null);
  useEffect(() => {
    const update = () => setRoute(readLocation());
    addEventListener('hashchange', update);
    return () => removeEventListener('hashchange', update);
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    fetch(import.meta.env.BASE_URL + 'catalog.json', { signal: abort.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error(`Catalogue request failed (${r.status})`);
        return r.json();
      })
      .then((data) => {
        if (data.schema_version !== 1 || !Array.isArray(data.campaigns))
          throw new Error('Unsupported catalogue format');
        setCampaigns(validateCatalog(data.campaigns));
        setLoading(false);
      })
      .catch((e) => {
        if (e.name !== 'AbortError') {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => abort.abort();
  }, []);
  const all = useMemo(() => observations(campaigns), [campaigns]);
  const hosts = useMemo(() => distinct(campaigns.map((c) => c.host.id)), [campaigns]);
  // Filters stay on the page that set them; other pages send them to the results.
  function filter(key: string, value: string) {
    const params = new URLSearchParams(route.filters);
    value ? params.set(key, value) : params.delete(key);
    const view = ['results', 'winners', 'overall'].includes(route.view) ? route.view : 'results';
    location.hash = view + (params.size ? '?' + params.toString() : '');
  }
  const heading = HEADINGS[route.view];
  return (
    <>
      <a href="#main" className="skip">
        Skip to results
      </a>
      <header className="topbar">
        <a className="brand" href="#results" aria-label="Plotbench home">
          <svg viewBox="0 0 36 28" aria-hidden="true">
            <path d="M1 21h6l4-15 6 21 6-23 5 17h7" />
          </svg>
          <strong>plotbench</strong>
          <span>/ baseline</span>
        </a>
        <nav aria-label="Main navigation">
          {VIEWS.map(([v, label]) => (
            <a
              key={v}
              className={route.view === v ? 'active' : ''}
              aria-current={route.view === v ? 'page' : undefined}
              href={'#' + v}
            >
              {label}
            </a>
          ))}
        </nav>
        <a className="github" href={REPOSITORY}>
          GitHub <span aria-hidden="true">↗</span>
        </a>
      </header>
      <main id="main">
        <div className="app-header page-heading">
          <div>
            <p className="eyebrow">OPEN BASELINE COLLECTION</p>
            <h1>{heading.title}</h1>
            <p className="lede">{heading.lede}</p>
          </div>
          {route.view !== 'contribute' && (
            <a className="btn-primary" href="#contribute">
              Contribute results <span aria-hidden="true">↗</span>
            </a>
          )}
        </div>
        {route.view === 'contribute' ? (
          <Contribute />
        ) : route.view === 'suite' ? (
          <SuitePage />
        ) : loading ? (
          <section className="empty muted" role="status">
            Loading benchmark catalogue…
          </section>
        ) : error ? (
          <section className="empty" role="alert">
            <h2>Couldn’t load the results</h2>
            <p className="alert">{error}</p>
            <button className="btn-soft" onClick={() => location.reload()}>
              Try again
            </button>
          </section>
        ) : route.view === 'winners' ? (
          <WinnersPage
            key={route.filters.toString()}
            observations={all}
            filters={route.filters}
            filter={filter}
            select={setSelected}
          />
        ) : route.view === 'overall' ? (
          <OverallPage observations={all} filters={route.filters} filter={filter} />
        ) : route.view === 'hosts' ? (
          <Hosts campaigns={campaigns} hosts={hosts} />
        ) : (
          <ResultsPage
            campaigns={campaigns}
            all={all}
            filters={route.filters}
            filter={filter}
            select={setSelected}
          />
        )}
        <footer>
          <span>
            plotbench <span className="muted">/ Open measurements. Explicit context.</span>
          </span>
          <span>
            <a href="#suite">The baseline suite</a> ·{' '}
            <a href={REPOSITORY + '/blob/main/docs/methodology.md'}>Measurement methodology ↗</a>
          </span>
        </footer>
      </main>
      {selected && <RunDetails observation={selected} close={() => setSelected(null)} />}
    </>
  );
}
function Hosts({ campaigns, hosts }: { campaigns: Submission[]; hosts: string[] }) {
  return (
    <section className="host-grid" aria-label="Benchmark hosts">
      {hosts.length ? (
        hosts.map((id) => {
          const cs = campaigns.filter((c) => c.host.id === id),
            h = cs[0].host,
            covered = coveredSections(observations(cs));
          return (
            <article className="host-card" key={id}>
              <div className="card-head">
                <h2>{h.label}</h2>
                <Pill>{h.architecture}</Pill>
              </div>
              <p>{h.cpu}</p>
              <dl className="kv">
                <dt>Graphics</dt>
                <dd>{h.gpu ?? 'Not recorded'}</dd>
                <dt>Memory</dt>
                <dd>{format(h.memory_gib)} GiB</dd>
                <dt>Latest OS</dt>
                <dd>{h.os}</dd>
                <dt>History</dt>
                <dd>
                  {cs.length} campaign{cs.length === 1 ? '' : 's'} ·{' '}
                  {cs.reduce((n, c) => n + c.runs.length, 0)} runs · latest{' '}
                  {date(cs[0].recorded_at)}
                </dd>
                <dt>Frontends</dt>
                <dd>{distinct(cs.flatMap((c) => c.runs.map((r) => r.frontend))).join(' · ')}</dd>
              </dl>
              <p>
                {covered.size} of {SECTIONS.length} sections
              </p>
              <SectionCoverage
                covered={covered}
                href={(slug) => `#results?host=${encodeURIComponent(id)}&section=${slug}`}
              />
              <a className="btn-soft" href={'#results?host=' + encodeURIComponent(id)}>
                Explore results <span aria-hidden="true">→</span>
              </a>
            </article>
          );
        })
      ) : (
        <Empty />
      )}
    </section>
  );
}
function RunDetails({
  observation: { campaign: c, run: r },
  close,
}: {
  observation: Observation;
  close: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  const x = r.context,
    section = sectionOf(r.config);
  return (
    <dialog
      ref={dialog}
      onClose={close}
      onClick={(e) => {
        if (e.target === dialog.current) close();
      }}
      aria-labelledby="detail-title"
    >
      <div className="dialog-content">
        <div className="panel-head">
          <p className="eyebrow">RUN DETAILS · {r.id}</p>
          <button className="btn-soft btn-icon" onClick={close} aria-label="Close run details">
            ×
          </button>
        </div>
        <h2 id="detail-title">
          {r.frontend} on {c.host.label}
        </h2>
        <div className="pills">
          {section && (
            <Pill>
              Section {section.index} · {section.title}
            </Pill>
          )}
          <Pill>
            {r.backend} · {r.mode}
          </Pill>
          <Pill tone={r.status === 'ok' ? 'success' : 'danger'}>{r.status}</Pill>
        </div>
        <p>{workloadLabel(r.config)}</p>
        <dl className="kv detail-grid">
          <dt>Submitted</dt>
          <dd>
            {format(r.metrics.submitted_hz)} updates/s / {r.config.hz} target
          </dd>
          <dt>Update p50 / p95</dt>
          <dd>
            {format(r.metrics.update_p50_ms, 3)} / {format(r.metrics.update_p95_ms, 3)} ms
          </dd>
          <dt>CPU / peak RSS</dt>
          <dd>
            {format(r.metrics.cpu_mean_percent)}% / {format(r.metrics.rss_peak_mib)} MiB
          </dd>
          <dt>Sequence gaps</dt>
          <dd>{format(r.metrics.gap_percent)}%</dd>
          <dt>Source rate</dt>
          <dd>{format(r.metrics.source_hz)} Hz</dd>
          <dt>Source misses / mailbox drops</dt>
          <dd>
            {format(r.metrics.source_deadline_misses, 0)} /{' '}
            {format(r.metrics.source_mailbox_drops, 0)}
          </dd>
          <dt>Window</dt>
          <dd>
            {r.warmup_seconds}s warmup + {r.measurement_seconds}s measurement · repetition{' '}
            {r.repetition} · {r.samples} samples
          </dd>
          <dt>Display</dt>
          <dd>
            {x.display_protocol ?? 'Unknown protocol'} · {scaleLabel(x.pixel_ratio)} ·{' '}
            {refreshLabel(x.refresh_hz)}
          </dd>
          <dt>Physical plot regions</dt>
          <dd>
            {Object.entries(x.plot_viewports)
              .filter(([, v]) => v)
              .map(([name, v]) => `${name}: ${v!.map((n) => format(n, 0)).join(' × ')} px`)
              .join('; ') || 'Not recorded'}
          </dd>
          <dt>Acquired</dt>
          <dd>{new Date(c.recorded_at).toLocaleString()}</dd>
          <dt>Acquisition host</dt>
          <dd>
            {c.host.cpu} · {c.host.gpu ?? 'GPU not recorded'} · {format(c.host.memory_gib)} GiB
          </dd>
          <dt>Platform</dt>
          <dd>
            {c.host.os} · {c.host.architecture}
          </dd>
          <dt>Renderer</dt>
          <dd>{x.renderer ?? 'Not recorded'}</dd>
        </dl>
        <div className="notice">
          <p>
            {x.measurement_stage ?? 'Timing boundary was not recorded.'}
            <br />
            CPU/API duration does not establish GPU completion or presentation.
          </p>
        </div>
        <h3>Recorded software</h3>
        <p>
          {Object.entries(x.versions)
            .map(([k, v]) => `${k} ${v}`)
            .join(' · ') || 'Versions not recorded'}
        </p>
        <dl className="kv detail-grid">
          <dt>Source commit</dt>
          <dd>
            <code>{x.commit ?? 'Not recorded'}</code>{' '}
            {x.dirty && <Pill tone="amber">Modified checkout</Pill>}
          </dd>
          <dt>Source fingerprint</dt>
          <dd>
            <code>{x.source_hash ?? 'Not recorded'}</code>
          </dd>
          <dt>Execution context</dt>
          <dd>
            <code>{x.fingerprint}</code>
          </dd>
        </dl>
        <h3>Campaign</h3>
        <p>
          {c.title} · {c.runs.length} of {c.planned_runs} planned runs recorded ·{' '}
          {c.completion_status}
        </p>
        {c.notes && <p>{c.notes}</p>}
        <div className="actions">
          <button className="btn-soft" onClick={() => download(c)}>
            Download submission
          </button>
          {Object.entries(c.links)
            .filter(([, url]) => url)
            .map(([label, url]) => (
              <a
                className="btn-soft"
                key={label}
                href={url!}
                target="_blank"
                rel="noopener noreferrer"
              >
                {label.replaceAll('_', ' ')} ↗
              </a>
            ))}
        </div>
        {!Object.values(c.links).some(Boolean) && (
          <p className="muted small">Full report and raw-data links have not been submitted.</p>
        )}
      </div>
    </dialog>
  );
}
function Contribute() {
  const [raw, setRaw] = useState<unknown>(null),
    [filename, setFilename] = useState(''),
    [id, setId] = useState(''),
    [hostId, setHostId] = useState(''),
    [hostLabel, setHostLabel] = useState(''),
    [notes, setNotes] = useState(''),
    [error, setError] = useState(''),
    [result, setResult] = useState<Submission | null>(null),
    [busy, setBusy] = useState(false),
    [reviewed, setReviewed] = useState(false),
    [proposed, setProposed] = useState<SubmissionDefaults | null>(null);
  const invalidate = () => {
    setResult(null);
    setReviewed(false);
  };
  // The summary's public fields fill the form; the contributor reviews and adjusts.
  const apply = (defaults: SubmissionDefaults) => {
    setId(defaults.id);
    setHostId(defaults.hostId);
    setHostLabel(defaults.hostLabel);
    setNotes(defaults.notes);
  };
  const edited =
    proposed !== null &&
    (id !== proposed.id ||
      hostId !== proposed.hostId ||
      hostLabel !== proposed.hostLabel ||
      notes !== proposed.notes);
  async function fileChanged(file?: File) {
    invalidate();
    setError('');
    setRaw(null);
    setFilename('');
    if (!file) return;
    try {
      if (file.size > 25 * 1024 * 1024)
        throw new Error('Summary exceeds 25 MiB; split a large campaign first.');
      const data = JSON.parse(await file.text());
      const defaults = suggestSubmission(data);
      setRaw(data);
      setFilename(file.name);
      setProposed(defaults);
      apply(defaults);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function prepare(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setResult(null);
    setReviewed(false);
    setBusy(true);
    try {
      const c = await exportSummary(raw, { id, hostId, hostLabel, notes });
      if (new TextEncoder().encode(JSON.stringify(c, null, 2) + '\n').length > MAX_SUBMISSION_BYTES)
        throw new Error('Public submission exceeds 5 MiB; split the campaign.');
      setResult(c);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const preview = result && {
    sections: coveredSections(observations([result])).size,
    frontends: distinct(result.runs.map((r) => r.frontend)).length,
  };
  return (
    <div className="contribute-layout">
      <section className="panel submission-form" aria-label="Prepare a submission">
        <h2>Prepare a submission</h2>
        <p className="muted small">
          Choose the <code>summary.json</code> of a completed baseline campaign (
          <code>./scripts/plotbench run --baseline</code>, unmodified). The form proposes the public
          fields from it; processing happens in your browser, and choosing a file does not upload
          it. Campaigns of any other suite are refused here.
        </p>
        <form onSubmit={prepare}>
          <label className="file-picker">
            Campaign summary{filename ? ` · ${filename}` : ''}
            <input
              aria-label="Campaign summary"
              type="file"
              accept=".json,application/json"
              onChange={(e) => void fileChanged(e.target.files?.[0])}
            />
          </label>
          {proposed && (
            <p className="muted small" role="status">
              Campaign ID, host alias, label and notes were proposed from the summary’s CPU model,
              OS, acquisition date, timings and display context. Review and adjust them before
              previewing; a second campaign on the same day needs a suffix on its ID.
            </p>
          )}
          <Field label="Campaign ID">
            <input
              aria-label="Campaign ID"
              required
              pattern="[a-z0-9][a-z0-9-]{0,79}"
              value={id}
              placeholder="workstation-a-20260915-plotbench-baseline"
              onChange={(e) => {
                setId(e.target.value);
                invalidate();
              }}
            />
          </Field>
          <div className="field-grid">
            <Field label="Public host ID">
              <input
                aria-label="Public host ID"
                required
                pattern="[a-z0-9][a-z0-9-]{0,79}"
                value={hostId}
                placeholder="workstation-a"
                onChange={(e) => {
                  setHostId(e.target.value);
                  invalidate();
                }}
              />
            </Field>
            <Field label="Host label">
              <input
                aria-label="Host label"
                required
                maxLength={200}
                value={hostLabel}
                placeholder="Linux workstation · RTX 4090"
                onChange={(e) => {
                  setHostLabel(e.target.value);
                  invalidate();
                }}
              />
            </Field>
          </div>
          <Field label="Operating conditions" hint="optional">
            <textarea
              aria-label="Operating conditions"
              value={notes}
              maxLength={2000}
              placeholder="For example: connected to power, native desktop at a fixed 120 Hz and 2x scaling, no other benchmark windows."
              onChange={(e) => {
                setNotes(e.target.value);
                invalidate();
              }}
            />
          </Field>
          <div className="actions">
            <button className="btn-primary" type="submit" disabled={!raw || busy}>
              {busy ? 'Preparing…' : 'Preview public submission'}
            </button>
            {edited && (
              <button
                className="btn-soft"
                type="button"
                onClick={() => {
                  apply(proposed);
                  invalidate();
                }}
              >
                Restore proposed values
              </button>
            )}
          </div>
        </form>
        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}
        {result && preview && (
          <section className="submission-preview" aria-label="Submission preview">
            <div className="panel-head">
              <h3>Ready to review</h3>
              <span className="muted small">
                {preview.sections} of {SECTIONS.length} sections · {preview.frontends} frontend
                {preview.frontends === 1 ? '' : 's'} · {BASELINE.repetitions} repetitions each
              </span>
            </div>
            <p className="muted small">
              {result.host.cpu} · {result.host.os} · {result.runs.length} runs
            </p>
            <details className="disclosure">
              <summary>Inspect the exact JSON to publish</summary>
              <pre>{JSON.stringify(result, null, 2)}</pre>
            </details>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={reviewed}
                onChange={(e) => setReviewed(e.target.checked)}
              />
              I reviewed this JSON and want to share these details publicly.
            </label>
            <button className="btn-soft" disabled={!reviewed} onClick={() => download(result)}>
              Download {result.id}.json
            </button>
            <p className="muted small">
              Add it to <code>website/results/</code> under exactly that name. If your browser
              appends a number because the file already exists, rename it before opening the pull
              request.
            </p>
          </section>
        )}
      </section>
      <aside className="panel guide" aria-label="How contributions work">
        <p className="eyebrow">HOW CONTRIBUTIONS WORK</p>
        <ol>
          <li>
            <span className="step-no">1</span>
            <div>
              <strong>Run the official baseline, unmodified</strong>
              <p>
                <code>./scripts/plotbench run --baseline</code> on a visible desktop with a fixed
                refresh rate and display scale, on an otherwise idle machine. Only{' '}
                <code>--frontends</code> may narrow the suite; every frontend you run covers all{' '}
                {SECTIONS.length} sections with {BASELINE.repetitions} repetitions. Keep failed
                attempts; if a frontend crashes the campaign, re-run that frontend alone as its own
                campaign.
              </p>
              <a className="btn-soft" href="#suite">
                Read the suite
              </a>
            </div>
          </li>
          <li>
            <span className="step-no">2</span>
            <div>
              <strong>Review the export</strong>
              <p>
                Raw logs, local paths, command lines and environment values are omitted. Check the
                proposed host alias, labels, notes, and all public fields before sharing. The export
                refuses campaigns that deviate from the suite, headless or X11 runs, and modified
                checkouts.
              </p>
            </div>
          </li>
          <li>
            <span className="step-no">3</span>
            <div>
              <strong>Open a pull request</strong>
              <p>
                Add the downloaded JSON to <code>website/results/</code>. Validation runs in CI;
                maintainers review the evidence before merging.
              </p>
              <a
                className="btn-soft"
                href={REPOSITORY + '/upload/main/website/results'}
                target="_blank"
                rel="noopener noreferrer"
              >
                Add file on GitHub ↗
              </a>
            </div>
          </li>
        </ol>
        <div className="filter-note">
          <strong>A growing record, not a global score.</strong>
          <p>
            Failed attempts and source-limited runs stay visible. Results remain associated with
            their acquisition host, source revision and display context; nothing is pooled across
            hosts or sections.
          </p>
        </div>
        <a href={REPOSITORY + '/blob/main/website/results/README.md'}>
          Read submission requirements ↗
        </a>
      </aside>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
