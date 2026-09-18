import { useMemo, useState } from 'react';
import {
  collectWinners,
  closeRatePercent,
  CLOSE_RATE_PERCENTAGES,
  type WinnerBoard,
  type FrontendRecord,
} from './winners';
import { inDateRange } from './aggregation';
import { sectionBySlug, sectionOf, type Section } from './baseline';
import { GroupedResults } from './grouped-results';
import { Field, format, Pill, rateRange } from './presentation';
import { workloadLabel, type Observation } from './model';
import {
  DateRange,
  SectionHead,
  SectionRail,
  Select,
  contextLine,
  refreshLabel,
  scaleLabel,
  shortCommit,
} from './section-rail';
import { sectionHref } from './results-page';
import { BoardChart } from './board-chart';
// Profile radar (top-left of the winner card). Self-contained — remove its
// import, its element below and its CSS block to drop it.
import { ProfileRadar } from './winner-radar';

/** Distinct display scales in the collection, as select options ("1x", "2x"). */
export function scaleOptions(observations: readonly Observation[]): [string, string][] {
  return [
    ...new Set(
      observations.flatMap((o) =>
        o.run.context.pixel_ratio === null ? [] : [o.run.context.pixel_ratio],
      ),
    ),
  ]
    .sort((a, b) => a - b)
    .map((ratio) => [String(ratio), scaleLabel(ratio)]);
}
/** Distinct hosts in the collection, as [id, label] select options, sorted by id. */
export function hostOptions(observations: readonly Observation[]): [string, string][] {
  const labels = new Map<string, string>();
  for (const { campaign: c } of observations)
    if (!labels.has(c.host.id)) labels.set(c.host.id, c.host.label);
  return [...labels].sort((a, b) => a[0].localeCompare(b[0]));
}
/** Benchmark observations within the page's date range, display scale and host. */
export function eligibleObservations(
  observations: readonly Observation[],
  filters: URLSearchParams,
): Observation[] {
  const scale = filters.get('scale'),
    host = filters.get('host');
  return observations.filter(
    ({ campaign: c, run: r }) =>
      c.classification === 'benchmark' &&
      (!scale || String(r.context.pixel_ratio) === scale) &&
      (!host || c.host.id === host) &&
      inDateRange(c.recorded_at, filters.get('from') ?? '', filters.get('to') ?? ''),
  );
}

export function RankingControls({
  observations,
  filters,
  filter,
  reset,
}: {
  observations: readonly Observation[];
  filters: URLSearchParams;
  filter: (key: string, value: string) => void;
  reset: string;
}) {
  const tolerance = closeRatePercent(filters.get('close'));
  return (
    <div className="toolbar toolbar-5" role="group" aria-label="Ranking controls">
      <Field label="Close update rates">
        <select
          aria-label="Close update rates"
          value={tolerance}
          onChange={(e) => filter('close', e.target.value)}
        >
          {CLOSE_RATE_PERCENTAGES.map((percent) => (
            <option key={percent} value={percent}>
              {percent === 0
                ? 'Exact rates'
                : `Within ${percent}%${percent === 2 ? ' (default)' : ''}`}
            </option>
          ))}
        </select>
      </Field>
      <Select
        label="Host"
        all="All hosts"
        value={filters.get('host') ?? ''}
        onChange={(v) => filter('host', v)}
        options={hostOptions(observations)}
      />
      <Select
        label="Display scale"
        all="All scales"
        value={filters.get('scale') ?? ''}
        onChange={(v) => filter('scale', v)}
        options={scaleOptions(observations)}
      />
      <DateRange filters={filters} filter={filter} />
      <div className="toolbar-end">
        {['close', 'host', 'scale', 'from', 'to', 'section'].some((k) => filters.get(k)) && (
          <a href={reset}>Reset</a>
        )}
      </div>
    </div>
  );
}

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
  const section = sectionBySlug(filters.get('section'));
  const tolerance = closeRatePercent(filters.get('close'));
  const visible = useMemo(
    () => eligibleObservations(observations, filters),
    [observations, filters],
  );
  const collection = useMemo(() => collectWinners(visible, tolerance), [visible, tolerance]);
  const counts = new Map<string, number>();
  for (const board of collection.boards)
    if (board.section)
      counts.set(board.section.slug, (counts.get(board.section.slug) ?? 0) + board.records.length);
  const boards = section
    ? collection.boards.filter((b) => b.section?.slug === section.slug)
    : collection.boards;
  const href = sectionHref('winners')(filters);
  return (
    <section className="winners-page" aria-label="Winners across hosts">
      <SectionRail counts={counts} current={section} href={href} unit="record" />
      {section && <SectionHead section={section} />}
      <RankingControls
        observations={observations}
        filters={filters}
        filter={filter}
        reset="#winners"
      />
      <div className="notice">
        <p>
          <strong>Best observed records per section, across all hosts.</strong> Ranking starts with
          campaign-weighted median submitted updates/s, then uses triangle area to balance
          throughput, memory and CPU for close rates. Hardware, frontend versions, source revisions
          and display settings may differ between records; this is not a hardware-independent
          library ranking, not a controlled comparison and not displayed FPS. Rates are paced by the
          60 Hz target; reaching it does not establish maximum rendering capacity.
        </p>
      </div>
      <p className="muted small aggregation-note">
        One best record per frontend and section, drawn from any host. Within {tolerance}% of the
        fastest remaining configuration rates form a band. Earlier bands rank first; within each
        band, the largest triangle area wins. Its axes are rate / target (capped at 1), lowest RSS /
        RSS and lowest CPU / CPU, using all eligible configurations in that band. Area is
        (throughput × RAM + RAM × CPU + CPU × throughput) / 3. Records at different source revisions
        or display scales stay separate groups and compete in the same section.{' '}
        {section ? (collection.excludedBySection[section.slug] ?? 0) : collection.excludedGroups}{' '}
        groups are excluded {section ? 'from this section' : 'across all sections'} for missing
        rates, unknown display scale, incomplete context or incomplete/non-positive resource
        measurements. This is a ranking preference, not a statistical significance test.
      </p>
      {boards.length ? (
        <div className="winner-boards">
          {boards.map((board) => (
            <Board key={board.key} board={board} select={select} />
          ))}
        </div>
      ) : (
        <div className="empty">
          <h2>No eligible benchmark results</h2>
          <p>
            {section
              ? `No published campaign has an eligible record for ${section.title} in this date range and display scale.`
              : 'Published baseline campaigns with complete context and positive CPU and memory measurements populate the winners page.'}
          </p>
          <div className="actions">
            {section && (
              <a className="btn-soft" href="#winners">
                All sections
              </a>
            )}
            <a className="btn-soft" href="#results">
              Explore all recorded runs
            </a>
            <a className="btn-soft" href="#suite">
              Read the baseline suite
            </a>
          </div>
        </div>
      )}
    </section>
  );
}

function boardTitle(board: WinnerBoard, section: Section | null): string {
  return section ? section.title : workloadLabel(board.representative.run.config);
}
function Board({ board, select }: { board: WinnerBoard; select: (o: Observation) => void }) {
  const r = board.representative.run,
    section = board.section,
    leaders = board.records.filter((record) => record.rank === 1);
  const [expanded, setExpanded] = useState(false);
  // Shared highlight for the profile glyphs and the bar charts, scoped to this
  // board so sibling boards do not cross-highlight.
  const [hovered, setHovered] = useState<string | null>(null);
  const label =
    board.records.length === 1
      ? 'Best recorded frontend (only entrant)'
      : leaders.length > 1
        ? 'Joint winners'
        : 'Winner';
  const scales = new Set(
    board.records.flatMap((record) =>
      record.groups.map((g) => g.representative.run.context.pixel_ratio),
    ),
  );
  const image = r.config.view !== 'waveform';
  return (
    <article className="winner-board" id={section ? 'winners-' + section.slug : undefined}>
      <header className="winner-section">
        {section && <span className="rail-index">{section.index}</span>}
        <strong>{boardTitle(board, section)}</strong>
        <span className="muted">
          spans {board.revisions} source revision{board.revisions === 1 ? '' : 's'} · {board.hosts}{' '}
          host{board.hosts === 1 ? '' : 's'}
        </span>
      </header>
      <div className="board-layout">
        <div className="winner-profiles">
          <ProfileRadar board={board} hovered={hovered} onHover={setHovered} />
        </div>
        <div className="board-facts">
          <div className="winner-heading">
            <div>
              <p className="eyebrow">{label}</p>
              <h3>{leaders.map((record) => record.frontend).join(' · ')}</h3>
              <p>
                {workloadLabel(r.config)} · seed {r.config.seed}
              </p>
              <div className="pills">
                <Pill>
                  {r.backend} · {r.mode}
                </Pill>
                <Pill>
                  {r.warmup_seconds}s warmup + {r.measurement_seconds}s measurement
                </Pill>
                {scales.size > 1 && <Pill tone="amber">Records at different display scales</Pill>}
              </div>
            </div>
            <div className="winner-score">
              <strong>
                {rateRange(
                  Math.min(...leaders.map((r) => r.minimumScore)),
                  Math.max(...leaders.map((r) => r.score)),
                )}
              </strong>
              <span>median updates/s</span>
              <small>Target {r.config.hz} Hz</small>
            </div>
          </div>
          <p className="muted winner-context">
            {board.records.length} frontend{board.records.length === 1 ? '' : 's'} · {board.hosts}{' '}
            host
            {board.hosts === 1 ? '' : 's'} · {board.evaluatedGroups} eligible group
            {board.evaluatedGroups === 1 ? '' : 's'}. Priority: throughput bands (
            {board.closeRatePercent}%) → triangle area. Resource values use equal campaign weights;
            CPU 100% means one logical CPU.
          </p>
          {image && (
            <p className="muted">
              Image sections rasterise {r.config.width} × {r.config.height} × scale² device pixels
              per plot, so a record at 2x scaling pushes four times the pixels of one at 1x. Records
              at different scales compete in the same section and are marked.
            </p>
          )}
        </div>
        <BoardChart board={board} hovered={hovered} onHover={setHovered} />
        <div className="board-records">
          <div className="winner-records">
            {leaders.map((record) => (
              <Record
                key={record.frontend}
                record={record}
                select={select}
                marked={scales.size > 1}
              />
            ))}
          </div>
          {board.records.length > leaders.length && (
            <details
              className="disclosure other-records"
              open={expanded}
              onToggle={(e) => setExpanded(e.currentTarget.open)}
            >
              <summary>All frontend records ({board.records.length})</summary>
              {expanded &&
                board.records
                  .filter((record) => record.rank !== 1)
                  .map((record) => (
                    <Record
                      key={record.frontend}
                      record={record}
                      select={select}
                      marked={scales.size > 1}
                    />
                  ))}
            </details>
          )}
        </div>
      </div>
    </article>
  );
}

function Record({
  record,
  select,
  marked,
}: {
  record: FrontendRecord;
  select: (o: Observation) => void;
  marked: boolean;
}) {
  const [open, setOpen] = useState(false),
    [limit, setLimit] = useState(10);
  const contexts = record.groups.map((g) => g.representative.run.context);
  const displayedGroups = [
    record.representativeGroup,
    ...record.groups.filter((g) => g !== record.representativeGroup),
  ];
  const commits = [...new Set(contexts.map((x) => shortCommit(x.commit)))],
    scales = [...new Set(contexts.map((x) => scaleLabel(x.pixel_ratio)))],
    refreshes = [...new Set(contexts.map((x) => refreshLabel(x.refresh_hz)))],
    protocols = [...new Set(contexts.map((x) => x.display_protocol ?? 'protocol not recorded'))];
  return (
    <div className="frontend-record">
      <div className="record-title">
        <strong>
          #{record.rank} {record.frontend}
        </strong>
        <span>{rateRange(record.minimumScore, record.score)} updates/s</span>
      </div>
      <p className="record-resources">
        Rate band {record.rateBand + 1} · Triangle area: {(record.profile.area * 100).toFixed(2)}% ·
        Median peak RSS: {format(record.memoryMib)} MiB · Median mean CPU:{' '}
        {format(record.cpuPercent)}%
        {record.groups.length > 1 &&
          ' · Profile values describe the marked tied configuration below.'}
      </p>
      <p className="record-context muted small">
        commit {commits.join(' / ')} · {scales.join(' / ')} · {refreshes.join(' / ')} ·{' '}
        {protocols.join(' / ')}
      </p>
      <ul className="winning-hosts">
        {displayedGroups.slice(0, limit).map((g) => {
          const { campaign: c, run: r } = g.representative;
          const slug = sectionOf(r.config)?.slug;
          return (
            <li key={g.key}>
              {record.groups.length > 1 && g === record.representativeGroup && (
                <strong>Shown in profile</strong>
              )}
              <a
                href={
                  '#results?host=' +
                  encodeURIComponent(c.host.id) +
                  (slug ? '&section=' + slug : '')
                }
              >
                {c.host.label}
              </a>
              <span>
                {c.host.cpu} · {c.host.gpu ?? 'GPU not recorded'} · {c.host.os}
              </span>
              <span>{contextLine(r.context)}</span>
              <span>
                {g.successful}/{g.attempted} successful runs · {g.campaigns.length} campaign
                {g.campaigns.length === 1 ? '' : 's'}
              </span>
              <span>
                {format(g.rates.median)} updates/s · Median peak RSS{' '}
                {g.resources.memoryMib === null
                  ? 'unavailable'
                  : `${format(g.resources.memoryMib)} MiB`}{' '}
                · Median mean CPU{' '}
                {g.resources.cpuPercent === null
                  ? 'unavailable'
                  : `${format(g.resources.cpuPercent)}%`}
              </span>
              {marked && (
                <Pill tone="amber">{scaleLabel(r.context.pixel_ratio)} display scale</Pill>
              )}
              {g.sourceLimited > 0 && <Pill tone="amber">{g.sourceLimited} source-limited</Pill>}
              {g.frontendLimited > 0 && (
                <Pill tone="info">{g.frontendLimited} frontend-limited</Pill>
              )}
              {g.successful < g.attempted && (
                <Pill tone="danger">{g.attempted - g.successful} without valid rate</Pill>
              )}
            </li>
          );
        })}
      </ul>
      {limit < record.groups.length && (
        <button className="btn-soft btn-small" onClick={() => setLimit((n) => n + 10)}>
          Show more tied configurations
        </button>
      )}
      <details
        className="disclosure winner-evidence"
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
