import { useState } from 'react';
import { type ResultGroup, type CampaignGroup } from './aggregation';
import { type Observation, sourceLimited, workloadLabel } from './model';
import { Pill, date, format } from './presentation';

export function GroupedResults({
  groups,
  select,
}: {
  groups: ResultGroup[];
  select: (o: Observation) => void;
}) {
  return (
    <div className="group-list" aria-label="Grouped results">
      {groups.map((group) => (
        <Group key={group.key} group={group} select={select} />
      ))}
    </div>
  );
}

function Group({ group: g, select }: { group: ResultGroup; select: (o: Observation) => void }) {
  const [open, setOpen] = useState(false);
  const { campaign: c, run: r } = g.representative;
  return (
    <details className="result-group" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        <div className="group-identity">
          <strong>{r.frontend}</strong>
          <span>{c.host.label}</span>
          <small>{workloadLabel(r.config)}</small>
          <div className="pills">
            <Pill>
              {r.backend} · {r.mode}
            </Pill>
            <Pill>{c.classification}</Pill>
            {g.limited > 0 && <Pill tone="amber">{g.limited} source-limited</Pill>}
            {g.successful < g.attempted && (
              <Pill tone="danger">{g.attempted - g.successful} without valid rate</Pill>
            )}
            {g.incompleteContext && <Pill>Incomplete context · unmerged</Pill>}
          </div>
        </div>
        <dl className="group-stats">
          <div>
            <dt>Median updates/s</dt>
            <dd className="rate">{format(g.rates.median)}</dd>
            <small>Target {r.config.hz} Hz</small>
          </div>
          <div>
            <dt>Middle 50%</dt>
            <dd>{g.rates.count > 1 ? `${format(g.rates.q1)}–${format(g.rates.q3)}` : '—'}</dd>
            <small>
              {g.rates.count} campaign median{g.rates.count === 1 ? '' : 's'}
            </small>
          </div>
          <div>
            <dt>Successful / attempted</dt>
            <dd>
              {g.successful} / {g.attempted}
            </dd>
            <small>
              {g.campaigns.length} campaign{g.campaigns.length === 1 ? '' : 's'}
            </small>
          </div>
        </dl>
        <span className="group-expand">
          {open ? 'Hide' : 'Explore'} runs <span aria-hidden="true">{open ? '−' : '+'}</span>
        </span>
      </summary>
      {open && (
        <div className="group-content">
          <p className="muted small">
            {date(g.first)}–{date(g.last)} UTC · {r.warmup_seconds}s warmup +{' '}
            {r.measurement_seconds}s measurement. Each campaign contributes one median; spread
            describes campaign medians, not individual updates or confidence intervals.
          </p>
          <p className="muted small">
            {c.host.os} · {c.host.cpu} · {c.host.gpu ?? 'GPU not recorded'} ·{' '}
            {format(c.host.memory_gib)} GiB. Context <code>{r.context.fingerprint}</code>
          </p>
          {g.rates.count < 2 && (
            <p className="muted small">
              At least two campaigns with valid rates are needed to show between-campaign spread.
            </p>
          )}
          {g.campaigns.map((campaign) => (
            <Campaign key={campaign.campaign.id} group={campaign} select={select} />
          ))}
        </div>
      )}
    </details>
  );
}

function Campaign({
  group: g,
  select,
}: {
  group: CampaignGroup;
  select: (o: Observation) => void;
}) {
  const [open, setOpen] = useState(false),
    [limit, setLimit] = useState(25);
  return (
    <details className="campaign-group" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        <strong>{g.campaign.title}</strong>
        <span>
          {date(g.campaign.recorded_at)} UTC · {g.campaign.id}
        </span>
        <span>
          Median {format(g.rates.median)} updates/s · {g.rates.count} / {g.observations.length}{' '}
          successful runs in this group
        </span>
      </summary>
      {open && (
        <div className="campaign-content">
          <p className="muted small">
            Repetition range:{' '}
            {g.rates.count > 1
              ? `${format(g.rates.min)}–${format(g.rates.max)} updates/s`
              : '— (fewer than two valid repetitions)'}
            . Whole campaign: {g.campaign.completion_status}; {g.campaign.runs.length} of{' '}
            {g.campaign.planned_runs} planned runs recorded.
          </p>
          {g.campaign.notes && <p className="muted small">{g.campaign.notes}</p>}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Repetition</th>
                  <th>Submitted updates/s</th>
                  <th>Status</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {g.observations.slice(0, limit).map((o) => (
                  <tr key={o.run.id}>
                    <td>
                      {o.run.repetition}
                      <span className="cell-sub">{o.run.id}</span>
                    </td>
                    <td>{o.run.status === 'ok' ? format(o.run.metrics.submitted_hz) : '—'}</td>
                    <td>
                      <div className="pills">
                        <Pill tone={o.run.status === 'ok' ? 'success' : 'danger'}>
                          {o.run.status}
                        </Pill>
                        {sourceLimited(o.run) && <Pill tone="amber">Source limits</Pill>}
                      </div>
                    </td>
                    <td>
                      <button
                        className="btn-soft btn-small"
                        aria-label={`Details for ${o.run.frontend} ${o.run.id} in ${o.campaign.id}`}
                        onClick={() => select(o)}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {limit < g.observations.length && (
            <button className="btn-soft btn-small" onClick={() => setLimit((n) => n + 25)}>
              Show more runs ({g.observations.length - limit} remaining)
            </button>
          )}
        </div>
      )}
    </details>
  );
}
