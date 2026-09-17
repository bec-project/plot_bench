import { useEffect, useMemo, useState } from 'react';
import { groupObservations, inDateRange, type ResultGroup } from './aggregation';
import { GROUP_ORDERS, ORDER_NOTES, compareGroups, compareRuns, groupOrder } from './ordering';
import { SECTIONS, sectionBySlug, sectionOf, type Section } from './baseline';
import { GroupedResults } from './grouped-results';
import { sourceLimited, frontendLimited, type Observation, type Submission } from './model';
import { Pill, date, format } from './presentation';
import {
  DateRange,
  SectionCoverage,
  SectionDivider,
  SectionHead,
  SectionRail,
  Select,
  scaleLabel,
  shortCommit,
} from './section-rail';

const PAGE_SIZE = 25;
const distinct = (values: string[]) => [...new Set(values)].sort();
const sectionIndex = (g: ResultGroup) => sectionOf(g.representative.run.config)?.index ?? Infinity;
/** Slugs of the sections a set of runs covers. */
export function coveredSections(runs: readonly Observation[]): Set<string> {
  return new Set(runs.flatMap((o) => sectionOf(o.run.config)?.slug ?? []));
}
function withSection(filters: URLSearchParams, view: string, slug: string | null): string {
  const params = new URLSearchParams(filters);
  slug ? params.set('section', slug) : params.delete('section');
  return '#' + view + (params.size ? '?' + params.toString() : '');
}
export const sectionHref = (view: string) => (filters: URLSearchParams) => (slug: string | null) =>
  withSection(filters, view, slug);

export function ResultsPage({
  campaigns,
  all,
  filters,
  filter,
  select,
}: {
  campaigns: Submission[];
  all: Observation[];
  filters: URLSearchParams;
  filter: (key: string, value: string) => void;
  select: (o: Observation) => void;
}) {
  const section = sectionBySlug(filters.get('section'));
  const hosts = useMemo(() => distinct(campaigns.map((c) => c.host.id)), [campaigns]);
  // Host, frontend and dates narrow the whole collection; the rail counts what
  // remains per section so a section link says what it leads to.
  const narrowed = useMemo(
    () =>
      all.filter(
        ({ campaign: c, run: r }) =>
          (!filters.get('host') || c.host.id === filters.get('host')) &&
          (!filters.get('frontend') || r.frontend === filters.get('frontend')) &&
          inDateRange(c.recorded_at, filters.get('from') ?? '', filters.get('to') ?? ''),
      ),
    [all, filters],
  );
  const visible = useMemo(
    () =>
      section ? narrowed.filter((o) => sectionOf(o.run.config)?.slug === section.slug) : narrowed,
    [narrowed, section],
  );
  const grouped = filters.get('layout') !== 'runs';
  const order = groupOrder(filters.get('sort'));
  // Sections keep their suite order; inside a section the selected order applies,
  // by default the highest median updates/s first.
  const allGroups = useMemo(
    () =>
      groupObservations(narrowed).sort(
        (a, b) => sectionIndex(a) - sectionIndex(b) || compareGroups(order)(a, b),
      ),
    [narrowed, order],
  );
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    for (const g of allGroups) {
      const slug = sectionOf(g.representative.run.config)?.slug;
      if (slug) m.set(slug, (m.get(slug) ?? 0) + 1);
    }
    return m;
  }, [allGroups]);
  const groups = section
    ? allGroups.filter((g) => sectionOf(g.representative.run.config)?.slug === section.slug)
    : allGroups;
  const runs = useMemo(
    () =>
      [...visible].sort(
        (a, b) =>
          (sectionOf(a.run.config)?.index ?? Infinity) -
            (sectionOf(b.run.config)?.index ?? Infinity) || compareRuns(order)(a, b),
      ),
    [visible, order],
  );
  const itemCount = grouped ? groups.length : runs.length;
  const [page, setPage] = useState(0);
  useEffect(() => setPage(0), [filters]);
  const href = sectionHref('results')(filters);
  const filtered = ['host', 'frontend', 'from', 'to', 'sort'].some((k) => filters.get(k));
  const pageGroups = groups.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  // In the all-sections view the list is chunked by section with a divider per chunk.
  const chunks: { section: Section | null; groups: ResultGroup[] }[] = [];
  for (const g of pageGroups) {
    const s = sectionOf(g.representative.run.config);
    const last = chunks[chunks.length - 1];
    if (last && last.section?.slug === s?.slug) last.groups.push(g);
    else chunks.push({ section: s, groups: [g] });
  }
  return (
    <>
      <Collection campaigns={campaigns} all={all} hosts={hosts} />
      <SectionRail counts={counts} current={section} href={href} />
      {section && <SectionHead section={section} />}
      {all.length === 0 ? (
        <Empty />
      ) : (
        <section className="panel results-panel" aria-label="Measurements">
          <div className="toolbar toolbar-5" role="group" aria-label="Filters">
            <Select
              label="Host"
              all="All hosts"
              value={filters.get('host') ?? ''}
              onChange={(v) => filter('host', v)}
              options={hosts.map((id) => [id, campaigns.find((c) => c.host.id === id)!.host.label])}
            />
            <Select
              label="Frontend"
              all="All frontends"
              value={filters.get('frontend') ?? ''}
              onChange={(v) => filter('frontend', v)}
              options={distinct(all.map((o) => o.run.frontend)).map((x) => [x, x])}
            />
            <DateRange filters={filters} filter={filter} />
            <Select
              label="Order"
              all={GROUP_ORDERS[0][1]}
              value={filters.get('sort') ?? ''}
              onChange={(v) => filter('sort', v)}
              options={GROUP_ORDERS.filter(([key]) => key !== 'rate')}
            />
            <div className="toolbar-end">
              {(filtered || section || !grouped) && <a href="#results">Reset</a>}
            </div>
          </div>
          <div className="panel-head">
            <div>
              <h2>{section ? section.title : 'All sections'}</h2>
              <p className="muted small">
                {grouped ? `${groups.length} groups · ` : ''}
                {visible.length} individual run{visible.length === 1 ? '' : 's'} · submitted updates
                per second, not displayed FPS
              </p>
            </div>
            <div className="segmented" role="group" aria-label="Results view">
              <button
                type="button"
                className={grouped ? 'seg seg-on' : 'seg'}
                aria-pressed={grouped}
                onClick={() => filter('layout', '')}
              >
                Grouped
              </button>
              <button
                type="button"
                className={grouped ? 'seg' : 'seg seg-on'}
                aria-pressed={!grouped}
                onClick={() => filter('layout', 'runs')}
              >
                Individual runs
              </button>
            </div>
          </div>
          {grouped && (
            <p className="muted small aggregation-note">
              One group per frontend, host, source revision, display scale and identical recorded
              context (refresh rate, display protocol, renderer and library versions); any context
              change starts a new group. Median of campaign medians, with each campaign weighted
              equally; middle 50% shows the spread of campaign medians. Ordered by section, then{' '}
              {ORDER_NOTES[order]}. Expand a group to inspect campaigns and repetitions.
            </p>
          )}
          {visible.length ? (
            <>
              {grouped ? (
                chunks.map((chunk, i) => (
                  <div key={chunk.section?.slug ?? 'other-' + i}>
                    {!section && chunk.section && (
                      <SectionDivider section={chunk.section} href={href(chunk.section.slug)} />
                    )}
                    <GroupedResults
                      groups={chunk.groups}
                      select={select}
                      section={section ? null : chunk.section}
                    />
                  </div>
                ))
              ) : (
                <RunTable
                  runs={runs.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)}
                  select={select}
                />
              )}
              <div className="pagination">
                <span>
                  {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, itemCount)} of{' '}
                  {itemCount} {grouped ? 'groups' : 'runs'}
                </span>
                <div>
                  <button
                    className="btn-soft"
                    disabled={page === 0}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    Previous
                  </button>
                  <button
                    className="btn-soft"
                    disabled={(page + 1) * PAGE_SIZE >= itemCount}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          ) : (
            <Empty filtered />
          )}
        </section>
      )}
    </>
  );
}

function RunTable({ runs, select }: { runs: Observation[]; select: (o: Observation) => void }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Frontend / host</th>
            <th>Section</th>
            <th>Submitted / target</th>
            <th>Context</th>
            <th>
              <span className="sr-only">Details</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((o) => {
            const { campaign: c, run: r } = o;
            const s = sectionOf(r.config);
            const valid = r.status === 'ok',
              ratio =
                valid && r.metrics.submitted_hz !== null
                  ? r.metrics.submitted_hz / r.config.hz
                  : null;
            return (
              <tr key={c.id + '/' + r.id}>
                <td>
                  <strong className="frontend">
                    <i className="dot" />
                    {r.frontend}
                  </strong>
                  <span className="cell-sub">{c.host.label}</span>
                </td>
                <td>
                  <span>{s ? `${s.index} · ${s.title}` : 'Outside the suite'}</span>
                  <span className="cell-sub">{r.scenario}</span>
                </td>
                <td>
                  <span className="rate">
                    {valid ? format(r.metrics.submitted_hz) : '—'} <small>/ {r.config.hz} Hz</small>
                  </span>
                  <div
                    className="bar"
                    aria-label={
                      ratio === null ? 'No valid rate' : `${format(ratio * 100)} percent of target`
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
                  <div className="pills">
                    <Pill>
                      <code>{shortCommit(r.context.commit)}</code>
                    </Pill>
                    <Pill>{scaleLabel(r.context.pixel_ratio)}</Pill>
                    {!valid && <Pill tone="danger">{r.status}</Pill>}
                    {sourceLimited(r) && <Pill tone="amber">Source-limited</Pill>}
                    {frontendLimited(r) && <Pill tone="info">Frontend-limited</Pill>}
                  </div>
                  <span className="cell-sub">
                    repetition {r.repetition} · {date(c.recorded_at)}
                  </span>
                </td>
                <td>
                  <button
                    className="btn-soft btn-icon"
                    aria-label={`Details for ${r.frontend} ${r.id} in ${c.id}`}
                    onClick={() => select(o)}
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
  );
}

function Collection({
  campaigns,
  all,
  hosts,
}: {
  campaigns: Submission[];
  all: Observation[];
  hosts: string[];
}) {
  const covered = coveredSections(all);
  return (
    <section className="panel collection" aria-label="Collection">
      <div className="panel-head">
        <h2>Collection</h2>
        <span className="muted small">Submitted updates per second, not displayed FPS</span>
      </div>
      <div className="status-grid">
        <div className="stat">
          <span className="stat-label">Hosts</span>
          <strong className="stat-value">{hosts.length.toLocaleString()}</strong>
          <small className="stat-note">
            {distinct(campaigns.map((c) => c.host.architecture)).join(' · ') ||
              'Awaiting contributions'}
          </small>
        </div>
        <div className="stat">
          <span className="stat-label">Campaigns</span>
          <strong className="stat-value">{campaigns.length.toLocaleString()}</strong>
          <small className="stat-note">
            {campaigns.length
              ? `Latest ${date(campaigns[0].recorded_at)} · ${all.length} runs`
              : 'No campaigns yet'}
          </small>
        </div>
        <div className="stat">
          <span className="stat-label">Frontends</span>
          <strong className="stat-value">{distinct(all.map((o) => o.run.frontend)).length}</strong>
          <small className="stat-note">Each rendering path measured separately</small>
        </div>
        <div className="stat">
          <span className="stat-label">Sections covered</span>
          <strong className="stat-value">
            {covered.size} of {SECTIONS.length}
          </strong>
          <small className="stat-note">Of the official baseline suite</small>
        </div>
      </div>
      <SectionCoverage covered={covered} href={(slug) => '#results?section=' + slug} />
    </section>
  );
}

export function Empty({ filtered = false }: { filtered?: boolean }) {
  return (
    <div className="empty">
      <h2>{filtered ? 'No matching runs' : 'The collection starts here'}</h2>
      <p>
        {filtered
          ? 'No run of the collection matches this section, host, frontend and date range.'
          : 'No baseline campaign has been published yet. Run the official suite on your machine and contribute the export.'}
      </p>
      <div className="actions">
        {filtered ? (
          <a className="btn-soft" href="#results">
            Clear filters
          </a>
        ) : (
          <>
            <a className="btn-soft" href="#suite">
              Read the baseline suite
            </a>
            <a className="btn-primary" href="#contribute">
              Contribute results
            </a>
          </>
        )}
      </div>
    </div>
  );
}
