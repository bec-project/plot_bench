import json
import re
from datetime import datetime

import pytest

from plotbench.campaign import (
    finalize_campaign_manifest,
    parse_timestamp,
    read_campaign,
    write_campaign_manifest,
)
from plotbench.report import build_report, run_time_series
from plotbench.series import series_svg

HOST = {
    "recorded_at": "2026-09-08T18:00:00+00:00",
    "platform": "macOS-15.7.5-arm64-arm-64bit-Mach-O",
    "machine": "arm64",
    "logical_cpus": 10,
    "physical_cpus": 10,
    "memory_bytes": 17179869184,
    "os": {"name": "macOS", "version": "15.7.5", "build": "24G624"},
    "model_identifier": "MacBookPro18,3",
    "cpu_model": "Apple M1 Pro <script>alert(1)</script>",
    "graphics": [
        {
            "sppci_model": "Apple M1 Pro",
            "spdisplays_vendor": "sppci_vendor_Apple",
            "sppci_cores": "16",
            "spdisplays_mtlgpufamilysupport": "spdisplays_metal3",
        }
    ],
    "displays": [
        {
            "_name": "Color LCD",
            "_spdisplays_pixels": "3024 x 1964",
            "_spdisplays_resolution": "1512 x 982 @ 120.00Hz",
            "spdisplays_pixelresolution": "spdisplays_3024x1964Retina",
            "spdisplays_main": "spdisplays_yes",
            "spdisplays_connection_type": "spdisplays_internal",
            "spdisplays_display_type": "spdisplays_built-in-liquid-retina-xdr",
            "spdisplays_online": "spdisplays_yes",
            "spdisplays_mirror": "spdisplays_off",
        }
    ],
}


def write_run(
    folder,
    *,
    scenario="waveform",
    frontend="example",
    mode="stream",
    repetition=1,
    backend="rust",
    status="ok",
    hz=10,
    warmup=1,
    measurement=2,
    seconds_of_samples=None,
    silent_second=None,
    resources_until_second=None,
):
    folder.mkdir(parents=True)
    manifest = dict(
        run_id=folder.name,
        scenario=scenario,
        frontend=frontend,
        backend=backend,
        mode=mode,
        repetition=repetition,
        config={"hz": hz},
        warmup_seconds=warmup,
        measurement_seconds=measurement,
        status=status,
        source_health={"backend": backend},
    )
    (folder / "run.json").write_text(json.dumps(manifest))
    seconds = seconds_of_samples if seconds_of_samples is not None else warmup + measurement + 0.3
    period = 1000 / hz
    samples = []
    for n in range(int(seconds * hz)):
        time_ms = 10000 + n * period
        elapsed = (time_ms - 10000 - warmup * 1000) / 1000
        if silent_second is not None and silent_second <= elapsed < silent_second + 1:
            continue
        samples.append(
            dict(
                seq=n,
                generation=0,
                skipped=0,
                client_time_ms=time_ms,
                update_ms=0.5,
                receive_age_ms=2 if mode == "stream" else None,
            )
        )
    batch = dict(
        run_id=folder.name,
        frontend=frontend,
        mode=mode,
        metadata={"plot_viewports": {"waveform": [800, 600]}},
        samples=samples,
    )
    (folder / "measurements.jsonl").write_text(json.dumps(batch) + "\n")
    if resources_until_second is not None:
        lines = []
        time_ms = 10000 + warmup * 1000
        end = time_ms + resources_until_second * 1000
        while time_ms < end:
            lines.append(json.dumps(dict(time_ms=time_ms, cpu_percent=50, rss_bytes=200 * 2**20)))
            time_ms += 250
        (folder / "resources.jsonl").write_text("\n".join(lines) + "\n")
    return manifest


def campaign(
    output, jobs, *, host=HOST, display="Built-in <b>display</b> 120 Hz", measurement_seconds=2
):
    return write_campaign_manifest(
        output,
        jobs=jobs,
        host=host,
        suite={
            "name": "fixture",
            "warmup_seconds": 1,
            "measurement_seconds": measurement_seconds,
            "cooldown_seconds": 0,
            "repetitions": 1,
            "cases": [{"name": "waveform", "config": {"hz": 10}}],
        },
        selected_frontends=["example"],
        selected_modes=["stream"],
        selected_backends=["rust"],
        repetitions=1,
        warmup_seconds=1,
        measurement_seconds=measurement_seconds,
        cooldown_seconds=0,
        headless=False,
        argv=["plotbench", "run"],
        provenance={"display_context": display},
    )


def job(scenario="waveform", frontend="example", repetition=1, mode="stream"):
    return dict(
        scenario=scenario, mode=mode, repetition=repetition, frontend=frontend, backend="rust"
    )


def test_campaign_manifest_records_timezone_aware_interval_and_completion(tmp_path):
    record = campaign(tmp_path, [job(), job(repetition=2)])
    assert datetime.fromisoformat(record["started_at"]).tzinfo is not None
    assert record["started_at_utc"].endswith("+00:00")
    assert re.fullmatch(r"[+-]\d{2}:\d{2}", record["timezone"]["utc_offset"])
    assert record["runs_planned"] == 2 and record["completion_status"] == "running"
    finalize_campaign_manifest(tmp_path, status="interrupted", attempted=1, failed=0)
    campaign_record = read_campaign(tmp_path)
    assert campaign_record["completion_status"] == "interrupted"
    assert campaign_record["runs_attempted"] == 1 and campaign_record["runs_planned"] == 2
    assert campaign_record["started_moment"].tzinfo is not None
    assert "UTC" in campaign_record["timezone"]


def test_report_embeds_hardware_and_acquisition_dates_and_escapes_metadata(tmp_path):
    campaign(tmp_path, [job()])
    write_run(tmp_path / "run-0001")
    finalize_campaign_manifest(tmp_path, status="completed", attempted=1, failed=0)
    html = build_report(tmp_path).read_text()
    expected_fragments = (
        "MacBookPro18,3",
        "macOS 15.7.5 (24G624)",
        "Color LCD",
        "1512 x 982 @ 120.00Hz",
        "main display",
        "spdisplays_metal3",
        "16.0 GiB",
        "10 / 10",
        "Complete campaign",
        "Timezone of acquisition",
    )
    for expected in expected_fragments:
        assert expected in html, expected
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "Built-in &lt;b&gt;display&lt;/b&gt; 120 Hz" in html
    summary = json.loads((tmp_path / "summary.json").read_text())
    hardware = summary["campaign"]["hardware"]
    assert hardware["cpu_model"] == HOST["cpu_model"]
    assert hardware["main_display"]["configured"] == "1512 x 982 @ 120.00Hz"
    assert summary["campaign"]["timezone"] and summary["campaign"]["started_at"] != "Not recorded"
    assert summary["campaign"]["recorded_runs"] == 1 and summary["campaign"]["missing_runs"] == []


def test_regeneration_preserves_recorded_dates_and_hardware_but_updates_generation_time(tmp_path):
    campaign(tmp_path, [job()])
    write_run(tmp_path / "run-0001")
    finalize_campaign_manifest(tmp_path, status="completed", attempted=1, failed=0)
    build_report(tmp_path)
    first = json.loads((tmp_path / "summary.json").read_text())
    build_report(tmp_path)
    second = json.loads((tmp_path / "summary.json").read_text())
    for key in ("started_at", "completed_at", "timezone", "hardware"):
        assert first["campaign"][key] == second["campaign"][key]
    assert second["campaign"]["hardware"]["cpu_model"] == HOST["cpu_model"]
    assert first["report_generated_at"] != second["report_generated_at"]
    assert first["campaign"]["report_generated_at"] != second["campaign"]["report_generated_at"]


def test_legacy_results_fall_back_to_run_host_json_without_inventing_fields(tmp_path):
    write_run(tmp_path / "run-0001")
    (tmp_path / "run-0001" / "host.json").write_text(
        json.dumps(
            {
                "backend": "rust",
                "recorded_at_ms": 1788877928182.728,
                "platform": "Darwin host 24.6.0 arm64",
                "machine": "aarch64",
                "logical_cpus": 10,
                "physical_cpus": 10,
                "memory_bytes": 17179869184,
                "cpu_model": "Apple M1 Pro",
            }
        )
    )
    html = build_report(tmp_path).read_text()
    assert "No campaign manifest" in html
    assert "Apple M1 Pro" in html and "aarch64" in html
    assert "2026-09-08T14:32:08+00:00" in html
    assert "recorded by the rust source" in html
    summary = json.loads((tmp_path / "summary.json").read_text())
    hardware = summary["campaign"]["hardware"]
    assert hardware["os"] is None and hardware["displays"] == [] and hardware["graphics"] == []
    assert summary["campaign"]["started_at"] == "Not recorded"
    assert html.count("Not recorded") >= 5


def test_legacy_naive_timestamps_never_receive_a_timezone(tmp_path):
    write_run(tmp_path / "run-0001")
    (tmp_path / "suite.json").write_text(
        json.dumps(
            {
                "suite": {"cases": [{"name": "waveform", "config": {"hz": 10}}]},
                "started_at": "2026-09-08T13:39:59.208868",
            }
        )
    )
    campaign_record = read_campaign(tmp_path)
    assert campaign_record["started_at"] == "2026-09-08T13:39:59.208868 (timezone not recorded)"
    assert campaign_record["timezone"] == "Not recorded"
    assert campaign_record["hardware"] is None
    assert parse_timestamp("nonsense") == (None, "unreadable: nonsense")
    html = build_report(tmp_path).read_text()
    assert "timezone not recorded" in html


def test_incomplete_campaign_lists_absent_runs_instead_of_omitting_them(tmp_path):
    campaign(tmp_path, [job(), job(repetition=2), job(scenario="image")])
    write_run(tmp_path / "run-0001")
    finalize_campaign_manifest(tmp_path, status="interrupted", attempted=1, failed=0)
    html = build_report(tmp_path).read_text()
    assert "Incomplete campaign" in html
    assert "1 of 3 planned runs recorded" in html and "2 planned runs absent" in html
    assert "image · stream · example · rust · repeat 1" in html
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert [item["scenario"] for item in summary["campaign"]["missing_runs"]] == [
        "waveform",
        "image",
    ]
    assert summary["campaign"]["completion_status"] == "interrupted"


def test_diagnostics_are_separate_sections_with_directory_qualified_links(tmp_path):
    main = tmp_path / "frontends"
    main.mkdir()
    campaign(main, [job()])
    write_run(main / "run-0001")
    finalize_campaign_manifest(main, status="completed", attempted=1, failed=0)
    replay = tmp_path / "replay"
    replay.mkdir()
    campaign(replay, [job(mode="replay")])
    write_run(replay / "run-0001", mode="replay")
    finalize_campaign_manifest(replay, status="completed", attempted=1, failed=0)
    stability = tmp_path / "stability"
    stability.mkdir()
    campaign(stability, [job()], measurement_seconds=5)
    write_run(
        stability / "run-0001",
        measurement=5,
        seconds_of_samples=6.5,
        silent_second=2,
        resources_until_second=2.5,
    )
    finalize_campaign_manifest(stability, status="completed", attempted=1, failed=0)
    probe = tmp_path / "source-probe"
    probe.mkdir()
    (probe / "summary.json").write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "scenario": "waveform",
                        "backend": "rust",
                        "repetition": 1,
                        "status": "ok",
                        "target_hz": 10,
                        "source_hz": 9.9,
                        "received_hz": 9.8,
                        "target_met": True,
                        "gap_percent": 0.0,
                        "path": "run-0001",
                    }
                ]
            }
        )
    )
    (probe / "report.html").write_text("<p>probe</p>")
    (main / "diagnostics.json").write_text(
        json.dumps(
            {"replay": "../replay", "stability": "../stability", "source_probe": "../source-probe"}
        )
    )
    html = build_report(main).read_text()
    summary = json.loads((main / "summary.json").read_text())
    assert len(summary["runs"]) == 1 and len(summary["comparisons"]) == 1
    entries = summary["diagnostics"]["entries"]
    assert {kind: entry["status"] for kind, entry in entries.items()} == {
        "replay": "available",
        "stability": "available",
        "source_probe": "available",
    }
    assert len(entries["replay"]["runs"]) == 1 and entries["replay"]["runs"][0]["mode"] == "replay"
    assert entries["replay"]["comparisons"][0]["mode"] == "replay"
    series = entries["stability"]["runs"][0]["series"]
    assert len(series["submissions_per_bin"]) == 5 and series["zero_bins"] == 1
    assert series["submissions_per_bin"][2] == 0 and series["resource_observations"] == 10
    assert 'href="../replay/run-0001/measurements.jsonl"' in html
    assert 'href="../stability/run-0001/resources.jsonl"' in html
    assert 'href="../source-probe/report.html"' in html
    assert "replay · run-0001" in html and "stability · run-0001" in html
    assert "Replay diagnostic" in html and "Stability diagnostic" in html
    assert (
        "1 bins with zero submissions" in html
        and "10 observations inside the measured window" in html
    )
    assert html.count('<table id="runs">') == 1
    main_table = html.split('<table id="runs">')[1].split("</table>")[0]
    assert main_table.count("<tr>") == 2  # header plus the single main run
    assert len((main / "summary.csv").read_text().splitlines()) == 2  # header + main run only


def test_missing_or_unknown_diagnostics_are_reported_unavailable(tmp_path):
    campaign(tmp_path, [job()])
    write_run(tmp_path / "run-0001")
    finalize_campaign_manifest(tmp_path, status="completed", attempted=1, failed=0)
    (tmp_path / "diagnostics.json").write_text(json.dumps({"replay": "../nowhere", "bogus": "x"}))
    html = build_report(tmp_path).read_text()
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["diagnostics"]["entries"]["replay"]["status"] == "unavailable"
    assert "does not exist" in summary["diagnostics"]["entries"]["replay"]["error"]
    assert "unknown diagnostic kind" in summary["diagnostics"]["entries"]["bogus"]["error"]
    assert "Unavailable: referenced directory does not exist" in html
    assert "has no <code>stability</code> entry" in html
    assert "has no <code>source_probe</code> entry" in html


def test_replacement_attempts_are_a_separate_section_and_never_replace_failures(tmp_path):
    main = tmp_path / "frontends"
    main.mkdir()
    campaign(main, [job()])
    write_run(main / "run-0001", status="exit-1")
    finalize_campaign_manifest(main, status="completed", attempted=1, failed=1)
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    campaign(replacement, [job()])
    write_run(replacement / "run-0001")
    finalize_campaign_manifest(replacement, status="completed", attempted=1, failed=0)
    (main / "diagnostics.json").write_text(json.dumps({"replacement": "../replacement"}))
    html = build_report(main).read_text()
    summary = json.loads((main / "summary.json").read_text())
    assert summary["runs"][0]["status"] == "exit-1" and summary["comparisons"][0]["valid"] == 0
    entry = summary["diagnostics"]["entries"]["replacement"]
    assert entry["status"] == "available" and entry["runs"][0]["status"] == "ok"
    assert "Replacement attempts after a harness fix" in html
    assert 'href="../replacement/run-0001/measurements.jsonl"' in html
    assert "replacement · run-0001" in html
    assert "exit-1" in html.split('<table id="runs">')[1].split("</table>")[0]


def test_labelled_diagnostic_attempts_stay_separate_sections(tmp_path):
    main = tmp_path / "frontends"
    main.mkdir()
    campaign(main, [job()])
    write_run(main / "run-0001")
    finalize_campaign_manifest(main, status="completed", attempted=1, failed=0)
    for name in ("stability", "stability-rerun"):
        folder = tmp_path / name
        folder.mkdir()
        campaign(folder, [job()], measurement_seconds=4)
        write_run(folder / "run-0001", measurement=4, seconds_of_samples=5.5)
        finalize_campaign_manifest(folder, status="completed", attempted=1, failed=0)
    (main / "diagnostics.json").write_text(
        json.dumps(
            {
                "stability:first attempt": {
                    "path": "../stability",
                    "note": "Throttled by the host after 30 s; read with <care>.",
                },
                "stability": "../stability-rerun",
            }
        )
    )
    html = build_report(main).read_text()
    summary = json.loads((main / "summary.json").read_text())
    entries = summary["diagnostics"]["entries"]
    assert entries["stability:first attempt"]["label"] == "first attempt"
    assert entries["stability:first attempt"]["reference"] == "../stability"
    assert entries["stability:first attempt"]["note"].startswith("Throttled")
    assert (
        "Operator note.</strong> Throttled by the host after 30 s; read with &lt;care&gt;." in html
    )
    assert entries["stability"]["label"] is None and entries["stability"]["note"] is None
    assert html.count("Stability diagnostic") == 2
    assert "Stability diagnostic · first attempt" in html
    assert 'href="../stability/run-0001/measurements.jsonl"' in html
    assert 'href="../stability-rerun/run-0001/measurements.jsonl"' in html
    assert "stability · first attempt · run-0001" in html and "stability · run-0001" in html
    assert "has no <code>stability</code> entry" not in html


def test_extension_runs_merge_into_the_comparison_only_when_they_match_the_suite(tmp_path):
    main = tmp_path / "frontends"
    main.mkdir()
    campaign(main, [job()])
    write_run(main / "run-0001")
    finalize_campaign_manifest(main, status="completed", attempted=1, failed=0)
    extension = tmp_path / "cpp"
    extension.mkdir()
    campaign(extension, [job(frontend="cpp"), job(frontend="cpp", scenario="other")])
    write_run(extension / "run-0001", frontend="cpp")
    write_run(extension / "run-0002", frontend="cpp", scenario="other")
    write_run(extension / "run-0003", frontend="cpp", hz=99)
    write_run(extension / "run-0004", frontend="cpp", mode="replay")
    finalize_campaign_manifest(extension, status="completed", attempted=4, failed=0)
    (main / "diagnostics.json").write_text(json.dumps({"extension:cpp": "../cpp"}))
    html = build_report(main).read_text()
    summary = json.loads((main / "summary.json").read_text())
    assert summary["campaign"]["recorded_runs"] == 1
    assert summary["campaign"]["merged_extension_runs"] == 1
    assert [row["extension"] for row in summary["runs"]] == [None, "cpp"]
    assert {(g["frontend"], g["scenario"]) for g in summary["comparisons"]} == {
        ("example", "waveform"),
        ("cpp", "waveform"),
    }
    entry = summary["diagnostics"]["entries"]["extension:cpp"]
    assert entry["merged_run_ids"] == ["run-0001"]
    assert {item["run_id"]: item["reasons"] for item in entry["excluded_runs"]} == {
        "run-0002": ["scenario is not in the main suite"],
        "run-0003": ["workload configuration differs from the main suite"],
        "run-0004": ["delivery mode is not part of the main suite"],
    }
    assert "1 from cpp (cpp;" in html and "Extension runs merged into the comparison" in html
    assert "cpp · run-0001" in html and 'href="../cpp/run-0001/measurements.jsonl"' in html
    assert "run-0003 · cpp · waveform: workload configuration differs" in html
    main_table = html.split('<table id="runs">')[1].split("</table>")[0]
    assert main_table.count("<tr>") == 3  # header, main run, merged extension run
    csv = (main / "summary.csv").read_text().splitlines()
    assert "extension" in csv[0].split(",") and len(csv) == 3


def test_absent_diagnostics_manifest_is_stated(tmp_path):
    write_run(tmp_path / "run-0001")
    html = build_report(tmp_path).read_text()
    assert "No <code>diagnostics.json</code> manifest" in html
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["diagnostics"] == {"manifest_present": False, "error": None, "entries": {}}


def test_time_series_keep_zero_bins_and_missing_resource_observations(tmp_path):
    write_run(tmp_path / "run-0001", measurement=4, seconds_of_samples=6, silent_second=1)
    series = run_time_series(tmp_path / "run-0001")
    assert series["submissions_per_bin"] == [10, 0, 10, 10]
    assert series["zero_bins"] == 1
    assert series["rss_mib"] == [] and series["resource_observations"] == 0
    svg = series_svg(series, title="fixture")
    assert "No resource observations were recorded" in svg
    assert "1 bins with zero submissions" in svg
    assert svg.count("<rect") == 3


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, (None, "Not recorded")),
        (
            1700000000000,
            (datetime.fromisoformat("2023-11-14T22:13:20+00:00"), "UTC epoch milliseconds"),
        ),
        ("2026-09-08T10:00:00+02:00", (datetime.fromisoformat("2026-09-08T10:00:00+02:00"), None)),
    ],
)
def test_timestamp_parsing_distinguishes_epoch_and_iso(value, expected):
    assert parse_timestamp(value) == expected
