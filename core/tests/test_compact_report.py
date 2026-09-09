"""Compact and detailed HTML share one analysis and remain usable offline."""

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from itertools import product

import pytest
from test_campaign_report import campaign, job, write_run

from plotbench import report
from plotbench.campaign import finalize_campaign_manifest, write_campaign_manifest
from plotbench.report_layout import acquisition_interval


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    @property
    def ids(self):
        return [attrs["id"] for _, attrs in self.elements if "id" in attrs]

    @property
    def charts(self):
        return [
            attrs
            for tag, attrs in self.elements
            if tag == "section" and attrs.get("class") == "chart"
        ]


@pytest.mark.parametrize(
    "start,end,expected",
    [
        (
            "2026-09-09T13:20:00+02:00 (2026-09-09T11:20:00+00:00)",
            "2026-09-09T13:21:00+02:00 (2026-09-09T11:21:00+00:00)",
            "09 Sep 2026, 13:20:00 – 13:21:00 (UTC+02:00)",
        ),
        (
            "2026-09-09T13:20:00 (timezone not recorded)",
            "2026-09-10T13:21:00 (timezone not recorded)",
            "09 Sep 2026, 13:20:00 – 10 Sep 2026, 13:21:00 (timezone not recorded)",
        ),
        ("Not recorded", "Not recorded", "Not recorded to Not recorded"),
    ],
)
def test_compact_acquisition_dates_use_one_zone_without_inventing_legacy_timezones(
    start, end, expected
):
    assert acquisition_interval({"started_at": start, "completed_at": end}) == expected


def fixture_suite(path, *, workloads=2, frontends=2, repetitions=1, backends=("python", "rust")):
    """Synthetic samples for report QA; never represent acquired performance."""
    path.mkdir(parents=True, exist_ok=True)
    jobs = []
    for index, (workload, frontend, repetition, backend, mode) in enumerate(
        product(
            range(workloads), range(frontends), range(repetitions), backends, ("stream", "replay")
        )
    ):
        case = f"synthetic-waveform-{workload:02d}"
        adapter = f"example-frontend-{frontend + 1}"
        folder = path / f"run-{index + 1:04d}"
        write_run(
            folder,
            scenario=case,
            frontend=adapter,
            backend=backend,
            repetition=repetition + 1,
            mode=mode,
        )
        manifest = json.loads((folder / "run.json").read_text())
        manifest["provenance"] = {
            "source_sha256": "synthetic-fixture-source",
            "note": "Synthetic QA samples, not benchmark measurements",
        }
        (folder / "run.json").write_text(json.dumps(manifest))
        jobs.append(
            dict(
                scenario=case,
                frontend=adapter,
                backend=backend,
                repetition=repetition + 1,
                mode=mode,
            )
        )
    write_campaign_manifest(
        path,
        jobs=jobs,
        host={
            "cpu_model": "Synthetic QA CPU — no performance claims",
            "machine": "x86_64",
            "os": {"name": "Linux", "version": "Synthetic fixture"},
            "memory_bytes": 16 * 1024**3,
        },
        suite={
            "name": "Synthetic report QA — generated examples, not benchmark measurements",
            "cases": [
                {"name": f"synthetic-waveform-{n:02d}", "config": {"hz": 10}}
                for n in range(workloads)
            ],
        },
        selected_frontends=[f"example-frontend-{n + 1}" for n in range(frontends)],
        selected_modes=["stream", "replay"],
        selected_backends=list(backends),
        repetitions=repetitions,
        warmup_seconds=1,
        measurement_seconds=2,
        cooldown_seconds=0,
        display_context="Synthetic display context, 1280 × 720 logical pixels",
    )
    finalize_campaign_manifest(path, status="completed", attempted=len(jobs), failed=0)
    return report.build_report(path)


def test_both_views_share_analysis_charts_and_machine_readable_outputs(tmp_path, monkeypatch):
    write_run(tmp_path / "run-0001")
    expected = report.summarize_run(tmp_path / "run-0001")
    calls = []
    original = report.summarize_directory

    def summarize(path):
        calls.append(path)
        return original(path)

    monkeypatch.setattr(report, "summarize_directory", summarize)
    compact_path = report.build_report(tmp_path)
    compact = compact_path.read_text()
    extended = (tmp_path / "report-extended.html").read_text()
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert compact_path == tmp_path / "report.html"
    assert calls == [tmp_path]
    assert summary["runs"] == [dict(expected, extension=None)]
    assert summary["comparisons"] == report.aggregate(summary["runs"])
    assert re.findall(r"<svg.*?</svg>", compact, re.S) == re.findall(
        r"<svg.*?</svg>", extended, re.S
    )
    assert len((tmp_path / "summary.csv").read_text().splitlines()) == 2
    assert "No campaign manifest" in compact
    assert "Absent main runs</dt><dd>Not recorded" in compact
    assert 'href="report.html"' in extended
    assert '<table id="runs">' in extended and "<table" not in compact
    assert "<pre>" in extended and "<pre>" not in compact


def test_large_report_omits_per_run_payload_and_keeps_all_charts(tmp_path):
    compact_path = fixture_suite(
        tmp_path, workloads=13, frontends=4, repetitions=3, backends=("rust",)
    )
    compact = compact_path.read_text()
    extended = (tmp_path / "report-extended.html").read_text()
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert len(summary["runs"]) == 312
    assert len(Document(compact).charts) == 26
    assert "Synthetic report QA" in compact
    assert 'id="runs"' not in compact and "<details" not in compact
    assert '"source_sha256"' not in compact and "synthetic-fixture-source" not in compact
    assert "synthetic-fixture-source" in extended
    assert len(compact) < len(extended) / 5


def test_metadata_is_escaped_and_compact_works_without_javascript_or_network(tmp_path):
    hostile = (
        '<script>alert("fixture")</script><img src="https://invalid.example/x" onerror="alert(1)">'
    )
    write_run(tmp_path / "run-0001", scenario=hostile, frontend=hostile)
    campaign(tmp_path, [job(scenario=hostile, frontend=hostile)], display=hostile)
    compact = report.build_report(tmp_path).read_text()
    document = Document(compact)
    assert "&lt;script&gt;" in compact and hostile not in compact
    assert len([tag for tag, _ in document.elements if tag == "script"]) == 1
    assert all(tag not in ("img", "iframe", "link") for tag, _ in document.elements)
    assert all(
        "src" not in attrs and not any(key.startswith("on") for key in attrs)
        for _, attrs in document.elements
    )
    assert "fetch(" not in compact and "XMLHttpRequest" not in compact
    assert "<noscript>" in compact
    assert all("hidden" not in attrs for attrs in document.charts)
    assert document.charts[0]["data-scenario"] == hostile
    assert "submitted updates/s" in compact and "not displayed FPS" in compact


def test_failure_incomplete_and_source_limit_warnings_survive_compact_selection(tmp_path):
    write_run(tmp_path / "run-0001", status="timeout")
    write_run(tmp_path / "run-0002", repetition=2)
    campaign(tmp_path, [job(), job(repetition=2), job(repetition=3)])
    finalize_campaign_manifest(tmp_path, status="interrupted", attempted=2, failed=1)
    source = [dict(time_ms=11000 + n * 100, generation_ms=1, seq=n, clients=1) for n in range(10)]
    (tmp_path / "run-0002" / "source.jsonl").write_text(
        "\n".join(json.dumps(row) for row in source)
    )
    compact = report.build_report(tmp_path).read_text()
    assert "Incomplete campaign" in compact and "1 planned runs absent" in compact
    assert "timeout: 1" in compact and "1/2 valid" in compact
    assert "Smoke validation" in compact
    assert "source-generation shortfall" in compact
    assert compact.index("timeout: 1") < compact.index('<main id="charts">')


@pytest.mark.parametrize(
    "status,empty,expected", [("timeout", False, "timeout"), ("ok", True, "no-data")]
)
def test_no_valid_runs_stay_visible_without_inventing_zero_throughput(
    tmp_path, status, empty, expected
):
    folder = tmp_path / "run-0001"
    write_run(folder, status=status)
    if empty:
        (folder / "measurements.jsonl").write_text("")
    compact = report.build_report(tmp_path).read_text()
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert f"{expected}: 1" in compact and "0/1 valid" in compact
    assert "— Hz" in compact
    assert summary["comparisons"][0]["median_hz"] is None
    assert summary["runs"][0]["status"] == expected


def test_cross_view_links_and_repeated_diagnostic_run_ids_are_distinct(tmp_path):
    main = tmp_path / "main"
    write_run(main / "run-0001")
    campaign(main, [job()])
    write_run(tmp_path / "replay" / "run-0001", mode="replay")
    (main / "diagnostics.json").write_text(
        json.dumps(
            {"replay:first": "../replay", "replay:second": "../replay", "stability": "../absent"}
        )
    )
    compact = report.build_report(main).read_text()
    extended = (main / "report-extended.html").read_text()
    compact_doc, extended_doc = Document(compact), Document(extended)
    assert len(extended_doc.ids) == len(set(extended_doc.ids))
    detail_ids = [
        attrs["id"] for tag, attrs in extended_doc.elements if tag == "details" and "id" in attrs
    ]
    assert len(detail_ids) == 3
    assert "unavailable" in compact and "referenced directory does not exist" in compact
    for tag, attrs in compact_doc.elements:
        if tag == "a" and attrs["href"].startswith("report-extended.html#"):
            assert attrs["href"].split("#", 1)[1] in extended_doc.ids
    for tag, attrs in extended_doc.elements:
        if tag == "a" and attrs["href"].startswith("#"):
            assert attrs["href"][1:] in extended_doc.ids
    report.build_report(main)
    assert Document((main / "report-extended.html").read_text()).ids == extended_doc.ids


def test_compact_script_filters_real_chart_metadata_without_a_browser(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed to execute report selection JavaScript")
    html = fixture_suite(tmp_path).read_text()
    charts = [
        {
            key.removeprefix("data-"): value
            for key, value in chart.items()
            if key.startswith("data-")
        }
        for chart in Document(html).charts
    ]
    script = html.split("<script>", 1)[1].split("</script>", 1)[0]
    harness = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const charts = CHARTS.map(dataset => ({dataset, hidden:false}));
const elements = Object.fromEntries(['scenario','backend','mode'].map(name => [name, {
  value:'', listeners:{}, addEventListener(event, callback) {this.listeners[event]=callback;}
}]));
elements.controls = {hidden:true};
elements['selection-status'] = {textContent:''};
const document = {querySelectorAll:() => charts, getElementById:name => elements[name]};
vm.runInNewContext(SCRIPT, {document});
assert.equal(elements.controls.hidden, false);
assert.equal(charts.filter(chart => !chart.hidden).length, 1);
for (const chart of charts) {
  for (const name of ['scenario','backend','mode']) elements[name].value = chart.dataset[name];
  elements.scenario.listeners.change();
  assert.equal(charts.filter(chart => !chart.hidden).length, 1);
  assert.equal(chart.hidden, false);
}
elements.scenario.value = 'missing'; elements.scenario.listeners.change();
assert.equal(charts.filter(chart => !chart.hidden).length, 0);
assert.match(elements['selection-status'].textContent, /No comparisons match/);
for (const name of ['scenario','backend','mode']) elements[name].value = '';
elements.mode.listeners.change();
assert.equal(charts.filter(chart => !chart.hidden).length, charts.length);
assert.equal(elements['selection-status'].textContent, `${charts.length} of ${charts.length} comparison charts shown.`);
"""
    source = f"const CHARTS = {json.dumps(charts)}; const SCRIPT = {json.dumps(script)};\n{harness}"
    subprocess.run([node, "-e", source], check=True, capture_output=True, text=True)
