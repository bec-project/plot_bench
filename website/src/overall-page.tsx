import { useMemo } from 'react';
import { SECTIONS } from './baseline';
import type { Observation } from './model';
import { collectOverall } from './overall';
import { closeRatePercent } from './winners';
import { sectionHref } from './results-page';
import { RankingControls, eligibleObservations } from './winners-page';

export function OverallPage({
  observations,
  filters,
  filter,
}: {
  observations: Observation[];
  filters: URLSearchParams;
  filter: (key: string, value: string) => void;
}) {
  const tolerance = closeRatePercent(filters.get('close'));
  const visible = useMemo(
    () => eligibleObservations(observations, filters),
    [observations, filters],
  );
  const ranking = useMemo(() => collectOverall(visible, tolerance), [visible, tolerance]);
  // Section links carry the close-rate, scale and date filters so the linked board
  // shows exactly the placement that was clicked.
  const sectionLink = sectionHref('winners')(filters);
  return (
    <section className="overall-page" aria-label="Overall ranking">
      <RankingControls
        observations={observations}
        filters={filters}
        filter={filter}
        reset="#overall"
      />
      <div className="notice">
        <p>
          <strong>Placements added up, nothing else.</strong> Each frontend's competition rank on
          the seven section boards is summed; the lowest total wins, ties go to the frontend with
          more section wins, and remaining ties are joint (1, 1, 3). No update rate, memory or CPU
          value is pooled across sections or hosts. Paced sections, where several frontends hold the
          60 Hz target, are decided by median peak RSS and then mean CPU within the {tolerance}%
          tolerance, so the total reflects resource use as much as throughput. The seven records
          behind one frontend may come from different hosts, source revisions and display scales;
          this is a summary of best-observed records, not a controlled comparison, and more
          submissions can change every placement.
        </p>
      </div>
      {ranking.entries.length ? (
        <>
          <div className="table-wrap">
            <table className="overall-table">
              <thead>
                <tr>
                  <th scope="col">Rank</th>
                  <th scope="col">Frontend</th>
                  <th scope="col">Total</th>
                  <th scope="col">Wins</th>
                  {SECTIONS.map((s) => (
                    <th scope="col" key={s.slug}>
                      <a href={sectionLink(s.slug)} title={s.title}>
                        <span className="rail-index">{s.index}</span>
                        <span className="sr-only">{s.title}</span>
                      </a>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ranking.entries.map((entry) => (
                  <tr key={entry.frontend}>
                    <td>
                      <strong>#{entry.rank}</strong>
                    </td>
                    <td>
                      <strong className="frontend">
                        <i className="dot" />
                        {entry.frontend}
                      </strong>
                      <span className="cell-sub">
                        {entry.hosts.length} host{entry.hosts.length === 1 ? '' : 's'} ·{' '}
                        {entry.revisions} revision{entry.revisions === 1 ? '' : 's'}
                        {entry.sourceLimitedGroups > 0 &&
                          ` · ${entry.sourceLimitedGroups} source-limited group${entry.sourceLimitedGroups === 1 ? '' : 's'}`}
                        {entry.frontendLimitedGroups > 0 &&
                          ` · ${entry.frontendLimitedGroups} frontend-limited group${entry.frontendLimitedGroups === 1 ? '' : 's'}`}
                      </span>
                    </td>
                    <td className="overall-total">{entry.total}</td>
                    <td>{entry.wins}</td>
                    {entry.placements.map((p) => (
                      <td key={p.section.slug}>
                        <a
                          className={p.rank === 1 ? 'placement placement-win' : 'placement'}
                          href={sectionLink(p.section.slug)}
                          aria-label={`${entry.frontend} ranks ${p.rank} in ${p.section.title}`}
                        >
                          {p.rank}
                        </a>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="overall-legend" aria-label="Section columns">
            {SECTIONS.map((s) => (
              <li key={s.slug}>
                <span className="rail-index">{s.index}</span>
                <a href={sectionLink(s.slug)}>{s.title}</a>
              </li>
            ))}
          </ul>
          <p className="muted small">
            Section columns show the competition rank on that board; open a section to see the
            record, its host and evidence. {ranking.excludedGroups} groups are excluded for missing
            rates, unknown display scale or incomplete context.
          </p>
        </>
      ) : (
        <div className="empty">
          <h2>No overall ranking yet</h2>
          <p>
            A frontend enters the overall ranking once it holds an eligible benchmark record in all{' '}
            {SECTIONS.length} sections of the baseline suite.
          </p>
          <div className="actions">
            <a className="btn-soft" href="#winners">
              Section winners
            </a>
            <a className="btn-soft" href="#suite">
              Read the baseline suite
            </a>
          </div>
        </div>
      )}
      {ranking.incomplete.length > 0 && (
        <section className="panel overall-incomplete" aria-label="Frontends without a full set">
          <h2>Not ranked: missing sections</h2>
          <p className="muted small">
            These frontends have eligible records in some sections only. They keep their places on
            the section boards, so the placements above are counted exactly as those boards show
            them, including the places these frontends hold.
          </p>
          <ul className="incomplete-list">
            {ranking.incomplete.map((f) => (
              <li key={f.frontend}>
                <strong className="frontend">
                  <i className="dot" />
                  {f.frontend}
                </strong>
                <span>
                  {f.present.length} of {SECTIONS.length} sections · missing{' '}
                  {f.missing.map((s, i) => (
                    <span key={s.slug}>
                      {i > 0 && ', '}
                      <a href={sectionLink(s.slug)}>{s.title}</a>
                    </span>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
