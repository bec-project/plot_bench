import { boardChart } from './chart';
import { format, rateRange } from './presentation';
import type { WinnerBoard } from './winners';

// Same encoding as the offline HTML reports, drawn with HTML rows so text keeps
// its CSS size at every width: one bar per frontend record (its ranked median),
// a whisker for the observed repetition range and a dashed line at the target.
export function BoardChart({ board }: { board: WinnerBoard }) {
  const { target, max, bars } = boardChart(board);
  const pct = (value: number) => `${((value / max) * 100).toFixed(2)}%`;
  const title = board.section
    ? `Median submitted updates per second by frontend in the ${board.section.title} section`
    : 'Median submitted updates per second by frontend';
  return (
    <figure className="board-chart">
      <div className="chart-rows" role="list" aria-label={title}>
        {bars.map((bar) => (
          <div
            key={bar.frontend}
            role="listitem"
            className={bar.winner ? 'chart-row chart-row-winner' : 'chart-row'}
          >
            <span className="chart-label">
              <span className="muted">#{bar.rank}</span> {bar.frontend}
            </span>
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
            <span className="chart-value">
              {rateRange(bar.minimum, bar.median)}
              <span className="muted">
                {' '}
                {bar.valid}/{bar.attempted} valid
                {bar.limited > 0 ? ` · ${bar.limited} source-limited` : ''}
              </span>
            </span>
          </div>
        ))}
      </div>
      <div className="chart-axis" aria-hidden="true">
        <span className="chart-axis-origin">0</span>
        <span className="chart-axis-target" style={{ left: pct(target) }}>
          target {format(target)} Hz
        </span>
      </div>
      <figcaption>
        Bars: median updates/s of each frontend's record, as ranked; a record that merges equally
        ranked groups spans its lowest to highest group median. Whiskers: observed range of the
        valid repetition rates behind the record. Dashed line: the paced target. Source-limited
        counts repetitions where the source, not the frontend, bounded the rate. Not displayed FPS.
      </figcaption>
    </figure>
  );
}
