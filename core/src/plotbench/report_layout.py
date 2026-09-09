"""Offline compact report layout and stable links into detailed evidence."""

import hashlib
import json
from collections import Counter
from datetime import datetime
from html import escape


def report_anchor(kind, *parts):
    """Stable HTML identity, including directory/scope when run names repeat."""
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]
    return f"{kind}-{digest}"


def diagnostic_anchor(entry):
    return report_anchor("diagnostic", entry["kind"], entry.get("label"), entry["reference"])


def _text(value):
    return escape(str(value)) if value is not None and value != "" else "Not recorded"


def _selector(name, label, values):
    options = "".join(
        f'<option value="{escape(value, quote=True)}">{escape(value)}</option>'
        for value in sorted(set(values))
    )
    return (
        f'<label for="{name}">{label}<select id="{name}">'
        f'<option value="">All {label.lower()}s</option>{options}</select></label>'
    )


def acquisition_interval(campaign):
    """Short dates without repeating local and UTC forms; unknown zones stay unknown."""
    moments = []
    for key in ("started_at", "completed_at"):
        value = campaign[key]
        try:
            moment = datetime.fromisoformat(value.split(" (", 1)[0])
        except (AttributeError, ValueError):
            moment = None
        moments.append(moment)
    start, end = moments

    def zone(moment):
        offset = moment.strftime("%z")
        return f"UTC{offset[:3]}:{offset[3:]}" if offset else "timezone not recorded"

    if start is not None and end is not None and start.utcoffset() == end.utcoffset():
        end_format = "%H:%M:%S" if start.date() == end.date() else "%d %b %Y, %H:%M:%S"
        return escape(f"{start:%d %b %Y, %H:%M:%S} – {end.strftime(end_format)} ({zone(start)})")
    labels = [
        f"{moment:%d %b %Y, %H:%M:%S} ({zone(moment)})" if moment else campaign[key]
        for moment, key in zip(moments, ("started_at", "completed_at"), strict=True)
    ]
    return " to ".join(_text(label) for label in labels)


def compact_report_html(summary, charts):
    """Render charts and essential context without embedding per-run audit payloads."""
    campaign = summary["campaign"]
    rows = summary["runs"]
    main_rows = [row for row in rows if not row.get("extension")]
    planned = campaign.get("runs_planned")
    missing = len(campaign["missing_runs"]) if campaign["missing_runs"] is not None else None
    failures = Counter(row["status"] for row in rows if row["status"] != "ok")
    failed = sum(failures.values())
    limited = sum(bool(row.get("source_limited")) for row in rows)
    warnings = []
    if not campaign["manifest_present"]:
        warnings.append(
            "No campaign manifest. Acquisition context and the planned matrix may be unavailable."
        )
    elif (
        campaign["completion_status"] in ("running", "interrupted", "error")
        or missing
        or (planned is not None and len(main_rows) < planned)
    ):
        warnings.append(
            f"Incomplete campaign: {len(main_rows)} of {_text(planned)} planned main runs recorded; "
            f"{_text(missing)} planned runs absent. Recorded status: {_text(campaign['completion_status'])}."
        )
    elif campaign["completion_status"] != "completed":
        warnings.append("Campaign completion status was not recorded.")
    if campaign.get("manifest_error"):
        warnings.append(_text(campaign["manifest_error"]))
    if any(row["measurement_seconds"] < 30 for row in rows):
        warnings.append(
            "Smoke validation: short measurements establish operation, not sustained performance."
        )
    if failed:
        statuses = ", ".join(
            f"{_text(status)}: {count}" for status, count in sorted(failures.items())
        )
        warnings.append(f"{failed} failed or unusable runs remain in the evidence ({statuses}).")
    if limited:
        warnings.append(
            f"{limited} runs have a source-generation shortfall. Inspect source and delivery evidence "
            "before attributing low throughput to a frontend."
        )
    warning_html = "".join(f'<p class="warning">{warning}</p>' for warning in warnings)
    stats = (
        ("Main runs", len(main_rows)),
        ("Extension runs", len(rows) - len(main_rows)),
        ("Valid runs", len(rows) - failed),
        ("Failed / unusable", failed),
        ("Absent main runs", missing),
        ("Source limited", limited),
    )
    stats_html = "".join(
        f"<div><dt>{label}</dt><dd>{_text(count)}</dd></div>" for label, count in stats
    )
    hardware = campaign.get("hardware") or {}
    hardware_label = " · ".join(
        _text(hardware.get(key)) for key in ("cpu_model", "os", "architecture")
    )
    memory = hardware.get("memory_gib")
    if memory is not None:
        hardware_label += f" · {memory:g} GiB RAM"
    diagnostic_items = []
    diagnostics = summary["diagnostics"]
    if diagnostics.get("error"):
        diagnostic_items.append(f'<li class="warning">{_text(diagnostics["error"])}</li>')
    for entry in diagnostics["entries"].values():
        title = entry["kind"] + (f" · {entry['label']}" if entry.get("label") else "")
        status = entry["status"]
        if status == "available":
            if entry["kind"] == "source_probe":
                detail = f"{len(entry['probe']['runs'])} receiver-only runs"
            elif entry["kind"] == "extension":
                detail = (
                    f"{len(entry.get('merged_run_ids', []))} merged, "
                    f"{len(entry.get('excluded_runs', []))} excluded"
                )
            else:
                valid = sum(row["status"] == "ok" for row in entry["runs"])
                detail = (
                    f"{len(entry['runs'])} separate runs; {valid} valid, "
                    f"{len(entry['runs']) - valid} failed or unusable"
                )
        else:
            detail = entry.get("error") or "Unavailable"
        diagnostic_items.append(
            f'<li><a href="report-extended.html#{diagnostic_anchor(entry)}">{escape(title)}</a>'
            f" — {escape(status)}; {escape(detail)}</li>"
        )
    diagnostic_html = (
        "<ul>" + "".join(diagnostic_items) + "</ul>"
        if diagnostic_items
        else "<p>No follow-up diagnostics were recorded or linked.</p>"
    )
    groups = summary["comparisons"]
    selectors = "".join(
        _selector(name, label, [group[key] for group in groups])
        for name, label, key in (
            ("scenario", "Workload", "scenario"),
            ("backend", "Source backend", "backend"),
            ("mode", "Delivery mode", "mode"),
        )
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Plotting benchmark · Compact report</title>
<style>
:root{{font:16px system-ui;color:#e9f0fa;background:#0e1420;color-scheme:dark}}*{{box-sizing:border-box}}body{{max-width:1180px;margin:0 auto;padding:40px 24px}}h1{{font-size:38px;letter-spacing:-1px;margin:10px 0 16px}}h2{{font-size:22px}}p,li{{color:#b3c2d6;line-height:1.6}}a{{color:#65ddc2;text-underline-offset:3px}}a:focus-visible,select:focus-visible{{outline:2px solid #65ddc2;outline-offset:4px}}.tag{{color:#65ddc2;letter-spacing:2px;font-size:12px}}nav{{display:flex;gap:12px 22px;flex-wrap:wrap;margin:18px 0}}.context{{border-top:1px solid #314158;padding-top:14px;overflow-wrap:anywhere;font-size:13px}}.context p{{margin:4px 0}}.stats{{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin:22px 0}}.stats div{{background:#172235;border-radius:8px;padding:14px}}dt{{font-size:12px;color:#b3c2d6}}dd{{margin:6px 0 0;font-size:25px}}.warning{{border-left:3px solid #f5c76e;padding:8px 12px;background:#22304a;font-size:13px}}#controls{{display:flex;gap:16px;flex-wrap:wrap;padding:18px;background:#172235;border-radius:8px}}#controls[hidden],section[hidden]{{display:none}}label{{display:flex;flex-direction:column;gap:7px;font-size:13px;max-width:100%}}select{{background:#101a2b;color:#e9f0fa;border:1px solid #405577;border-radius:5px;padding:9px;max-width:100%;font:inherit}}section.chart{{margin:20px 0;padding:22px;background:#172235;border-radius:10px}}h2 span{{display:block;font-size:13px;color:#65ddc2;margin-top:8px}}.chart p{{font-size:13px}}.chart-scroll{{overflow-x:auto}}svg{{display:block;width:100%;min-width:650px;height:auto}}#selection-status{{font-size:13px}}.notes{{font-size:13px}}footer{{border-top:1px solid #314158;margin-top:30px;padding-top:14px}}@media(max-width:720px){{body{{padding:24px 16px}}h1{{font-size:30px}}.stats{{grid-template-columns:repeat(3,minmax(0,1fr))}}section.chart{{padding:16px}}}}@media print{{#controls{{display:none}}body{{max-width:none;padding:0}}section.chart[hidden]{{display:block}}section.chart{{break-inside:avoid}}svg{{min-width:0}}}}
</style></head><body>
<header><div class="tag">PLOTBENCH / RECORDED MEASUREMENTS</div><h1>Plotting benchmark report</h1>
<p>Compact view · {_text(campaign.get('suite_name'))}</p>
<nav aria-label="Report navigation"><a href="report-extended.html">Extended report</a><a href="report-extended.html#evidence">Run evidence</a><a href="summary.csv">CSV</a><a href="summary.json">Structured summary</a></nav>
<div class="context"><p><strong>Acquired</strong> {acquisition_interval(campaign)}</p>
<p><strong>Campaign</strong> {_text(campaign['completion_status'])} · {len(main_rows)} of {_text(planned)} planned main runs recorded · warmup / measured / cooldown: {_text(campaign.get('warmup_seconds'))} / {_text(campaign.get('measurement_seconds'))} / {_text(campaign.get('cooldown_seconds'))} seconds</p>
<p><strong>Recorded host</strong> {hardware_label}</p><p><strong>Display context</strong> {_text(campaign.get('display_context'))} · <a href="report-extended.html#campaign">Full acquisition metadata</a></p></div></header>
<dl class="stats">{stats_html}</dl>{warning_html}
<p class="notes">Bars show median <strong>submitted updates/s</strong>, not displayed FPS. White ranges span valid repetitions; gold markers show the target. Backend, delivery mode, source/build and display/runtime contexts stay separate. Equal window sizes do not guarantee equal plotting areas. <a href="report-extended.html#methodology">Measurement definitions</a>.</p>
<div id="controls" hidden>{selectors}</div><p id="selection-status" role="status" aria-live="polite">All recorded comparison charts are shown.</p>
<noscript><p>JavaScript is disabled. All charts remain available below; use the extended report for detailed evidence.</p></noscript>
<main id="charts">{charts}</main>
<section class="notes" aria-labelledby="follow-ups"><h2 id="follow-ups">Follow-up diagnostics</h2>{diagnostic_html}<p>Replay, stability, receiver probes and replacement attempts retain their separate evidence. Compatible extensions are identified in the main comparison; original failed attempts remain recorded.</p></section>
<footer class="notes"><p>Report generated {_text(summary['report_generated_at'])}. Acquisition metadata is retained from the recorded campaign. Per-run source/build provenance and separate report-generator provenance are available in the <a href="summary.json">structured summary</a> and <a href="report-extended.html#evidence">extended report</a>.</p></footer>
<script>
(() => {{
  const charts = [...document.querySelectorAll('#charts .chart')];
  const names = ['scenario', 'backend', 'mode'];
  const selectors = names.map(name => document.getElementById(name));
  const status = document.getElementById('selection-status');
  function update() {{
    let visible = 0;
    for (const chart of charts) {{
      chart.hidden = !selectors.every((select, index) => !select.value || chart.dataset[names[index]] === select.value);
      if (!chart.hidden) visible += 1;
    }}
    status.textContent = visible ? `${{visible}} of ${{charts.length}} comparison charts shown.` : 'No comparisons match these selections. Select All to broaden the view.';
  }}
  if (charts.length) {{
    selectors.forEach((select, index) => {{select.value = charts[0].dataset[names[index]]; select.addEventListener('change', update);}});
    document.getElementById('controls').hidden = false;
    update();
  }}
}})();
</script></body></html>"""
