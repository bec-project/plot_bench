import { boardChart, resourceChart, type ResourceChartData } from './chart';
import { format, rateRange } from './presentation';
import type { WinnerBoard } from './winners';

// Row highlight shared with the profile glyphs: hovering a frontend anywhere in
// the winner card lights up its row in all three tables. Optional, so the chart
// still renders standalone (e.g. in tests) without the hover wiring.
export type RowHover = { hovered?: string | null; onHover?: (frontend: string | null) => void };
export function rowClass(base: string, frontend: string, hover: RowHover): string {
  return hover.onHover && hover.hovered === frontend ? `${base} chart-row-hover` : base;
}
export function rowHoverProps(frontend: string, { onHover }: RowHover) {
  return onHover
    ? { onMouseEnter: () => onHover(frontend), onMouseLeave: () => onHover(null) }
    : {};
}

// Same encoding as the offline HTML reports. A table keeps the label, bar and
// value columns aligned across every row and the axis row, and reads as data.
export function BoardChart({ board, hovered = null, onHover }: { board: WinnerBoard } & RowHover) {
  const hover: RowHover = { hovered, onHover };
  // While a frontend is hovered, drop the winner row's standing emphasis so only
  // the frontend being inspected stands out.
  const hovering = onHover != null && hovered != null;
  const { target, max, bars } = boardChart(board);
  const pct = (value: number) => `${((value / max) * 100).toFixed(2)}%`;
  const where = board.section ? ` in the ${board.section.title} section` : '';
  // CPU is charted per logical core, so 100% marks one saturated core.
  const memory = resourceChart(board, 'rss_peak_mib', (r) => r.memoryMib);
  const cpu = resourceChart(board, 'cpu_mean_percent', (r) => r.cpuPercent, 100);
  return (
    <figure className={hovering ? 'board-chart board-chart--hovering' : 'board-chart'}>
      <table
        className="chart-table chart-throughput"
        aria-label={`Median submitted updates per second by frontend${where}`}
      >
        <caption className="chart-caption">
          Submitted updates/s <span className="muted">· higher is better</span>
        </caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">Rank and frontend</th>
            <th scope="col">Median updates/s as a bar with the observed repetition range</th>
            <th scope="col">Median updates/s and valid repetitions</th>
          </tr>
        </thead>
        <tbody>
          {bars.map((bar) => (
            <tr
              key={bar.frontend}
              className={rowClass(
                bar.winner ? 'chart-row chart-row-winner' : 'chart-row',
                bar.frontend,
                hover,
              )}
              {...rowHoverProps(bar.frontend, hover)}
            >
              <th scope="row" className="chart-label">
                <span className="muted">#{bar.rank}</span> {bar.frontend}
              </th>
              <td className="chart-track-cell">
                <span className="chart-track" aria-hidden="true">
                  <span className="chart-bar" style={{ width: pct(bar.minimum) }} />
                  {bar.median > bar.minimum && (
                    <span
                      className="chart-bar chart-bar-range"
                      style={{ left: pct(bar.minimum), width: pct(bar.median - bar.minimum) }}
                    />
                  )}
                  {bar.low !== null && bar.high !== null && bar.high > bar.low && (
                    <span
                      className="chart-whisker"
                      style={{ left: pct(bar.low), width: pct(bar.high - bar.low) }}
                    />
                  )}
                  <span className="chart-target" style={{ left: pct(target) }} />
                </span>
              </td>
              <td className="chart-value">
                <span className="chart-rate">{rateRange(bar.minimum, bar.median)}</span>
                <span className="muted">
                  {' '}
                  {bar.valid}/{bar.attempted} valid
                  {bar.sourceLimited > 0 ? ` · ${bar.sourceLimited} source-limited` : ''}
                  {bar.frontendLimited > 0 ? ` · ${bar.frontendLimited} frontend-limited` : ''}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot aria-hidden="true">
          <tr className="chart-axis">
            <td />
            <td className="chart-track-cell">
              <span className="chart-axis-line">
                <span className="chart-axis-origin">0</span>
                <span className="chart-axis-target" style={{ left: pct(target) }}>
                  target {format(target)} Hz
                </span>
              </span>
            </td>
            <td />
          </tr>
        </tfoot>
      </table>
      <ResourceChart
        title="Peak memory · RSS"
        hint="lower is better"
        chart={memory}
        section={where}
        unit=" MiB"
        emptyLabel="No memory coverage in these records."
        hover={hover}
      />
      <ResourceChart
        title="Mean CPU"
        hint="lower is better"
        chart={cpu}
        section={where}
        unit="%"
        referenceLabel="1 core"
        emptyLabel="No CPU coverage in these records."
        hover={hover}
      />
      <figcaption>
        Bars: the ranked value of each frontend's record — median submitted updates/s, then median
        peak resident memory and median mean CPU, in rank order. Whiskers: the observed range across
        the record's valid repetitions. Throughput's dashed line is the paced target; CPU's is one
        logical core (100%). Triangle area balances throughput, memory and CPU within each rate
        band, with equal campaign weights. For tied configurations, resource bars use the profile's
        configuration, throughput spans the tied medians, and whiskers span all tied repetitions.
        Not displayed FPS.
      </figcaption>
    </figure>
  );
}

// One resource metric as a bar-per-frontend table, in the same rank order and
// visual encoding as the throughput chart. Rendered only when data exists.
function ResourceChart({
  title,
  hint,
  chart,
  section,
  unit,
  referenceLabel,
  emptyLabel,
  hover,
}: {
  title: string;
  hint: string;
  chart: ResourceChartData;
  section: string;
  unit: string;
  referenceLabel?: string;
  emptyLabel: string;
  hover: RowHover;
}) {
  const pct = (value: number) => `${((value / chart.max) * 100).toFixed(2)}%`;
  const valueText = (value: number) =>
    unit === '%' ? `${format(value)}%` : `${format(value)}${unit}`;
  return (
    <table
      className="chart-table chart-resource"
      aria-label={`Median ${title} by frontend${section}`}
    >
      <caption className="chart-caption">
        {title} <span className="muted">· {hint}</span>
      </caption>
      <thead className="sr-only">
        <tr>
          <th scope="col">Rank and frontend</th>
          <th scope="col">Median value as a bar with the observed repetition range</th>
          <th scope="col">Median value</th>
        </tr>
      </thead>
      <tbody>
        {!chart.hasData ? (
          <tr className="chart-row">
            <td colSpan={3} className="chart-empty muted">
              {emptyLabel}
            </td>
          </tr>
        ) : (
          chart.bars.map((bar) => (
            <tr
              key={bar.frontend}
              className={rowClass(
                bar.winner ? 'chart-row chart-row-winner' : 'chart-row',
                bar.frontend,
                hover,
              )}
              {...rowHoverProps(bar.frontend, hover)}
            >
              <th scope="row" className="chart-label">
                <span className="muted">#{bar.rank}</span> {bar.frontend}
              </th>
              <td className="chart-track-cell">
                <span className="chart-track" aria-hidden="true">
                  {bar.value !== null && (
                    <span
                      className="chart-bar chart-bar-resource"
                      style={{ width: pct(bar.value) }}
                    />
                  )}
                  {bar.low !== null && bar.high !== null && bar.high > bar.low && (
                    <span
                      className="chart-whisker"
                      style={{ left: pct(bar.low), width: pct(bar.high - bar.low) }}
                    />
                  )}
                  {chart.reference !== null && (
                    <span className="chart-reference" style={{ left: pct(chart.reference) }} />
                  )}
                </span>
              </td>
              <td className="chart-value">
                {bar.value === null ? (
                  <span className="muted">incomplete</span>
                ) : (
                  valueText(bar.value)
                )}
              </td>
            </tr>
          ))
        )}
      </tbody>
      {chart.hasData && (
        <tfoot aria-hidden="true">
          <tr className="chart-axis">
            <td />
            <td className="chart-track-cell">
              <span className="chart-axis-line">
                <span className="chart-axis-origin">0</span>
                {chart.reference !== null && referenceLabel ? (
                  <span className="chart-axis-target" style={{ left: pct(chart.reference) }}>
                    {referenceLabel}
                  </span>
                ) : (
                  <span className="chart-axis-max">{valueText(chart.max)}</span>
                )}
              </span>
            </td>
            <td />
          </tr>
        </tfoot>
      )}
    </table>
  );
}
