import { useMemo, useState } from 'react';
import { collectWinners, type WinnerBoard, type FrontendRecord } from './winners';
import { inDateRange } from './aggregation';
import { GroupedResults } from './grouped-results';
import { Badge, format } from './presentation';
import { workloadKey, workloadLabel, type Observation } from './model';

export function WinnersPage({
  observations,
  filters,
  filter,
  select,
}: {
  observations: Observation[];
  filters: URLSearchParams;
  filter: (key: string, value: string) => void;
  select: (o: Observation) => void;
}) {
  const kind = ['benchmark', 'smoke', 'diagnostic'].includes(filters.get('kind') ?? '')
    ? filters.get('kind')!
    : 'benchmark';
  const visible = useMemo(
    () =>
      observations.filter(
        ({ campaign: c, run: r }) =>
          c.classification === kind &&
          (!filters.get('backend') || r.backend === filters.get('backend')) &&
          (!filters.get('mode') || r.mode === filters.get('mode')) &&
          (!filters.get('workload') || workloadKey(r.config) === filters.get('workload')) &&
          inDateRange(c.recorded_at, filters.get('from') ?? '', filters.get('to') ?? ''),
      ),
    [observations, filters, kind],
  );
  const collection = useMemo(() => collectWinners(visible), [visible]);
  const [page, setPage] = useState(0),
    pageSize = 12;
  const allKinds = [...new Set(observations.map((o) => o.campaign.classification))];
  return (
    <section className="winners-page" aria-label="Winners across hosts">
      <div className="notice">
        <p>
          <strong>Best observed configurations across all hosts.</strong> Scores are
          campaign-weighted median submitted updates/s. Hardware, frontend versions and display
          settings may differ; this is not a hardware-independent library ranking or displayed FPS.
          Rates are paced by the target; reaching it does not establish maximum rendering capacity.
        </p>
      </div>
      <div className="winner-filters">
        <label>
          Collection
          <select
            aria-label="Winner collection"
            value={kind}
            onChange={(e) => filter('kind', e.target.value)}
          >
            <option value="benchmark">Benchmarks</option>
            <option value="smoke">Smoke checks</option>
            <option value="diagnostic">Diagnostics</option>
          </select>
        </label>
        <label>
          Source backend
          <select
            aria-label="Winner source backend"
            value={filters.get('backend') ?? ''}
            onChange={(e) => filter('backend', e.target.value)}
          >
            <option value="">All backends</option>
            {[...new Set(observations.map((o) => o.run.backend))].sort().map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </label>
        <label>
          Delivery
          <select
            aria-label="Winner delivery"
            value={filters.get('mode') ?? ''}
            onChange={(e) => filter('mode', e.target.value)}
          >
            <option value="">All modes</option>
            <option value="stream">stream</option>
            <option value="replay">replay</option>
          </select>
        </label>
        <label>
          Workload
          <select
            aria-label="Winner workload"
            value={filters.get('workload') ?? ''}
            onChange={(e) => filter('workload', e.target.value)}
          >
            <option value="">All workloads</option>
            {[
              ...new Map(
                observations.map((o) => [workloadKey(o.run.config), workloadLabel(o.run.config)]),
              ).entries(),
            ].map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Acquired from (UTC)
          <input
            aria-label="Winner acquired from (UTC)"
            type="date"
            value={filters.get('from') ?? ''}
            onChange={(e) => filter('from', e.target.value)}
          />
        </label>
        <label>
          Acquired through (UTC)
          <input
            aria-label="Winner acquired through (UTC)"
            type="date"
            value={filters.get('to') ?? ''}
            onChange={(e) => filter('to', e.target.value)}
          />
        </label>
      </div>
      {kind !== 'benchmark' && (
        <div className="notice">
          <p>
            <strong>{kind === 'smoke' ? 'Smoke records only.' : 'Diagnostic records only.'}</strong>{' '}
            These observations do not establish sustained performance or supported-platform
            rankings.
          </p>
        </div>
      )}
      <div className="section-line">
        <div>
          <h2>
            {kind === 'benchmark'
              ? 'Overall winners'
              : kind === 'smoke'
                ? 'Best observed smoke results'
                : 'Best observed diagnostic results'}
          </h2>
          <p className="muted">
            {collection.boards.length} comparison cases · {collection.excludedGroups} groups
            excluded for missing rates or incomplete context
          </p>
        </div>
        <a href="#winners">Reset</a>
      </div>
      <p className="aggregation-note">
        One best record per frontend and case, drawn from any host. Source revision, workload,
        backend, delivery mode and durations stay separate. Scores tie at 0.1 updates/s precision;
        ties do not establish statistical equivalence.
      </p>
      {collection.boards.length ? (
        <>
          <div className="winner-boards">
            {collection.boards.slice(page * pageSize, (page + 1) * pageSize).map((board) => (
              <Board key={board.key} board={board} select={select} />
            ))}
          </div>
          <div className="pagination">
            <span>
              {page * pageSize + 1}–{Math.min((page + 1) * pageSize, collection.boards.length)} of{' '}
              {collection.boards.length} cases
            </span>
            <div>
              <button disabled={page === 0} onClick={() => setPage((n) => n - 1)}>
                Previous cases
              </button>
              <button
                disabled={(page + 1) * pageSize >= collection.boards.length}
                onClick={() => setPage((n) => n + 1)}
              >
                Next cases
              </button>
            </div>
          </div>
        </>
      ) : (
        <div className="empty">
          <h2>No eligible {kind === 'benchmark' ? 'benchmark' : kind} results</h2>
          <p>
            {kind === 'benchmark'
              ? 'Add repeated benchmark campaigns to populate the winners page, or inspect another collection.'
              : 'Try clearing the filters or inspect the recorded runs.'}
          </p>
          <div className="actions">
            {allKinds
              .filter((k) => k !== kind)
              .map((k) => (
                <a className="button" key={k} href={'#winners?kind=' + k}>
                  View{' '}
                  {k === 'smoke'
                    ? 'smoke checks'
                    : k === 'benchmark'
                      ? 'benchmarks'
                      : 'diagnostics'}
                </a>
              ))}
            <a className="button" href="#results">
              Explore all recorded runs
            </a>
          </div>
        </div>
      )}
    </section>
  );
}

function Board({ board, select }: { board: WinnerBoard; select: (o: Observation) => void }) {
  const r = board.representative.run,
    leaders = board.records.filter((record) => record.rank === 1);
  const [expanded, setExpanded] = useState(false);
  const label =
    board.records.length === 1
      ? 'Best recorded frontend (only entrant)'
      : leaders.length > 1
        ? 'Joint winners'
        : 'Winner';
  return (
    <article className="winner-board">
      <div className="winner-heading">
        <div>
          <p className="eyebrow">{label}</p>
          <h3>{leaders.map((record) => record.frontend).join(' · ')}</h3>
          <p>
            {workloadLabel(r.config)} · seed {r.config.seed}
          </p>
          <div className="badges">
            <Badge>
              {r.backend} · {r.mode}
            </Badge>
            <Badge>
              {r.warmup_seconds}s warmup + {r.measurement_seconds}s measurement
            </Badge>
          </div>
        </div>
        <div className="winner-score">
          <strong>{format(leaders[0].score)}</strong>
          <span>median updates/s</span>
          <small>Target {r.config.hz} Hz</small>
        </div>
      </div>
      <p className="muted winner-context">
        {board.records.length} frontends · {board.hosts} hosts · {board.evaluatedGroups} eligible
        groups. Source <code>{r.context.source_hash?.slice(0, 12)}</code> · commit{' '}
        <code>{r.context.commit?.slice(0, 12) ?? 'not recorded'}</code>
        {r.context.dirty && ' · modified checkout'}
      </p>
      <div className="winner-records">
        {leaders.map((record) => (
          <Record key={record.frontend} record={record} select={select} />
        ))}
      </div>
      {board.records.length > leaders.length && (
        <details
          className="other-records"
          open={expanded}
          onToggle={(e) => setExpanded(e.currentTarget.open)}
        >
          <summary>All frontend records ({board.records.length})</summary>
          {expanded &&
            board.records
              .filter((record) => record.rank !== 1)
              .map((record) => <Record key={record.frontend} record={record} select={select} />)}
        </details>
      )}
    </article>
  );
}

function Record({ record, select }: { record: FrontendRecord; select: (o: Observation) => void }) {
  const [open, setOpen] = useState(false),
    [limit, setLimit] = useState(10);
  return (
    <div className="frontend-record">
      <div className="record-title">
        <strong>
          #{record.rank} {record.frontend}
        </strong>
        <span>{format(record.score)} updates/s</span>
      </div>
      <ul className="winning-hosts">
        {record.groups.slice(0, limit).map((g) => {
          const c = g.representative.campaign;
          return (
            <li key={g.key}>
              <a href={'#results?host=' + encodeURIComponent(c.host.id)}>{c.host.label}</a>
              <span>
                {c.host.cpu} · {c.host.gpu ?? 'GPU not recorded'} · {c.host.os}
              </span>
              <span>
                {g.successful}/{g.attempted} successful runs · {g.campaigns.length} campaigns
              </span>
              {g.limited > 0 && <Badge tone="amber">{g.limited} source-limited</Badge>}
              {g.successful < g.attempted && (
                <Badge tone="danger">{g.attempted - g.successful} without valid rate</Badge>
              )}
            </li>
          );
        })}
      </ul>
      {limit < record.groups.length && (
        <button onClick={() => setLimit((n) => n + 10)}>Show more tied configurations</button>
      )}
      <details
        className="winner-evidence"
        open={open}
        onToggle={(e) => setOpen(e.currentTarget.open)}
      >
        <summary>
          Inspect evidence for {record.frontend} ({record.groups.length} best configurations)
        </summary>
        {open && <GroupedResults groups={record.groups.slice(0, limit)} select={select} />}
      </details>
    </div>
  );
}
