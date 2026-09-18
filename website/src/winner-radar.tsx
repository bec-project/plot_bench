import { profileData } from './winner-profile';
import { format } from './presentation';
import type { WinnerBoard } from './winners';

// Per-frontend "signature" glyph for the winner card: a three-axis radar
// (throughput / RAM / CPU) using the ranking's normalization within each rate
// band. It shows one frontend at a time — the winner by default, or
// whichever frontend is hovered anywhere in the card — over a faint best/worst
// envelope for scale. Output-and-input: hovering a name in its legend drives
// the shared highlight, and the shared highlight drives the shape.
//
// Self-contained: delete this file, its import and its <ProfileRadar/> line to
// drop the radar without touching the bar charts.

const R = 64;
const CX = 110;
const CY = 92;
const RINGS = [0.25, 0.5, 0.75, 1] as const;

type AxisSpec = {
  label: string;
  angle: number;
  goodness: (frontend: ReturnType<typeof profileData>['points'][number]) => number;
  value: (frontend: ReturnType<typeof profileData>['points'][number]) => string;
  worst: number;
  anchor: 'start' | 'middle' | 'end';
};

const polar = (g: number, angle: number): [number, number] => {
  const a = (angle * Math.PI) / 180;
  return [CX + R * g * Math.cos(a), CY + R * g * Math.sin(a)];
};

export function ProfileRadar({
  board,
  hovered,
  onHover,
}: {
  board: WinnerBoard;
  hovered: string | null;
  onHover: (frontend: string | null) => void;
}) {
  const data = profileData(board);
  if (!data.points.length) return null;
  const active =
    data.points.find((p) => p.frontend === hovered) ??
    data.points.find((p) => p.winner) ??
    data.points[0];
  const worst = data.worstGoodness[active.rateBand];

  const axes: AxisSpec[] = [
    {
      label: 'Throughput',
      angle: -90,
      goodness: (p) => p.gThroughput,
      value: (p) => `${format(p.throughput)}/s`,
      worst: worst.throughput,
      anchor: 'middle',
    },
    {
      label: 'RAM',
      angle: 30,
      goodness: (p) => p.gRss,
      value: (p) => `${format(p.rss)} MiB`,
      worst: worst.rss,
      anchor: 'start',
    },
    {
      label: 'CPU',
      angle: 150,
      goodness: (p) => p.gCpu,
      value: (p) => `${format(p.cpu)}%`,
      worst: worst.cpu,
      anchor: 'end',
    },
  ];

  const poly = (values: number[]) =>
    axes.map((ax, i) => polar(values[i], ax.angle).join(',')).join(' ');
  const activePoly = poly(axes.map((ax) => ax.goodness(active)));
  const worstPoly = poly(axes.map((ax) => ax.worst));
  const tone = active.winner ? 'var(--accent)' : '#6f9ff5';

  return (
    <figure className="profile-card" aria-label="Resource profile radar">
      <figcaption className="profile-title">
        Profile <span className="muted">· higher is better on every axis</span>
      </figcaption>
      <div className="profile-body">
        <svg viewBox="16 2 188 140" role="img" aria-label={radarSummary(active, axes)}>
          <g aria-hidden="true">
            {RINGS.map((g) => (
              <polygon key={g} className="profile-grid" points={poly([g, g, g])} />
            ))}
            {axes.map((ax) => {
              const [x, y] = polar(1, ax.angle);
              return <line key={ax.label} className="profile-grid" x1={CX} y1={CY} x2={x} y2={y} />;
            })}
            <polygon className="profile-worst" points={worstPoly} />
            <polygon
              className="profile-active"
              points={activePoly}
              style={{ fill: tone, stroke: tone }}
            />
            {axes.map((ax) => {
              const [x, y] = polar(ax.goodness(active), ax.angle);
              return <circle key={ax.label} r={2.6} cx={x} cy={y} style={{ fill: tone }} />;
            })}
            {axes.map((ax) => {
              const [x, y] = polar(1.18, ax.angle);
              return (
                <text
                  key={ax.label}
                  className="profile-axis-name"
                  x={x}
                  y={ax.angle === -90 ? y - 1 : y + 4}
                  textAnchor={ax.anchor}
                >
                  {ax.label}
                </text>
              );
            })}
          </g>
        </svg>
        <div className="profile-readout">
          <p className="profile-active-name">
            <span className="profile-swatch" style={{ background: tone }} aria-hidden="true" />
            <strong>{active.frontend}</strong>
            <span className="muted"> · #{active.rank}</span>
            <span className="muted"> · band {active.rateBand + 1}</span>
          </p>
          <p className="profile-area">Triangle area: {(active.area * 100).toFixed(2)}%</p>
          <p className="profile-values muted">
            {axes.map((ax, i) => (
              <span key={ax.label}>
                {i > 0 && ' · '}
                {ax.label} {ax.value(active)}
              </span>
            ))}
          </p>
          <ul className="profile-legend" aria-label="Highlight a frontend">
            {data.points.map((p) => (
              <li key={p.frontend}>
                <button
                  type="button"
                  className={p.frontend === active.frontend ? 'is-active' : undefined}
                  onMouseEnter={() => onHover(p.frontend)}
                  onMouseLeave={() => onHover(null)}
                  onFocus={() => onHover(p.frontend)}
                  onBlur={() => onHover(null)}
                >
                  {p.frontend}
                </button>
              </li>
            ))}
          </ul>
          <p className="profile-note muted">
            Area ranks configurations within the same throughput band; earlier bands rank first.
            Throughput is scaled to the {format(data.target)} Hz target. RAM and CPU use the lowest
            values among all eligible configurations in this band. The faint shape marks the worst
            shown value on each axis in this band. Filters and new results can change these scales.
          </p>
        </div>
      </div>
    </figure>
  );
}

function radarSummary(
  active: ReturnType<typeof profileData>['points'][number],
  axes: AxisSpec[],
): string {
  const parts = axes.map((ax) => `${ax.label} ${ax.value(active)}`).join(', ');
  return `${active.frontend}, rank ${active.rank}, band ${active.rateBand + 1}, triangle area ${(active.area * 100).toFixed(2)}%: ${parts}.`;
}
