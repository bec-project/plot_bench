import json

import pytest

from plotbench.report import (
    aggregate,
    build_report,
    deadline_counter_increase,
    delivery_ack_rate,
    summarize_run,
    workload_label,
)
from plotbench.runner import expand_cases


def write_run(folder, *, status="ok", duplicate=False):
    folder.mkdir()
    manifest = dict(
        run_id=folder.name,
        scenario="waveform",
        frontend="example",
        mode="stream",
        repetition=1,
        config={"hz": 10},
        warmup_seconds=1,
        measurement_seconds=2,
        status=status,
    )
    (folder / "run.json").write_text(json.dumps(manifest))
    samples = [
        dict(
            seq=n,
            generation=0,
            skipped=0,
            client_time_ms=10000 + n * 100,
            update_ms=n,
            receive_age_ms=2,
        )
        for n in range(33)
    ]
    batch = dict(
        run_id=folder.name, frontend="example", mode="stream", metadata={}, samples=samples
    )
    (folder / "measurements.jsonl").write_text(
        json.dumps(batch) + "\n" + (json.dumps(batch) + "\n" if duplicate else "")
    )
    return samples


def test_fixed_measurement_window_excludes_warmup_and_tail(tmp_path):
    folder = tmp_path / "run-0001"
    write_run(folder, duplicate=True)
    row = summarize_run(folder)
    assert row["samples"] == 20
    assert row["submitted_hz"] == 10
    assert row["update_p50_ms"] == 19.5
    assert row["update_p95_ms"] == pytest.approx(28.05)
    assert row["duplicate_samples"] == 33
    assert row["sustained_candidate"] is False


def test_failures_are_retained_but_not_ranked(tmp_path):
    folder = tmp_path / "run-0001"
    write_run(folder, status="timeout")
    row = summarize_run(folder)
    comparison = aggregate([row])[0]
    assert comparison["attempted"] == 1
    assert comparison["valid"] == 0
    assert comparison["median_hz"] is None
    report = build_report(tmp_path).with_name("report-extended.html")
    assert "timeout" in report.read_text()
    assert "displayed FPS" in report.read_text()
    assert (tmp_path / "summary.csv").exists()


def test_case_expansion_preserves_cartesian_matrix():
    cases = expand_cases(
        {
            "case_groups": [
                {
                    "name": "images",
                    "base": {"view": "image"},
                    "matrix": {
                        "resolution": [256, 512],
                        "image_mode": ["rgb", "scalar"],
                        "hz": [30, 120],
                    },
                }
            ]
        }
    )
    assert len(cases) == 8
    assert cases[-1]["config"]["width"] == cases[-1]["config"]["height"] == 512


@pytest.mark.parametrize(
    "metadata,expected",
    [
        ({"config": {"hz": 120}}, "configuration-changed"),
        ({"telemetry_lost": 1}, "incomplete-telemetry"),
        ({"dropped_metric_samples": 2}, "incomplete-telemetry"),
        ({"termination_reason": "user"}, "interrupted"),
        ({"receiver_connection_epoch": 2}, "receiver-reconnected"),
    ],
)
def test_invalid_measurement_evidence_is_excluded(tmp_path, metadata, expected):
    folder = tmp_path / "run-0001"
    write_run(folder)
    path = folder / "measurements.jsonl"
    batch = json.loads(path.read_text())
    batch["metadata"] = metadata
    path.write_text(json.dumps(batch) + "\n")
    row = summarize_run(folder)
    assert row["status"] == expected
    assert aggregate([row])[0]["valid"] == 0


def test_single_run_report_links_point_to_local_raw_files(tmp_path):
    folder = tmp_path / "run-0001"
    write_run(folder)
    text = build_report(folder).with_name("report-extended.html").read_text()
    assert 'href="./measurements.jsonl"' in text
    assert 'href="run-0001/measurements.jsonl"' not in text


def test_backend_results_are_never_pooled(tmp_path):
    rows = []
    for backend in ("python", "rust"):
        folder = tmp_path / backend
        write_run(folder)
        path = folder / "run.json"
        manifest = json.loads(path.read_text())
        manifest.update(backend=backend, source_health={"backend": backend})
        path.write_text(json.dumps(manifest))
        rows.append(summarize_run(folder))
    groups = aggregate(rows)
    assert len(groups) == 2
    assert {group["backend"] for group in groups} == {"python", "rust"}
    assert all(group["attempted"] == group["valid"] == 1 for group in groups)
    text = build_report(tmp_path).with_name("report-extended.html").read_text()
    assert "python source" in text and "rust source" in text
    assert "<th>Backend</th>" in text and "<th>Source Hz</th>" in text


def test_wrong_source_backend_is_excluded(tmp_path):
    folder = tmp_path / "run"
    write_run(folder)
    path = folder / "run.json"
    manifest = json.loads(path.read_text())
    manifest.update(backend="rust", source_health={"backend": "python"})
    path.write_text(json.dumps(manifest))
    row = summarize_run(folder)
    assert row["status"] == "backend-mismatch"
    assert aggregate([row])[0]["valid"] == 0


def test_unhealthy_source_cannot_produce_a_ranked_result(tmp_path):
    folder = tmp_path / "run"
    write_run(folder)
    path = folder / "run.json"
    manifest = json.loads(path.read_text())
    manifest["source_health"] = dict(backend="python", status="error", error="generation failed")
    path.write_text(json.dumps(manifest))
    row = summarize_run(folder)
    assert row["status"] == "source-error"
    assert row["error"] == "generation failed"
    assert aggregate([row])[0]["valid"] == 0


def test_duplicate_scenario_names_cannot_pool_different_workloads():
    with pytest.raises(ValueError, match="names must be unique"):
        expand_cases(
            {
                "cases": [
                    dict(name="same", config={"points": 1000}),
                    dict(name="same", config={"points": 10000}),
                ]
            }
        )


def test_optional_timing_coverage_uses_measured_window_and_never_fills_missing_with_zero(tmp_path):
    folder = tmp_path / "run"
    write_run(folder)
    path = folder / "measurements.jsonl"
    batch = json.loads(path.read_text())
    for sample in batch["samples"]:
        sample["update_complete_ms"] = 100 + sample["seq"]
        if sample["seq"] % 2 == 0:
            sample["draw_ms"] = sample["seq"]
    batch["metadata"]["measurement_stage"] = "A unique documented boundary"
    path.write_text(json.dumps(batch) + "\n")
    row = summarize_run(folder)
    assert row["draw_samples"] == 10
    assert row["draw_coverage_percent"] == 50
    assert row["draw_p50_ms"] == 19
    assert row["update_complete_samples"] == 20
    assert row["update_complete_p50_ms"] == 119.5
    assert row["image_upload_wait_p50_ms"] is None
    report = build_report(folder).with_name("report-extended.html").read_text()
    assert "Observation coverage" in report and "10/20 (50.0%)" in report
    assert "A unique documented boundary" in report
    assert "Stage observations are not additive" in report
    summary = json.loads((folder / "summary.json").read_text())
    assert "report_provenance" in summary


def test_counter_statistics_distinguish_missing_and_multi_client_evidence():
    samples = [
        {"time_ms": 1000, "clients": 1, "acknowledgements_total": 10, "deadline_misses_total": 2},
        {"time_ms": 2000, "clients": 1, "acknowledgements_total": 69, "deadline_misses_total": 3},
    ]
    assert delivery_ack_rate(samples) == 59
    assert deadline_counter_increase(samples) == 1
    assert delivery_ack_rate([dict(s, clients=2) for s in samples]) is None
    assert delivery_ack_rate([samples[1], samples[0]]) is None
    # The client disconnecting at the very end of the window shortens the span; it does not
    # hide the rate. A missing client before or inside the span stays ambiguous.
    trailing = samples + [{"time_ms": 2100, "clients": 0, "acknowledgements_total": 69}]
    assert delivery_ack_rate(trailing) == 59
    assert delivery_ack_rate([{"time_ms": 500, "clients": 0}, *samples]) is None
    assert delivery_ack_rate([samples[0], {"time_ms": 1500, "clients": 0}, samples[1]]) is None
    assert delivery_ack_rate(samples + [{"time_ms": 2100, "clients": 2}]) is None
    assert deadline_counter_increase([samples[1], samples[0]]) is None
    assert delivery_ack_rate([{"time_ms": 1000}]) is None
    assert deadline_counter_increase([{"time_ms": 1000}, {"time_ms": 2000}]) is None


def test_report_preserves_each_runs_provenance_and_links(tmp_path):
    for index in range(2):
        folder = tmp_path / f"run-{index}"
        write_run(folder)
        path = folder / "run.json"
        record = json.loads(path.read_text())
        record["provenance"] = {"git": {"commit": f"revision-{index}"}}
        path.write_text(json.dumps(record))
    html = build_report(tmp_path).with_name("report-extended.html").read_text()
    for index in range(2):
        assert f"revision-{index}" in html
        assert f'href="run-{index}/measurements.jsonl"' in html


@pytest.mark.parametrize("move", [False, True])
def test_measured_display_changes_are_retained_and_excluded_from_comparisons(tmp_path, move):
    folder = tmp_path / "run"
    write_run(folder)
    path = folder / "measurements.jsonl"
    original = json.loads(path.read_text())
    batches = []
    for first, last, name in (
        (0, 10, "startup"),
        (10, 20, "main"),
        (20, 33, "other" if move else "main"),
    ):
        batch = dict(
            original,
            samples=original["samples"][first:last],
            metadata={"display": {"name": name, "recorded_at_ms": first * 1000}},
        )
        batches.append(batch)
    path.write_text("\n".join(json.dumps(batch) for batch in batches))
    row = summarize_run(folder)
    assert len(row["observed_display_contexts"]) == (2 if move else 1)
    assert row["status"] == ("display-changed" if move else "ok")
    assert aggregate([row])[0]["valid"] == (0 if move else 1)


@pytest.mark.parametrize("difference", ["source", "artifact", "display", "runtime", "headless"])
def test_repetitions_with_different_execution_contexts_are_not_pooled(tmp_path, difference):
    folder = tmp_path / "run"
    write_run(folder)
    base = summarize_run(folder)
    base.update(
        sustained_candidate=True,
        provenance={"source_sha256": "A", "artifacts": {"iced": {"files": {"binary": "A"}}}},
    )
    changed = json.loads(json.dumps(base))
    if difference == "source":
        changed["provenance"]["source_sha256"] = "B"
    elif difference == "artifact":
        changed["provenance"]["artifacts"]["iced"]["files"]["binary"] = "B"
    elif difference == "display":
        changed["metadata"]["display"] = {"name": "different monitor"}
    elif difference == "runtime":
        changed["metadata"]["versions"] = {"numpy": "different"}
    else:
        changed["metadata"]["headless"] = True
    groups = aggregate([base, changed, base])
    assert sorted(group["valid"] for group in groups) == [1, 2]
    assert not any(group["repeated_sustained_candidate"] for group in groups)


@pytest.mark.parametrize(
    "key,value",
    [
        ("browser_selection", "custom"),
        ("browser_executable", "/example/custom-chromium"),
        ("browser_executable_sha256", "different-binary-with-the-same-version"),
        ("browser_launch_arguments", ["--ozone-platform=wayland"]),
        ("playwright_version", "different-driver"),
        ("display_protocol_requested", "wayland"),
        ("display_session", {"session_type": "wayland", "desktop": "different-compositor"}),
    ],
)
def test_same_browser_version_with_different_execution_settings_is_not_pooled(tmp_path, key, value):
    folder = tmp_path / "run"
    write_run(folder)
    base = summarize_run(folder)
    base["metadata"]["browser_version"] = "123.0"
    changed = json.loads(json.dumps(base))
    changed["metadata"][key] = value
    groups = aggregate([base, changed, base])
    assert sorted(group["valid"] for group in groups) == [1, 2]


def test_workload_label_names_plot_and_curve_counts_only_when_they_exceed_one():
    base = {
        "view": "both",
        "hz": 30,
        "points": 10000,
        "append_count": 1000,
        "width": 256,
        "height": 256,
        "waveform_mode": "replace",
        "image_mode": "scalar",
    }
    single = dict(base, curves=1, waveform_plots=1, image_plots=1)
    assert workload_label(single) == "both · 10,000 points replace · 256 × 256 scalar · 30 Hz"
    assert workload_label(base) == workload_label(single)  # legacy records without the fields
    multi = dict(base, curves=3, waveform_plots=2, image_plots=3)
    assert workload_label(multi) == (
        "both · 10,000 points replace · 2 plots × 3 curves · 256 × 256 scalar · 3 plots · 30 Hz"
    )
    assert workload_label(dict(base, curves=3)) == (
        "both · 10,000 points replace · 1 plot × 3 curves · 256 × 256 scalar · 30 Hz"
    )
    append = dict(base, view="waveform", waveform_mode="append", waveform_plots=4)
    assert (
        workload_label(append)
        == "waveform · 10,000 points append +1,000 · 4 plots × 1 curve · 30 Hz"
    )
    images = dict(base, view="image", image_mode="rgb", image_plots=4, curves=8)
    assert workload_label(images) == "image · 256 × 256 rgb · 4 plots · 30 Hz"
    assert workload_label(dict(multi, curves="3", waveform_plots=True)) == workload_label(
        dict(base, image_plots=3)
    )
