"""Portable descriptive charts for the receiver-only backend probe."""

import hashlib
import json
import math
from collections import defaultdict
from html import escape
from textwrap import shorten

COLORS = {"python": "#729de8", "rust": "#ebbd6a"}
BACKGROUND = "#11202a"
TEXT = "#dce8ee"
MUTED = "#9fb6c4"


def _number(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        return None
    return value


def _statistics(values):
    if not values:
        return None
    values = sorted(values)
    low, high = values[(len(values) - 1) // 2], values[len(values) // 2]
    return dict(median=low + (high - low) / 2, min=values[0], max=values[-1])


def _comparisons(rows):
    groups = defaultdict(list)
    settings = {}
    for index, row in enumerate(rows):
        config = row.get("config")
        config = (
            {key: value for key, value in config.items() if key != "generation"}
            if isinstance(config, dict) and config
            else None
        ) or None
        try:
            config_key = json.dumps(config, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError):
            config = None
        if config is None:
            config_key = f"unknown-config-{index}"
        target = _number(row.get("target_hz"), positive=True)
        duration = _number(row.get("measurement_seconds"), positive=True)
        scenario = str(row.get("scenario", "Unnamed workload"))
        backend = str(row.get("backend", "unknown"))
        provenance = row.get("provenance") or {}
        context = dict(
            source_identity=provenance.get("source_sha256") or provenance.get("git"),
            artifact_files={
                key: value.get("files") for key, value in provenance.get("artifacts", {}).items()
            },
        )
        context_id = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()[:12]
        key = (scenario, config_key, target, duration, backend, context_id)
        groups[key].append(row)
        settings[key] = dict(
            scenario=scenario,
            backend=backend,
            context_id=context_id,
            config=config,
            config_known=config is not None,
            target_hz=target,
            measurement_seconds=duration,
        )
    results = []
    for key, runs in groups.items():
        group = settings[key]
        valid = [
            row
            for row in runs
            if row.get("status") == "ok"
            and group["target_hz"] is not None
            and group["measurement_seconds"] is not None
            and _number(row.get("received_hz")) is not None
            and _number(row.get("source_hz")) is not None
        ]
        group.update(
            attempted=len(runs),
            valid=len(valid),
            invalid=len(runs) - len(valid),
            target_met=sum(
                row["source_hz"] >= group["target_hz"] * 0.98
                and row["received_hz"] >= group["target_hz"] * 0.98
                for row in valid
            ),
            received_hz=_statistics([row["received_hz"] for row in valid]),
            source_hz=_statistics([row["source_hz"] for row in valid]),
        )
        results.append(group)

    def order(group):
        config = group["config"] or {}
        return (
            {"waveform": 0, "image": 1}.get(config.get("view"), 2),
            _number(config.get("points")) or 0,
            _plot_count(config, "waveform_plots"),
            _plot_count(config, "curves"),
            {"scalar": 0, "rgb": 1}.get(config.get("image_mode"), 2),
            _plot_count(config, "image_plots"),
            group["scenario"],
            json.dumps(config, sort_keys=True),
            group["target_hz"] or 0,
            group["measurement_seconds"] or 0,
            {"python": 0, "rust": 1}.get(group["backend"], 2),
            group["backend"],
        )

    return sorted(results, key=order)


def _format(value):
    return f"{value:,.6g}"


def _ticks(maximum):
    desired = maximum / 4
    if desired == 0:
        return [0, maximum]
    magnitude = 10 ** math.floor(math.log10(desired))
    if magnitude == 0:
        return [0, maximum]
    spacing = next(value for value in (1, 2, 3, 5, 10) if value >= desired / magnitude)
    interval = spacing * magnitude
    return [index * interval for index in range(int(maximum / interval) + 1)]


def _plot_count(config, field):
    value = config.get(field, 1)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 1


def _label(group):
    """Compact workload label; multi-plot counts prefix it ("2 × 3-curve 10k-point waveforms").

    Combined workloads join the two kinds in a shorter form: "2 × 3-curve 10k wf + 3 × 256² img".
    """
    config = group["config"] or {}
    view = config.get("view")
    waveform = _waveform_label(config) if view in ("waveform", "both") else None
    image = _image_label(config) if view in ("image", "both") else None
    if view == "waveform" and waveform is not None:
        return waveform
    if view == "image" and image is not None:
        return image
    if view == "both" and waveform is not None and image is not None:
        return f"{waveform} + {image}"
    return group["scenario"]


def _waveform_label(config):
    if _number(config.get("points")) is None:
        return None
    points = config["points"]
    count = (
        f"{points / 1e6:g}M"
        if points >= 1e6
        else f"{points / 1e3:g}k" if points >= 1e3 else f"{points:g}"
    )
    plots, curves = _plot_count(config, "waveform_plots"), _plot_count(config, "curves")
    prefix = (f"{plots} × " if plots > 1 else "") + (f"{curves}-curve " if curves > 1 else "")
    if config.get("view") == "both":
        return f"{prefix}{count} wf"
    return f"{prefix}{count}-point waveform{'s' if plots > 1 else ''}"


def _image_label(config):
    width, height = config.get("width"), config.get("height")
    if _number(width) is None or _number(height) is None:
        return None
    dimensions = f"{width:g}²" if width == height else f"{width:g} × {height:g}"
    mode = "RGB" if config.get("image_mode") == "rgb" else str(config.get("image_mode", ""))
    plots = _plot_count(config, "image_plots")
    prefix = f"{plots} × " if plots > 1 else ""
    if config.get("view") == "both":
        return f"{prefix}{dimensions}{'' if mode == 'scalar' else ' ' + mode} img"
    return f"{prefix}{dimensions} {mode} image{'s' if plots > 1 else ''}"


def _text(x, y, text, *, size=14, fill=TEXT, anchor="start", weight="normal"):
    return f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}">{escape(str(text))}</text>'


def _chart(groups, *, delivery):
    width, left, right, top, step = 1100, 300, 770, 160, 60
    bottom = top + step * len(groups)
    height = bottom + 100
    title = (
        "Source generation and receiver delivery" if delivery else "Received throughput by backend"
    )
    chart_id = "probe-delivery" if delivery else "probe-received"
    maximum = max(
        max(group["target_hz"], group["source_hz"]["max"], group["received_hz"]["max"])
        for group in groups
    )
    # A ratio scale avoids overflowing when finite input rates are unusually large.
    axis_max = maximum * 1.05 if maximum < 1e307 else maximum

    def x(value):
        return left + value / axis_max * (right - left)

    description = (
        (
            "Median source generation (open circles) and received rate (filled squares). "
            if delivery
            else "Bars show median received rate; capped whiskers show the observed repetition minimum and maximum. "
        )
        + "Each backend is separate. Vertical dashed markers show each row's requested rate. Zero-based axis in Hz. Only complete successful runs with finite nonnegative rates are plotted. Target-met counts require both rates to reach 98% of the requested rate in that run. These measurements use a common receiver without plotting and are not displayed FPS."
    )
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{chart_id}-title {chart_id}-desc" font-family="system-ui, -apple-system, sans-serif">',
        f'<title id="{chart_id}-title">{title}</title>',
        f'<desc id="{chart_id}-desc">{escape(description)}</desc>',
        f'<rect width="{width}" height="{height}" fill="{BACKGROUND}"/>',
        f'<defs><clipPath id="{chart_id}-labels"><rect x="26" y="{top - 6}" width="254" height="{bottom - top}"/></clipPath></defs>',
        _text(26, 37, title, size=25, weight="600"),
        _text(
            26, 63, "Hz · median of valid repetitions · common receiver · no plotting", fill=MUTED
        ),
    ]
    if delivery:
        elements.extend(
            [
                '<circle cx="34" cy="93" r="5" fill="none" stroke="#dce8ee" stroke-width="2"/>',
                _text(47, 98, "Source generation", size=13),
                '<rect x="209" y="88" width="10" height="10" fill="#dce8ee"/>',
                _text(228, 98, "Received + decoded", size=13),
            ]
        )
    else:
        elements.extend(
            [
                '<rect x="27" y="87" width="26" height="12" fill="#9fb6c4"/>',
                _text(63, 98, "Median", size=13),
                '<path d="M146 93 H180 M146 88 V98 M180 88 V98" stroke="#dce8ee" stroke-width="2"/>',
                _text(192, 98, "Observed min–max", size=13),
            ]
        )
    elements.extend(
        [
            '<path d="M431 84 V102" stroke="#dce8ee" stroke-dasharray="4 3" stroke-width="2"/>',
            _text(441, 98, "Requested Hz", size=13),
            _text(26, 139, "WORKLOAD / BACKEND", size=11, fill=MUTED, weight="600"),
            _text(300, 139, "RATE (Hz)", size=11, fill=MUTED, weight="600"),
        ]
    )
    if delivery:
        elements.extend(
            [
                _text(875, 139, "SOURCE Hz", size=11, fill=MUTED, anchor="end"),
                _text(977, 139, "RECEIVED Hz", size=11, fill=MUTED, anchor="end"),
            ]
        )
    else:
        elements.append(_text(977, 139, "MEDIAN [MIN–MAX] Hz", size=11, fill=MUTED, anchor="end"))
    elements.append(_text(1073, 139, "MET / VALID", size=11, fill=MUTED, anchor="end"))
    for value in _ticks(maximum):
        px = x(value)
        elements.append(f'<path d="M{px:.2f} {top - 6} V{bottom}" stroke="#273d4b"/>')
        elements.append(
            _text(f"{px:.2f}", bottom + 23, _format(value), size=12, fill=MUTED, anchor="middle")
        )

    variants = defaultdict(dict)
    signatures = []
    for index, group in enumerate(groups):
        signature = json.dumps(
            [group["config"], group["target_hz"], group["measurement_seconds"]], sort_keys=True
        )
        if not group["config_known"]:
            signature += f"-attempt-{index}"
        variants[group["scenario"]].setdefault(signature, len(variants[group["scenario"]]) + 1)
        signatures.append(signature)
    for index, group in enumerate(groups):
        y = top + step * index + 23
        color = COLORS.get(group["backend"], "#b9c9d6")
        source, received = group["source_hz"], group["received_hz"]
        signature = signatures[index]
        label = _label(group)
        if len(variants[group["scenario"]]) > 1:
            label = shorten(label, width=23, placeholder="…")
            label += f" · case {variants[group['scenario']][signature]}"
        details = f"{group['scenario']}\n{json.dumps(group, sort_keys=True, ensure_ascii=False)}"
        elements.extend(
            [
                f"<g><title>{escape(details)}</title>",
                f'<path d="M26 {y + 30} H1074" stroke="#273d4b"/>',
                f'<g clip-path="url(#{chart_id}-labels)">',
                _text(26, y - 2, shorten(label, width=31, placeholder="…"), size=14, weight="600"),
                _text(
                    26,
                    y + 18,
                    shorten(
                        f"{group['backend'].title()} · {_format(group['target_hz'])} Hz · {_format(group['measurement_seconds'])} s",
                        width=37,
                        placeholder="…",
                    ),
                    size=12,
                    fill=color,
                ),
                "</g>",
            ]
        )
        target = x(group["target_hz"])
        elements.append(
            f'<path d="M{target:.2f} {y - 17} V{y + 17}" stroke="#dce8ee" stroke-width="1.5" stroke-dasharray="4 3"/>'
        )
        if delivery:
            sx, rx = x(source["median"]), x(received["median"])
            elements.extend(
                [
                    f'<path d="M{sx:.2f} {y} H{rx:.2f}" stroke="{color}" stroke-width="2"/>',
                    f'<circle cx="{sx:.2f}" cy="{y}" r="7" fill="{BACKGROUND}" stroke="{color}" stroke-width="2"/>',
                    f'<rect x="{rx - 4:.2f}" y="{y - 4}" width="8" height="8" fill="{color}"/>',
                    _text(875, y + 5, _format(source["median"]), anchor="end"),
                    _text(977, y + 5, _format(received["median"]), anchor="end"),
                ]
            )
        else:
            low, high = x(received["min"]), x(received["max"])
            elements.extend(
                [
                    f'<rect x="{left}" y="{y - 11}" width="{x(received["median"]) - left:.2f}" height="22" rx="2" fill="{color}"/>',
                    f'<path d="M{low:.2f} {y} H{high:.2f} M{low:.2f} {y - 6} V{y + 6} M{high:.2f} {y - 6} V{y + 6}" fill="none" stroke="#f3f6fa" stroke-width="2"/>',
                    _text(
                        977, y - 2, _format(received["median"]), size=15, weight="600", anchor="end"
                    ),
                    _text(
                        977,
                        y + 16,
                        f"[{_format(received['min'])}–{_format(received['max'])}]",
                        size=11,
                        fill=MUTED,
                        anchor="end",
                    ),
                ]
            )
        elements.extend(
            [
                _text(1073, y + 2, f"{group['target_met']} / {group['valid']}", anchor="end"),
                _text(
                    1073,
                    y + 19,
                    f"valid {group['valid']}/{group['attempted']}",
                    size=10,
                    fill=MUTED,
                    anchor="end",
                ),
                "</g>",
            ]
        )
    elements.extend(
        [
            _text(
                26,
                bottom + 57,
                "Met: both source and received rates ≥98% of the requested rate in that repetition.",
                size=12,
                fill=MUTED,
            ),
            _text(
                26,
                bottom + 78,
                (
                    "Points show separate medians, not per-frame latency. Full configuration and values are in row tooltips and summary JSON."
                    if delivery
                    else "Range is observed variability, not a confidence interval. Full configuration and values are in row tooltips and summary JSON."
                ),
                size=12,
                fill=MUTED,
            ),
            "</svg>",
        ]
    )
    return "".join(elements)


def build_probe_charts(rows):
    """Return JSON-safe comparisons and two standalone SVGs, or None without valid data.

    Comparisons retain every attempt, grouped by scenario, backend, target, duration
    and full configuration except generation. Unknown configurations are isolated
    per attempt. Each rate statistic is {median, min, max}, or None without valid
    paired observations. ``target_met`` counts passing valid runs, not medians.
    """
    comparisons = _comparisons(rows)
    valid = [group for group in comparisons if group["valid"]]
    return dict(
        comparisons=comparisons,
        received_svg=_chart(valid, delivery=False) if valid else None,
        delivery_svg=_chart(valid, delivery=True) if valid else None,
    )
