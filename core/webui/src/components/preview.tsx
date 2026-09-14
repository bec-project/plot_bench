import { showsImage, showsWaveform } from '../config-fields';
import type { Config, Plan } from '../types';
import { CommandLine } from './commands';

const PREVIEW_LIMIT = 250;

function mmss(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

// Compact plot layout of one run, e.g. "2×3 wf · 3 img", "2×3 wf" or "3 img";
// the curve count is only spelled out when a plot draws more than one curve.
export function plotsLabel(config: Config): string {
  const view = String(config.view);
  const parts: string[] = [];
  if (showsWaveform(view)) {
    const plots = Number(config.waveform_plots ?? 1);
    const curves = Number(config.curves ?? 1);
    parts.push(`${curves > 1 ? `${plots}×${curves}` : plots} wf`);
  }
  if (showsImage(view)) parts.push(`${Number(config.image_plots ?? 1)} img`);
  return parts.join(' · ');
}

export function PlanPreview(props: {
  plan: Plan | null;
  error: string | null;
  pending: boolean;
  commands: { label: string; command: string }[];
  needsSave: boolean;
}) {
  const { plan, error, pending, commands, needsSave } = props;
  return (
    <section class="panel">
      <div class="panel-head">
        <h2>Execution preview</h2>
        {pending ? <span class="pill pill-pending">validating…</span> : null}
      </div>
      {error ? <p id="plan-error" class="alert" role="alert">{error}</p> : null}
      {plan ? (
        <>
          <p id="plan-summary" class="summary">
            <strong>{plan.case_count.toLocaleString()}</strong> workloads ·{' '}
            <strong>{plan.run_count.toLocaleString()}</strong> runs · at least{' '}
            <strong>{(plan.estimate.minimum_seconds / 60).toFixed(1)}</strong> min
          </p>
          <p class="muted small">
            Each run: startup → warmup {plan.warmup_seconds}s → measure {plan.measurement_seconds}s → cooldown{' '}
            {plan.cooldown_seconds}s (≈ {mmss(plan.warmup_seconds + plan.measurement_seconds + plan.cooldown_seconds)}{' '}
            each). Startup, replay preload, teardown and report generation add more.
          </p>
          <div class="run-here">
            <p class="block-label">
              Run this configuration
              {needsSave ? <span class="run-note"> · save it first</span> : null}
            </p>
            {commands.map((entry) => (
              <CommandLine label={entry.label} command={entry.command} />
            ))}
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Workload</th>
                  <th>Plots</th>
                  <th>Frontend</th>
                  <th>Source</th>
                  <th>Mode</th>
                  <th>Rep</th>
                  <th>Rate</th>
                </tr>
              </thead>
              <tbody>
                {plan.jobs.slice(0, PREVIEW_LIMIT).map((job) => (
                  <tr>
                    <td>{job.run_id}</td>
                    <td>{job.scenario}</td>
                    <td>{plotsLabel(job.config)}</td>
                    <td>{job.frontend ?? 'Receiver'}</td>
                    <td>{job.backend}</td>
                    <td>{job.mode}</td>
                    <td>{job.repetition}</td>
                    <td>{job.config.hz} Hz</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p class="muted small">
            {plan.jobs.length > PREVIEW_LIMIT
              ? `Showing the first ${PREVIEW_LIMIT} runs in the actual shuffled order. Use --dry-run --json for the full ${plan.run_count.toLocaleString()}-run schedule.`
              : 'All planned runs shown in the actual shuffled order.'}
          </p>
        </>
      ) : (
        !error && <p class="muted">Configure workloads above to preview the schedule.</p>
      )}
    </section>
  );
}
