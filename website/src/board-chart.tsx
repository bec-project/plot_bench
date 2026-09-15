import { boardChart } from './chart';
import { format, rateRange } from './presentation';
import type { WinnerBoard } from './winners';

// Same encoding as the offline HTML reports. A table keeps the label, bar and
// value columns aligned across every row and the axis row, and reads as data.
export function BoardChart({ board }: { board: WinnerBoard }) {
  const { target, max, bars } = boardChart(board);
  const pct = (value: number) => `${((value / max) * 100).toFixed(2)}%`;
  const title = board.section
    ? `Median submitted updates per second by frontend in the ${board.section.title} section`
    : 'Median submitted updates per second by frontend';
  return (
    <figure className="board-chart">
      <table className="chart-table" aria-label={title}>
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
              className={bar.winner ? 'chart-row chart-row-winner' : 'chart-row'}
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
                {rateRange(bar.minimum, bar.median)}
                <span className="muted">
                  {' '}
                  {bar.valid}/{bar.attempted} valid
                  {bar.limited > 0 ? ` · ${bar.limited} source-limited` : ''}
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
      <figcaption>
        Bars: median updates/s of each frontend's record, as ranked; a record that merges equally
        ranked groups spans its lowest to highest group median. Whiskers: observed range of the
        valid repetition rates behind the record. Dashed line: the paced target. Source-limited
        counts repetitions where the source, not the frontend, bounded the rate. Not displayed FPS.
      </figcaption>
    </figure>
  );
}
