"""Per-second submission and resident-memory time series for stability diagnostics."""

import math
from html import escape


def submission_bins(samples, start_ms, seconds, bin_seconds=1.0):
    """Count submitted samples per fixed bin after warmup; empty bins stay at zero."""
    count = max(1, math.ceil(seconds / bin_seconds))
    bins = [0] * count
    for sample in samples:
        index = int((sample["client_time_ms"] - start_ms) / (bin_seconds * 1000))
        if 0 <= index < count:
            bins[index] += 1
    return bins


def rss_series(resources, start_ms, end_ms):
    """(elapsed seconds, RSS MiB) for observations inside the window; none means none."""
    points = []
    for sample in resources:
        time_ms, rss = sample.get("time_ms"), sample.get("rss_bytes")
        if type(time_ms) not in (int, float) or type(rss) not in (int, float):
            continue
        if start_ms <= time_ms < end_ms:
            points.append(((time_ms - start_ms) / 1000, rss / 1024**2))
    return points


def run_series(samples, resources, *, start_ms, measurement_seconds, warmup_seconds, target_hz):
    end_ms = start_ms + measurement_seconds * 1000
    measured = [s for s in samples if start_ms <= s["client_time_ms"] < end_ms]
    bins = submission_bins(measured, start_ms, measurement_seconds)
    rss = rss_series(resources, start_ms, end_ms)
    return dict(
        bin_seconds=1,
        submissions_per_bin=bins,
        zero_bins=sum(1 for value in bins if value == 0),
        rss_mib=[[round(t, 3), round(mib, 3)] for t, mib in rss],
        resource_observations=len(rss),
        measurement_seconds=measurement_seconds,
        warmup_seconds=warmup_seconds,
        target_hz=target_hz,
        units="submissions per one-second bin after warmup; RSS in MiB summed over the frontend process tree",
    )


def _ticks(maximum, count=5):
    if maximum <= 0:
        return [0]
    raw = maximum / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(s * magnitude for s in (1, 2, 2.5, 5, 10) if s * magnitude >= raw)
    return [i * step for i in range(int(maximum // step) + 2) if i * step <= maximum * 1.0001]


def series_svg(series, *, title):
    """Two aligned panels: submissions per second with the target line, then RSS over time."""
    width, left, right, top, panel, gap, bottom = 980, 70, 30, 30, 150, 60, 40
    height = top + panel * 2 + gap + bottom
    plot_w = width - left - right
    seconds = max(1, series["measurement_seconds"])
    bins = series["submissions_per_bin"]
    target = series.get("target_hz") or 0
    y_max = max([target * 1.15, max(bins, default=0) * 1.1, 1])
    rss = series["rss_mib"]
    rss_max = max([point[1] for point in rss], default=0) * 1.1 or 1

    def x(seconds_elapsed):
        return left + plot_w * seconds_elapsed / seconds

    def y1(value):
        return top + panel - panel * value / y_max

    def y2(value):
        return top + panel + gap + panel - panel * value / rss_max

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
        f'<text x="{left}" y="{top - 12}" fill="#d1deed" font-size="14">Submitted updates per one-second bin '
        f"(target {target:g} Hz); {series['zero_bins']} bins with zero submissions</text>",
    ]
    for tick in _ticks(y_max):
        parts.append(
            f'<path d="M{left} {y1(tick):.1f} H{width - right}" stroke="#314158" stroke-width="1"/>'
            f'<text x="{left - 8}" y="{y1(tick) + 4:.1f}" fill="#9eb2ce" font-size="11" text-anchor="end">{tick:g}</text>'
        )
    bar_w = plot_w / len(bins)
    for index, value in enumerate(bins):
        if value > 0:
            parts.append(
                f'<rect x="{x(index):.2f}" y="{y1(value):.2f}" width="{max(bar_w - 0.3, 0.5):.2f}" '
                f'height="{y1(0) - y1(value):.2f}" fill="#63d7b9"/>'
            )
    if target:
        parts.append(
            f'<path d="M{left} {y1(target):.1f} H{width - right}" stroke="#f5c76e" stroke-width="2" stroke-dasharray="6 4"/>'
        )
    parts.append(
        f'<path d="M{left} {y1(0):.1f} H{width - right}" stroke="#9eb2ce" stroke-width="1"/>'
    )
    parts.append(
        f'<text x="{left}" y="{top + panel + gap - 12}" fill="#d1deed" font-size="14">Resident memory (MiB, frontend process tree); '
        f"{series['resource_observations']} observations inside the measured window</text>"
    )
    for tick in _ticks(rss_max):
        parts.append(
            f'<path d="M{left} {y2(tick):.1f} H{width - right}" stroke="#314158" stroke-width="1"/>'
            f'<text x="{left - 8}" y="{y2(tick) + 4:.1f}" fill="#9eb2ce" font-size="11" text-anchor="end">{tick:g}</text>'
        )
    if rss:
        points = " ".join(f"{x(t):.2f},{y2(mib):.2f}" for t, mib in rss)
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="#7aa6ff" stroke-width="1.5"/>'
        )
    else:
        parts.append(
            f'<text x="{left + 12}" y="{top + panel + gap + panel / 2:.1f}" fill="#f5c76e" font-size="13">No resource observations were recorded inside the measured window.</text>'
        )
    parts.append(
        f'<path d="M{left} {y2(0):.1f} H{width - right}" stroke="#9eb2ce" stroke-width="1"/>'
    )
    for tick in _ticks(seconds, 6):
        parts.append(
            f'<text x="{x(tick):.1f}" y="{height - bottom + 18}" fill="#9eb2ce" font-size="11" text-anchor="middle">{tick:g} s</text>'
        )
    parts.append(
        f'<text x="{width - right}" y="{height - 6}" fill="#9eb2ce" font-size="11" text-anchor="end">Elapsed seconds inside the measured window '
        f"(0 s = end of the {series['warmup_seconds']:g} s warmup)</text>"
    )
    parts.append("</svg>")
    return "".join(parts)
