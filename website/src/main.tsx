import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { exportSummary } from './export';
import { MAX_SUBMISSION_BYTES, validateCatalog } from './validation';
import { groupObservations, inDateRange } from './aggregation';
import { GroupedResults } from './grouped-results';
import { WinnersPage } from './winners-page';
import { Badge, date, format } from './presentation';
import {
  REPOSITORY,
  observations,
  sourceLimited,
  workloadKey,
  workloadLabel,
  type Observation,
  type Submission,
} from './model';
import './style.css';

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
function readLocation() {
  const [view, query = ''] = location.hash.slice(1).split('?');
  return {
    view: ['hosts', 'contribute', 'winners'].includes(view) ? view : 'results',
    filters: new URLSearchParams(query),
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
  function filter(key: string, value: string) {
    const params = new URLSearchParams(route.filters);
    value ? params.set(key, value) : params.delete(key);
    location.hash =
      (route.view === 'winners' ? 'winners' : 'results') +
      (params.size ? '?' + params.toString() : '');
  }
  const visible = useMemo(
    () =>
      all.filter(
        ({ campaign: c, run: r }) =>
          (!route.filters.get('host') || c.host.id === route.filters.get('host')) &&
          (!route.filters.get('frontend') || r.frontend === route.filters.get('frontend')) &&
          (!route.filters.get('backend') || r.backend === route.filters.get('backend')) &&
          (!route.filters.get('mode') || r.mode === route.filters.get('mode')) &&
          (!route.filters.get('workload') ||
            workloadKey(r.config) === route.filters.get('workload')) &&
          (!route.filters.get('platform') || c.host.os === route.filters.get('platform')) &&
          (!route.filters.get('kind') || c.classification === route.filters.get('kind')) &&
          inDateRange(
            c.recorded_at,
            route.filters.get('from') ?? '',
            route.filters.get('to') ?? '',
          ),
      ),
    [all, route.filters],
  );
  const grouped = route.filters.get('layout') !== 'runs';
  const groups = useMemo(() => groupObservations(visible), [visible]);
  const itemCount = grouped ? groups.length : visible.length;
  const [page, setPage] = useState(0);
  useEffect(() => setPage(0), [route]);
  const pageSize = 25;
  const workloads = [
    ...new Map(all.map(({ run: r }) => [workloadKey(r.config), workloadLabel(r.config)])).entries(),
  ];
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
          <span>/ results</span>
        </a>
        <nav aria-label="Main navigation">
          {[
            ['results', 'Results'],
            ['winners', 'Winners'],
            ['hosts', 'Hosts'],
            ['contribute', 'Contribute'],
          ].map(([v, label]) => (
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
        <div className="page-heading">
          <div>
            <p className="eyebrow">OPEN BENCHMARK COLLECTION</p>
            <h1>
              {route.view === 'hosts'
                ? 'Explore the hosts'
                : route.view === 'winners'
                  ? 'The best results, across hosts.'
                  : route.view === 'contribute'
                    ? 'Add your measurements'
                    : 'Plotting performance, in context.'}
            </h1>
            <p className="lede">
              {route.view === 'hosts'
                ? 'Hardware and platforms behind the submitted campaigns.'
                : route.view === 'winners'
                  ? 'Find the best balance of update rate, memory and CPU for each workload, wherever it was measured.'
                  : route.view === 'contribute'
                    ? 'Contribute a campaign from your machine. Every submission keeps its own context.'
                    : 'Explore community measurements across plotting libraries, machines, and platforms.'}
            </p>
          </div>
          {route.view !== 'contribute' && (
            <a className="button primary" href="#contribute">
              Contribute results <span aria-hidden="true">↗</span>
            </a>
          )}
        </div>
        {route.view === 'contribute' ? (
          <Contribute />
        ) : loading ? (
          <section className="empty" role="status">
            Loading benchmark catalogue…
          </section>
        ) : error ? (
          <section className="empty error" role="alert">
            <h2>Couldn’t load the results</h2>
            <p>{error}</p>
            <button onClick={() => location.reload()}>Try again</button>
          </section>
        ) : (
          <>
            <div className="stats">
              <div>
                <span>Hosts</span>
                <strong>{hosts.length.toLocaleString()}</strong>
                <small>
                  {distinct(campaigns.map((c) => c.host.architecture)).join(' · ') ||
                    'Awaiting contributions'}
                </small>
              </div>
              <div>
                <span>Campaigns</span>
                <strong>{campaigns.length.toLocaleString()}</strong>
                <small>
                  {campaigns.length
                    ? 'Latest ' + date(campaigns[0].recorded_at)
                    : 'No campaigns yet'}
                </small>
              </div>
              <div>
                <span>Recorded runs</span>
                <strong>{all.length.toLocaleString()}</strong>
                <small>
                  {all.filter((o) => o.run.status === 'ok').length} valid ·{' '}
                  {all.filter((o) => o.run.status !== 'ok').length} flagged
                </small>
              </div>
              <div>
                <span>Frontends</span>
                <strong>{distinct(all.map((o) => o.run.frontend)).length}</strong>
                <small>Each rendering path measured separately</small>
              </div>
            </div>
            {route.view === 'winners' ? (
              <WinnersPage
                key={route.filters.toString()}
                observations={all}
                filters={route.filters}
                filter={filter}
                select={setSelected}
              />
            ) : route.view === 'hosts' ? (
              <section className="host-grid" aria-label="Benchmark hosts">
                {hosts.length ? (
                  hosts.map((id) => {
                    const cs = campaigns.filter((c) => c.host.id === id),
                      h = cs[0].host;
                    return (
                      <article className="host-card" key={id}>
                        <div className="host-icon" aria-hidden="true">
                          ▤
                        </div>
                        <Badge>{h.architecture}</Badge>
                        <h2>{h.label}</h2>
                        <p>{h.cpu}</p>
                        <dl>
                          <dt>Graphics</dt>
                          <dd>{h.gpu ?? 'Not recorded'}</dd>
                          <dt>Memory</dt>
                          <dd>{format(h.memory_gib)} GiB</dd>
                          <dt>Latest OS</dt>
                          <dd>{h.os}</dd>
                          <dt>History</dt>
                          <dd>
                            {cs.length} campaign{cs.length === 1 ? '' : 's'} ·{' '}
                            {cs.reduce((n, c) => n + c.runs.length, 0)} runs
                          </dd>
                        </dl>
                        <p className="muted">
                          {distinct(cs.flatMap((c) => c.runs.map((r) => r.frontend))).join(' · ')}
                        </p>
                        <a className="button" href={'#results?host=' + encodeURIComponent(id)}>
                          Explore results <span aria-hidden="true">→</span>
                        </a>
                      </article>
                    );
                  })
                ) : (
                  <Empty />
                )}
              </section>
            ) : (
              <div className="workspace">
                <aside className="filters">
                  <div className="section-line">
                    <h2>Explore</h2>
                    {route.filters.size > 0 && <a href="#results">Reset</a>}
                  </div>
                  <Select
                    label="Host"
                    value={route.filters.get('host') ?? ''}
                    onChange={(v) => filter('host', v)}
                    options={hosts.map((id) => [
                      id,
                      campaigns.find((c) => c.host.id === id)!.host.label,
                    ])}
                  />
                  <Select
                    label="Platform"
                    value={route.filters.get('platform') ?? ''}
                    onChange={(v) => filter('platform', v)}
                    options={distinct(campaigns.map((c) => c.host.os)).map((x) => [x, x])}
                  />
                  <Select
                    label="Frontend"
                    value={route.filters.get('frontend') ?? ''}
                    onChange={(v) => filter('frontend', v)}
                    options={distinct(all.map((o) => o.run.frontend)).map((x) => [x, x])}
                  />
                  <Select
                    label="Source backend"
                    value={route.filters.get('backend') ?? ''}
                    onChange={(v) => filter('backend', v)}
                    options={distinct(all.map((o) => o.run.backend)).map((x) => [x, x])}
                  />
                  <Select
                    label="Delivery"
                    value={route.filters.get('mode') ?? ''}
                    onChange={(v) => filter('mode', v)}
                    options={distinct(all.map((o) => o.run.mode)).map((x) => [x, x])}
                  />
                  <Select
                    label="Campaign type"
                    value={route.filters.get('kind') ?? ''}
                    onChange={(v) => filter('kind', v)}
                    options={distinct(campaigns.map((c) => c.classification)).map((x) => [x, x])}
                  />
                  <label className="select-label">
                    Acquired from (UTC)
                    <input
                      aria-label="Acquired from (UTC)"
                      type="date"
                      value={route.filters.get('from') ?? ''}
                      onChange={(e) => filter('from', e.target.value)}
                    />
                  </label>
                  <label className="select-label">
                    Acquired through (UTC)
                    <input
                      aria-label="Acquired through (UTC)"
                      type="date"
                      value={route.filters.get('to') ?? ''}
                      onChange={(e) => filter('to', e.target.value)}
                    />
                  </label>
                  <div className="filter-note">
                    <strong>Keep the context.</strong>
                    <p>
                      Match workloads, source versions, and delivery modes before comparing hosts.
                      No cross-host averages are calculated.
                    </p>
                  </div>
                </aside>
                <section className="results-panel">
                  <div className="section-line">
                    <div>
                      <h2>Measurements</h2>
                      <p className="muted">
                        {grouped ? `${groups.length} groups · ` : ''}
                        {visible.length} individual run{visible.length === 1 ? '' : 's'} · submitted
                        updates, not displayed FPS
                      </p>
                    </div>
                  </div>
                  <div className="view-toggle" role="group" aria-label="Results view">
                    <button aria-pressed={grouped} onClick={() => filter('layout', '')}>
                      Grouped
                    </button>
                    <button aria-pressed={!grouped} onClick={() => filter('layout', 'runs')}>
                      Individual runs
                    </button>
                  </div>
                  {grouped && (
                    <p className="aggregation-note">
                      Median of campaign medians, with each campaign weighted equally. Middle 50%
                      shows the spread of campaign medians. Expand a group to inspect campaigns and
                      repetitions.
                    </p>
                  )}
                  <Select
                    label="Workload"
                    value={route.filters.get('workload') ?? ''}
                    onChange={(v) => filter('workload', v)}
                    options={workloads}
                  />
                  {campaigns.some((c) => c.classification === 'smoke') && (
                    <div className="notice">
                      <span className="notice-dot" />
                      <p>
                        <strong>Smoke runs are functional checks.</strong> Short campaigns establish
                        that an adapter works; they do not establish a sustained performance
                        ranking.
                      </p>
                    </div>
                  )}
                  {visible.length ? (
                    <>
                      {grouped ? (
                        <GroupedResults
                          key={route.filters.toString()}
                          groups={groups.slice(page * pageSize, (page + 1) * pageSize)}
                          select={setSelected}
                        />
                      ) : (
                        <div className="table-scroll">
                          <table>
                            <thead>
                              <tr>
                                <th>Frontend / host</th>
                                <th>Workload</th>
                                <th>Submitted / target</th>
                                <th>Context</th>
                                <th>
                                  <span className="sr-only">Details</span>
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {visible.slice(page * pageSize, (page + 1) * pageSize).map((o) => {
                                const { campaign: c, run: r } = o;
                                const valid = r.status === 'ok',
                                  ratio =
                                    valid && r.metrics.submitted_hz !== null
                                      ? r.metrics.submitted_hz / r.config.hz
                                      : null;
                                return (
                                  <tr key={c.id + '/' + r.id}>
                                    <td>
                                      <strong className="frontend">
                                        <i
                                          className={
                                            'dot ' + (r.frontend === 'matplotlib' ? 'violet' : '')
                                          }
                                        />
                                        {r.frontend}
                                      </strong>
                                      <span className="cell-sub">{c.host.label}</span>
                                    </td>
                                    <td>
                                      <span>
                                        {r.config.view === 'image'
                                          ? 'Image'
                                          : r.config.view === 'waveform'
                                            ? 'Waveform'
                                            : 'Waveform + image'}
                                      </span>
                                      <span className="cell-sub">
                                        {r.config.view !== 'image'
                                          ? `${format(r.config.points, 0)} pts · ${r.config.waveform_mode}`
                                          : ''}
                                        {r.config.view === 'both' ? ' / ' : ''}
                                        {r.config.view !== 'waveform'
                                          ? `${r.config.width}×${r.config.height} ${r.config.image_mode}`
                                          : ''}
                                      </span>
                                    </td>
                                    <td>
                                      <span className="rate">
                                        {valid ? format(r.metrics.submitted_hz) : '—'}{' '}
                                        <small>/ {r.config.hz} Hz</small>
                                      </span>
                                      <div
                                        className="bar"
                                        aria-label={
                                          ratio === null
                                            ? 'No valid rate'
                                            : `${format(ratio * 100)} percent of target`
                                        }
                                      >
                                        <span
                                          style={{
                                            width: `${Math.min(100, Math.max(0, (ratio ?? 0) * 100))}%`,
                                          }}
                                        />
                                      </div>
                                    </td>
                                    <td>
                                      <div className="badges">
                                        <Badge>
                                          {r.backend} · {r.mode}
                                        </Badge>
                                        <Badge tone={valid ? 'muted' : 'danger'}>
                                          {valid ? c.classification : r.status}
                                        </Badge>
                                        {sourceLimited(r) && (
                                          <Badge tone="amber">Source limits</Badge>
                                        )}
                                      </div>
                                      <span className="cell-sub">
                                        {r.measurement_seconds}s · repetition {r.repetition} ·{' '}
                                        {date(c.recorded_at)}
                                      </span>
                                    </td>
                                    <td>
                                      <button
                                        className="icon-button"
                                        aria-label={`Details for ${r.frontend} ${r.id} in ${c.id}`}
                                        onClick={() => setSelected(o)}
                                      >
                                        ↗
                                      </button>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                      <div className="pagination">
                        <span>
                          {page * pageSize + 1}–{Math.min((page + 1) * pageSize, itemCount)} of{' '}
                          {itemCount} {grouped ? 'groups' : 'runs'}
                        </span>
                        <div>
                          <button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                            Previous
                          </button>
                          <button
                            disabled={(page + 1) * pageSize >= itemCount}
                            onClick={() => setPage((p) => p + 1)}
                          >
                            Next
                          </button>
                        </div>
                      </div>
                    </>
                  ) : (
                    <Empty filtered={route.filters.size > 0} />
                  )}
                </section>
              </div>
            )}
          </>
        )}
        <footer>
          <span>
            plotbench <span className="muted">/ Open measurements. Explicit context.</span>
          </span>
          <a href={REPOSITORY + '/blob/main/docs/methodology.md'}>Measurement methodology ↗</a>
        </footer>
      </main>
      {selected && <RunDetails observation={selected} close={() => setSelected(null)} />}
    </>
  );
}
function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[][];
  onChange: (v: string) => void;
}) {
  return (
    <label className="select-label">
      {label}
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">
          All {label.toLowerCase() === 'delivery' ? 'modes' : label.toLowerCase() + 's'}
        </option>
        {options.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
    </label>
  );
}
function Empty({ filtered = false }: { filtered?: boolean }) {
  return (
    <div className="empty">
      <h2>{filtered ? 'No matching runs' : 'The collection starts here'}</h2>
      <p>
        {filtered
          ? 'Try a different workload or clear the filters.'
          : 'Add a campaign from your machine to start building a cross-platform picture.'}
      </p>
      <a className="button" href={filtered ? '#results' : '#contribute'}>
        {filtered ? 'Clear filters' : 'Contribute results'}
      </a>
    </div>
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
  const x = r.context;
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
        <div className="section-line">
          <p className="eyebrow">RUN DETAILS · {r.id}</p>
          <button className="icon-button" onClick={close} aria-label="Close run details">
            ×
          </button>
        </div>
        <h2 id="detail-title">
          {r.frontend} on {c.host.label}
        </h2>
        <div className="badges">
          <Badge>
            {r.backend} · {r.mode}
          </Badge>
          <Badge>{c.classification}</Badge>
          <Badge tone={r.status === 'ok' ? 'success' : 'danger'}>{r.status}</Badge>
        </div>
        <p>{workloadLabel(r.config)}</p>
        <dl className="detail-grid">
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
            {r.warmup_seconds}s warmup + {r.measurement_seconds}s measurement · {r.samples} samples
          </dd>
          <dt>Display</dt>
          <dd>
            {x.display_protocol ?? 'Unknown protocol'} · {format(x.pixel_ratio)}× scale ·{' '}
            {format(x.refresh_hz)} Hz refresh
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
        <dl className="detail-grid">
          <dt>Source commit</dt>
          <dd>
            <code>{x.commit ?? 'Not recorded'}</code>
            {x.dirty && <Badge tone="amber">Modified checkout</Badge>}
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
          <button onClick={() => download(c)}>Download submission</button>
          {Object.entries(c.links)
            .filter(([, url]) => url)
            .map(([label, url]) => (
              <a
                className="button"
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
          <p className="muted">Full report and raw-data links have not been submitted.</p>
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
    [reviewed, setReviewed] = useState(false);
  const invalidate = () => {
    setResult(null);
    setReviewed(false);
  };
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
      setRaw(data);
      setFilename(file.name);
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
  return (
    <div className="contribute-layout">
      <section className="submission-form">
        <h2>Prepare a submission</h2>
        <p>
          Choose the <code>summary.json</code> from a completed Plotbench campaign. Processing
          happens in your browser; choosing a file does not upload it.
        </p>
        <form onSubmit={prepare}>
          <label className="file-picker">
            Campaign summary
            <input
              aria-label="Campaign summary"
              type="file"
              accept=".json,application/json"
              onChange={(e) => void fileChanged(e.target.files?.[0])}
            />
            <span>{filename || 'Choose summary.json'}</span>
          </label>
          <label>
            Campaign ID
            <input
              required
              pattern="[a-z0-9][a-z0-9-]{0,79}"
              value={id}
              placeholder="workstation-a-2026-09-14"
              onChange={(e) => {
                setId(e.target.value);
                invalidate();
              }}
            />
          </label>
          <div className="form-pair">
            <label>
              Public host ID
              <input
                required
                pattern="[a-z0-9][a-z0-9-]{0,79}"
                value={hostId}
                placeholder="workstation-a"
                onChange={(e) => {
                  setHostId(e.target.value);
                  invalidate();
                }}
              />
            </label>
            <label>
              Host label
              <input
                required
                maxLength={200}
                value={hostLabel}
                placeholder="Linux workstation · RTX 4090"
                onChange={(e) => {
                  setHostLabel(e.target.value);
                  invalidate();
                }}
              />
            </label>
          </div>
          <label>
            Operating conditions <span className="muted">optional</span>
            <textarea
              value={notes}
              maxLength={2000}
              placeholder="For example: connected to power, native desktop, no other benchmark windows."
              onChange={(e) => {
                setNotes(e.target.value);
                invalidate();
              }}
            />
          </label>
          <button className="primary" type="submit" disabled={!raw || busy}>
            {busy ? 'Preparing…' : 'Preview public submission'}
          </button>
        </form>
        {error && (
          <div className="notice error" role="alert">
            <p>{error}</p>
          </div>
        )}
        {result && (
          <section className="submission-preview" aria-label="Submission preview">
            <div className="section-line">
              <h3>Ready to review</h3>
              <Badge>{result.classification}</Badge>
            </div>
            <p>
              {result.host.cpu} · {result.host.os} · {result.runs.length} runs
            </p>
            <details>
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
            <button disabled={!reviewed} onClick={() => download(result)}>
              Download {result.id}.json
            </button>
          </section>
        )}
      </section>
      <aside className="contribution-guide">
        <p className="eyebrow">HOW CONTRIBUTIONS WORK</p>
        <ol>
          <li>
            <strong>Run a campaign</strong>
            <p>
              Use a visible desktop, keep the workload fixed, and retain every attempt. For longer
              measurements, repeat the same cases.
            </p>
          </li>
          <li>
            <strong>Review the export</strong>
            <p>
              Raw logs, local paths, command lines and environment values are omitted. Check
              hardware labels, notes, and all public fields before sharing.
            </p>
          </li>
          <li>
            <strong>Open a pull request</strong>
            <p>
              Add the downloaded JSON to <code>website/results/</code>. Validation runs in CI;
              maintainers review the evidence before merging.
            </p>
            <a
              className="button"
              href={REPOSITORY + '/upload/main/website/results'}
              target="_blank"
              rel="noopener noreferrer"
            >
              Add file on GitHub ↗
            </a>
          </li>
        </ol>
        <div className="filter-note">
          <strong>A growing record, not a global score.</strong>
          <p>
            Smoke runs, diagnostics, failed attempts and missing observations stay visible. Results
            remain associated with their acquisition host and software context.
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
