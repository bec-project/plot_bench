import { BASELINE, SECTIONS, fixedConditions } from './baseline';
import { REPOSITORY, workloadLabel } from './model';
import { layoutLabel } from './section-rail';

const COMMAND =
  './scripts/plotbench run --baseline --frontends pyqtgraph matplotlib --output results/baseline';

export function SuitePage() {
  return (
    <section className="suite-page" aria-label="The baseline suite">
      <section className="panel">
        <div className="panel-head">
          <h2>{BASELINE.name}</h2>
          <span className="muted small">{SECTIONS.length} sections · one suite for every host</span>
        </div>
        <p>
          Every published campaign is one unmodified run of this suite. Its seven sections are the
          cases of <code>scenarios/baseline.json</code> in the repository; the site derives the
          table below from that file, so this page cannot drift from what the runner executes.
        </p>
        <p className="muted small">{fixedConditions()}</p>
        <div className="table-wrap">
          <table className="suite-table">
            <thead>
              <tr>
                <th scope="col">Section</th>
                <th scope="col">Title</th>
                <th scope="col">View</th>
                <th scope="col">Layout</th>
                <th scope="col">Workload</th>
              </tr>
            </thead>
            <tbody>
              {SECTIONS.map((s) => (
                <tr key={s.slug}>
                  <td>
                    <span className="rail-index">{s.index}</span>
                    <span className="cell-sub">
                      <code>{s.slug}</code>
                    </span>
                  </td>
                  <td>
                    <strong>{s.title}</strong>
                  </td>
                  <td>{s.config.view}</td>
                  <td>{layoutLabel(s.config)}</td>
                  <td>{workloadLabel(s.config)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <h2>Fixed conditions</h2>
        <dl className="kv detail-grid">
          <dt>Source</dt>
          <dd>
            {BASELINE.backend} generator, {BASELINE.mode} delivery over WebSockets
          </dd>
          <dt>Timing</dt>
          <dd>
            {BASELINE.warmupSeconds} s warmup, {BASELINE.measurementSeconds} s measurement,{' '}
            {BASELINE.cooldownSeconds} s cooldown, {BASELINE.repetitions} repetitions per section
          </dd>
          <dt>Window</dt>
          <dd>
            The frontends' default 1100 × 820 logical window; recorded viewports remain evidence
          </dd>
          <dt>Frontends</dt>
          <dd>
            {BASELINE.frontends.join(' · ')} — any subset may be run, each covers all sections
          </dd>
          <dt>Display</dt>
          <dd>
            A visible desktop (native or Wayland) with a fixed refresh rate and display scale;
            JFreeChart may use verified XWayland. Headless and plain X11 campaigns are diagnostic
          </dd>
        </dl>
      </section>
      <section className="panel">
        <h2>Run it</h2>
        <p className="muted small">
          Only <code>--frontends</code> may narrow the suite; timing, repetition, mode, backend and
          limit overrides make a campaign unpublishable. Then export the campaign on the{' '}
          <a href="#contribute">contribute page</a>.
        </p>
        <pre>{COMMAND}</pre>
        <div className="actions">
          <a className="btn-primary" href="#contribute">
            Contribute results
          </a>
          <a className="btn-soft" href={REPOSITORY + '/blob/main/docs/methodology.md'}>
            Measurement methodology ↗
          </a>
          <a className="btn-soft" href={REPOSITORY + '/blob/main/docs/suites.md'}>
            Suite reference ↗
          </a>
        </div>
      </section>
    </section>
  );
}
