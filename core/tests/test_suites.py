"""Suite validation and previews share the exact schedule used for execution."""

import itertools
import json
import random
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from plotbench import cli, probe, runner
from plotbench.suites import expand_cases, plan_from_args, prepare_suite


def minimal_suite():
    return dict(
        cases=[dict(name="wave", config={"view": "waveform"})],
        frontends=["pyqtgraph"],
        modes=["stream"],
        backends=["python"],
        repetitions=1,
    )


def test_schedule_preserves_existing_expansion_and_seeded_job_order():
    suite = minimal_suite()
    suite.update(
        modes=["replay", "stream"],
        backends=["rust", "python"],
        repetitions=2,
        case_groups=[
            dict(
                name="append",
                base={"view": "waveform"},
                matrix={"points": [1000, 2000], "hz": [30, 60]},
            )
        ],
    )
    original = deepcopy(suite)
    plan = prepare_suite(suite)
    assert suite == original
    assert plan.cases[-1] == dict(
        name="append-2000-60",
        config={"view": "waveform", "points": 2000, "hz": 60, "append_count": 200},
    )
    expected = list(
        itertools.product(
            plan.cases, suite["modes"], range(2), suite["frontends"], suite["backends"]
        )
    )
    random.Random(42).shuffle(expected)
    assert plan.jobs == expected
    probe_plan = prepare_suite(suite, kind="probe")
    expected_probe = list(itertools.product(plan.cases, suite["backends"], range(2)))
    random.Random(42).shuffle(expected_probe)
    assert probe_plan.jobs == expected_probe


@pytest.mark.parametrize("kind,defaults", [("run", (5, 30, 1)), ("probe", (2, 10, 0.5))])
def test_defaults_and_cli_timing_overrides_include_cooldown(kind, defaults, tmp_path):
    suite = minimal_suite()
    plan = prepare_suite(suite, kind=kind)
    assert (plan.warmup, plan.measurement, plan.cooldown) == defaults
    suite.update(warmup_seconds=9, measurement_seconds=90, cooldown_seconds=8, repetitions=4)
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(suite))
    args = SimpleNamespace(suite=path, warmup=0, duration=2.5, cooldown=0, repetitions=2)
    plan = plan_from_args(args, kind=kind)
    summary = plan.to_dict()
    assert (plan.warmup, plan.measurement, plan.cooldown, plan.repetitions) == (0, 2.5, 0, 2)
    assert summary["estimate"]["minimum_seconds"] == 5
    assert summary["suite"]["measurement_seconds"] == 2.5
    assert summary["run_count"] == 2
    assert summary["jobs"][0]["config"]["generation"] == 0


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("frontends", [], "frontends"),
        ("frontends", ["missing"], r"frontends\[0\]"),
        ("frontends", ["pyqtgraph", "pyqtgraph"], "duplicates"),
        ("modes", ["stream", "stream"], "duplicates"),
        ("modes", "stream", "modes"),
        ("backends", [["python"]], r"backends\[0\]"),
        ("warmup_seconds", True, "warmup_seconds"),
        ("warmup_seconds", float("inf"), "timing"),
        ("warmup_seconds", 10**1000, "timing"),
        ("measurement_seconds", "30", "measurement_seconds"),
        ("measurement_seconds", 0, "measurement_seconds"),
        ("cooldown_seconds", -1, "cooldown_seconds"),
        ("repetitions", 1.5, "repetitions"),
        ("repetitions", True, "repetitions"),
        ("repetitions", 0, "repetitions"),
        ("order_seed", 1.5, "order_seed"),
        ("display_context", {}, "display_context"),
        ("name", "", "name"),
        ("typo", 1, "unknown fields: typo"),
        ("cases", {}, "cases"),
        ("case_groups", {}, "case_groups"),
    ],
)
def test_invalid_suite_fields_have_actionable_errors(field, value, message):
    suite = minimal_suite()
    suite[field] = value
    with pytest.raises(ValueError, match=message):
        prepare_suite(suite)


@pytest.mark.parametrize(
    "case,message",
    [
        ({"name": "a", "config": {"point": 2}}, r"cases\[0\].config: unknown fields: point"),
        ({"name": "a", "config": {"points": True}}, r"cases\[0\].config: points"),
        ({"name": "a", "config": {"hz": float("nan")}}, r"cases\[0\].config: hz"),
        ({"name": "a", "config": {"points": 3}}, "append_count"),
        ({"name": "a"}, r"cases\[0\].config"),
        ({"name": "", "config": {}}, r"cases\[0\].name"),
    ],
)
def test_invalid_explicit_workloads_retain_field_location(case, message):
    with pytest.raises(ValueError, match=message):
        prepare_suite({"cases": [case]})


@pytest.mark.parametrize(
    "matrix,message",
    [
        ({}, "choose at least one axis"),
        ({"hz": []}, "matrix.hz"),
        ({"hz": 60}, "matrix.hz"),
        ({"points": [False]}, "points"),
        ({"resolutions": [512]}, "unknown fields: resolutions"),
        ({"resolution": [9000]}, "maximum dimensions"),
        ({"hz": [30, 30]}, "names must be unique"),
    ],
)
def test_invalid_matrix_dimensions_fail_before_launch(matrix, message):
    with pytest.raises(ValueError, match=message):
        expand_cases({"case_groups": [dict(name="g", matrix=matrix)]})


def test_limit_applies_before_job_expansion_and_validation_is_not_bypassed():
    suite = minimal_suite()
    suite["cases"].append(dict(name="image", config={"view": "image"}))
    suite["repetitions"] = 3
    assert len(prepare_suite(suite, limit=1).jobs) == 3
    suite["cases"][1]["config"]["hz"] = 999
    with pytest.raises(ValueError, match="hz"):
        prepare_suite(suite, limit=1)


def test_optional_empty_metadata_and_explicit_zero_timings_survive_round_trip():
    suite = minimal_suite()
    suite.update(description="", display_context="", warmup_seconds=0, cooldown_seconds=0)
    for kind in ("run", "probe"):
        preview = prepare_suite(suite, kind=kind).to_dict()
        assert preview["suite"] == suite
        assert preview["warmup_seconds"] == preview["cooldown_seconds"] == 0
        assert (
            prepare_suite(json.loads(json.dumps(preview["suite"])), kind=kind).to_dict() == preview
        )


def test_expansion_limits_are_checked_before_large_cartesian_products():
    with pytest.raises(ValueError, match="expanded cases"):
        prepare_suite({"case_groups": [dict(name="g", matrix={"hz": list(range(10_001))})]})
    with pytest.raises(ValueError, match="100,000 runs"):
        prepare_suite(minimal_suite(), overrides={"repetitions": 100_001})


def test_matrix_dimensions_override_base_resolution_without_mutating_suite():
    suite = dict(
        case_groups=[
            dict(name="wide", base={"resolution": 512}, matrix={"width": [1024, 2048]}),
            dict(name="square", base={"width": 1000, "height": 2000}, matrix={"resolution": [256]}),
        ]
    )
    original = deepcopy(suite)
    cases = expand_cases(suite)
    assert [case["config"] for case in cases] == [
        {"width": 1024, "height": 512},
        {"width": 2048, "height": 512},
        {"width": 256, "height": 256},
    ]
    assert suite == original


@pytest.mark.parametrize("dimension", ["width", "height"])
def test_resolution_and_dimension_axes_cannot_silently_replace_each_other(dimension):
    with pytest.raises(ValueError, match="resolution cannot be combined"):
        expand_cases(
            {"case_groups": [dict(name="image", matrix={"resolution": [512], dimension: [256]})]}
        )


@pytest.mark.parametrize("value", [[], ["unused"], None, {"ignored": True}])
def test_probe_ignores_frontend_and_mode_selections_but_validates_workloads(value):
    suite = dict(minimal_suite(), frontends=value, modes=value)
    plan = prepare_suite(suite, kind="probe")
    assert len(plan.jobs) == 1
    assert plan.frontends == plan.modes == []
    suite["cases"][0]["config"]["hz"] = 999
    with pytest.raises(ValueError, match="hz"):
        prepare_suite(suite, kind="probe")


@pytest.mark.parametrize("kind", ["run", "probe"])
@pytest.mark.parametrize(
    "timings",
    [
        {"measurement_seconds": 1e308},
        {"warmup_seconds": 9e307, "measurement_seconds": 9e307},
        {"cooldown_seconds": 1e308, "repetitions": 2},
        {"measurement_seconds": 1e305, "repetitions": 10_000},
    ],
)
def test_derived_duration_overflow_is_rejected_before_allocating_jobs(kind, timings, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid durations must fail before allocating the schedule")

    monkeypatch.setattr("plotbench.suites.itertools.product", forbidden)
    with pytest.raises(ValueError, match="derived schedule durations and timeouts"):
        prepare_suite(dict(minimal_suite(), **timings), kind=kind)


def test_cli_retains_full_integer_seed_precision():
    suite = minimal_suite()
    suite["order_seed"] = suite["cases"][0]["config"]["seed"] = 9007199254740993
    plan = prepare_suite(json.loads(json.dumps(suite))).to_dict()
    assert plan["suite"]["order_seed"] == plan["jobs"][0]["config"]["seed"] == 9007199254740993


@pytest.mark.parametrize("kind", ["run", "probe"])
def test_json_cli_dry_run_is_pure_machine_readable_and_does_not_start_processes(
    kind, tmp_path, capsys, monkeypatch
):
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(minimal_suite()))
    output = tmp_path / "must-not-exist"

    def forbidden(*args, **kwargs):
        pytest.fail("Dry runs must not inspect artifacts or launch processes")

    for module in (runner, probe):
        monkeypatch.setattr(module, "require_current_artifact", forbidden)
        monkeypatch.setattr(module, "source_process", forbidden)
    monkeypatch.setattr(
        "sys.argv",
        [
            "plotbench",
            kind,
            "--suite",
            str(path),
            "--output",
            str(output),
            "--duration",
            "2",
            "--warmup",
            "0",
            "--cooldown",
            "1",
            "--repetitions",
            "2",
            "--dry-run",
            "--json",
        ],
    )
    cli.main()
    plan = json.loads(capsys.readouterr().out)
    assert plan["kind"] == kind
    assert plan["estimate"]["minimum_seconds"] == 6
    assert not output.exists()


def test_json_requires_dry_run_before_any_launch(tmp_path):
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(minimal_suite()))
    args = SimpleNamespace(suite=path, json=True, dry_run=False)
    with pytest.raises(ValueError, match="--json requires --dry-run"):
        runner.run_suite(args)


def test_shipped_suites_validate_in_both_entrypoints():
    root = Path(__file__).resolve().parents[2]
    for path in (root / "scenarios").glob("*.json"):
        suite = json.loads(path.read_text())
        for kind in ("run", "probe"):
            plan = prepare_suite(suite, kind=kind)
            assert plan.jobs, path
