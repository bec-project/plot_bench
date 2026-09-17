"""Suite validation and previews share the exact schedule used for execution."""

import itertools
import json
import random
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from plotbench import cli, probe, runner
from plotbench.config import Config
from plotbench.suites import (
    BASELINE_SUITE,
    CONFIG_FIELDS,
    FRONTENDS,
    expand_cases,
    plan_from_args,
    prepare_suite,
)

ROOT = Path(__file__).resolve().parents[2]


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


def test_multi_plot_axes_expand_with_derived_append_count_and_field_named_cases():
    suite = dict(
        case_groups=[
            dict(
                name="layout",
                base={"view": "both", "points": 10000, "resolution": 256},
                matrix={"waveform_plots": [1, 2], "curves": [1, 3], "image_plots": [4]},
            )
        ]
    )
    cases = expand_cases(suite)
    assert [case["name"] for case in cases] == [
        "layout-1-1-4",
        "layout-1-3-4",
        "layout-2-1-4",
        "layout-2-3-4",
    ]
    assert cases[-1]["config"] == {
        "view": "both",
        "points": 10000,
        "append_count": 1000,
        "width": 256,
        "height": 256,
        "waveform_plots": 2,
        "curves": 3,
        "image_plots": 4,
    }
    job = prepare_suite(suite).to_dict()["jobs"][0]["config"]
    assert {job["waveform_plots"], job["image_plots"]} <= {1, 2, 4} and job["curves"] in (1, 3)


@pytest.mark.parametrize(
    "config,message",
    [
        ({"curves": 0}, r"cases\[0\].config: curves must be between 1 and 64"),
        ({"curves": 65}, r"cases\[0\].config: curves must be between 1 and 64"),
        ({"waveform_plots": 17}, r"cases\[0\].config: waveform_plots must be between 1 and 16"),
        ({"image_plots": 0}, r"cases\[0\].config: image_plots must be between 1 and 16"),
        ({"curves": True}, r"cases\[0\].config: curves must be an integer"),
        ({"waveform_plots": 2.0}, r"cases\[0\].config: waveform_plots must be an integer"),
        ({"curves": 64, "waveform_plots": 16, "points": 10_000_000}, "256 MiB"),
    ],
)
def test_invalid_plot_and_curve_counts_are_located_in_the_case(config, message):
    with pytest.raises(ValueError, match=message):
        prepare_suite({"cases": [dict(name="a", config=config)]})


@pytest.mark.parametrize(
    "matrix,message",
    [
        ({"curves": [1, 65]}, r"case_groups\[0\].config .*curves must be between 1 and 64"),
        ({"waveform_plots": [0]}, r"case_groups\[0\].config .*waveform_plots must be between"),
        ({"image_plots": [16, 17]}, r"case_groups\[0\].config .*image_plots must be between"),
        ({"curves": [False]}, r"case_groups\[0\].config .*curves must be an integer"),
    ],
)
def test_invalid_plot_and_curve_axes_fail_before_launch(matrix, message):
    with pytest.raises(ValueError, match=message):
        expand_cases({"case_groups": [dict(name="g", matrix=matrix)]})


def _shipped(name):
    root = Path(__file__).resolve().parents[2]
    return json.loads((root / "scenarios" / f"{name}.json").read_text())


def test_smoke_suite_exercises_the_multi_plot_path_of_every_adapter():
    suite = _shipped("smoke")
    case = {case["name"]: case["config"] for case in suite["cases"]}["multi-plots-30hz"]
    assert case == {
        "view": "both",
        "hz": 30,
        "points": 10000,
        "append_count": 1000,
        "curves": 2,
        "waveform_plots": 2,
        "width": 256,
        "height": 256,
        "waveform_mode": "replace",
        "image_mode": "scalar",
        "image_plots": 2,
    }
    assert len(prepare_suite(suite).jobs) == 3 * 6 * 2


SIX_FRONTENDS = ["pyqtgraph", "pyqtgraph-gl", "matplotlib", "qtgraphs", "iced", "plotly"]


def test_multi_plot_smoke_scenario_matches_its_specification():
    suite = _shipped("multi-plot-smoke")
    assert suite["frontends"] == SIX_FRONTENDS and suite["modes"] == ["stream", "replay"]
    assert (
        suite["warmup_seconds"],
        suite["measurement_seconds"],
        suite["repetitions"],
        suite["cooldown_seconds"],
        suite["order_seed"],
    ) == (1, 3, 1, 0.5, 42)
    configs = {case["name"]: Config(**case["config"]) for case in suite["cases"]}
    assert list(configs) == [
        "two-waveforms-three-curves-three-images-30hz",
        "four-waveforms-four-curves-60hz",
        "four-images-rgb-30hz",
    ]
    combined = configs["two-waveforms-three-curves-three-images-30hz"]
    assert (combined.view, combined.hz, combined.points, combined.append_count) == (
        "both",
        30,
        10000,
        1000,
    )
    assert (combined.curves, combined.waveform_plots, combined.image_plots) == (3, 2, 3)
    assert (combined.width, combined.height, combined.image_mode) == (256, 256, "scalar")
    waveforms = configs["four-waveforms-four-curves-60hz"]
    assert (waveforms.view, waveforms.hz, waveforms.points, waveforms.waveform_mode) == (
        "waveform",
        60,
        10000,
        "replace",
    )
    assert (waveforms.curves, waveforms.waveform_plots) == (4, 4)
    images = configs["four-images-rgb-30hz"]
    assert (images.view, images.hz, images.width, images.height, images.image_mode) == (
        "image",
        30,
        256,
        256,
        "rgb",
    )
    assert images.image_plots == 4
    plan = prepare_suite(suite)
    assert plan.backends == ["rust"] and len(plan.jobs) == 3 * 6 * 2


def test_beamline_dashboard_scenario_matches_its_specification():
    suite = _shipped("beamline-dashboard")
    assert suite["backends"] == ["rust"] and suite["modes"] == ["stream"]
    assert suite["frontends"] == SIX_FRONTENDS
    assert (
        suite["warmup_seconds"],
        suite["measurement_seconds"],
        suite["repetitions"],
        suite["cooldown_seconds"],
    ) == (5, 30, 3, 2)
    configs = {case["name"]: Config(**case["config"]) for case in suite["cases"]}
    expected = {
        "monitor-wall-10hz": ("both", 10, 4, 2, 10000, "replace", 2, 512, "scalar"),
        "detector-live-30hz": ("both", 30, 2, 4, 100000, "append", 1, 1024, "rgb"),
        "scan-overview-60hz": ("waveform", 60, 6, 3, 10000, "append", 1, 512, "scalar"),
        "multi-detector-30hz": ("image", 30, 1, 1, 10000, "replace", 4, 512, "scalar"),
        "everything-open-30hz": ("both", 30, 4, 4, 100000, "replace", 4, 512, "scalar"),
    }
    assert list(configs) == list(expected)
    for name, values in expected.items():
        config = configs[name]
        assert (
            config.view,
            config.hz,
            config.waveform_plots,
            config.curves,
            config.points,
            config.waveform_mode,
            config.image_plots,
            config.width,
            config.image_mode,
        ) == values, name
        assert config.height == config.width
        assert config.append_count == config.points // 10
    assert len(prepare_suite(suite).jobs) == 5 * 6 * 3


def test_multi_plot_sweep_scenario_matches_its_specification():
    suite = _shipped("multi-plot-sweep")
    assert suite["backends"] == ["rust"] and suite["modes"] == ["stream"]
    assert suite["frontends"] == SIX_FRONTENDS
    assert (
        suite["warmup_seconds"],
        suite["measurement_seconds"],
        suite["repetitions"],
        suite["cooldown_seconds"],
    ) == (5, 30, 3, 2)
    groups = {group["name"]: group for group in suite["case_groups"]}
    assert groups["curves"]["matrix"] == {"curves": [1, 4, 16], "points": [10000, 100000]}
    assert groups["curves"]["base"] == {"view": "waveform", "hz": 60, "points": 10000}
    assert groups["waveform-plots"]["matrix"] == {"waveform_plots": [1, 2, 4, 8], "curves": [1, 4]}
    assert groups["waveform-plots"]["base"]["waveform_mode"] == "replace"
    assert groups["image-plots"]["matrix"] == {"image_plots": [1, 2, 4], "resolution": [256, 512]}
    assert groups["image-plots"]["base"] == {"view": "image", "hz": 30, "image_mode": "scalar"}
    cases = expand_cases(suite)
    names = [case["name"] for case in cases]
    assert len(names) == 6 + 8 + 6 and names[:2] == ["curves-1-10000", "curves-1-100000"]
    assert "waveform-plots-8-4" in names and "image-plots-4-512" in names
    assert all(Config(**case["config"]).append_count > 0 for case in cases)
    assert len(prepare_suite(suite).jobs) == 20 * 6 * 3


BASELINE_COMMON = {
    "hz": 60,
    "points": 10000,
    "append_count": 1000,
    "waveform_mode": "replace",
    "curves": 1,
    "waveform_plots": 1,
    "width": 512,
    "height": 512,
    "image_mode": "scalar",
    "image_plots": 1,
    "seed": 42,
}


def test_baseline_scenario_matches_its_specification():
    suite = _shipped("baseline")
    assert suite["name"] == "Plotbench baseline"
    assert suite["backends"] == ["rust"] and suite["modes"] == ["stream"]
    # Membership is explicit: every listed frontend exists in the catalog, a subset is allowed.
    assert suite["frontends"] and set(suite["frontends"]) <= set(FRONTENDS)
    assert len(set(suite["frontends"])) == len(suite["frontends"])
    assert "case_groups" not in suite
    assert (
        suite["warmup_seconds"],
        suite["measurement_seconds"],
        suite["cooldown_seconds"],
        suite["repetitions"],
        suite["order_seed"],
    ) == (5, 30, 2, 3, 42)
    expected = {
        "waveform": dict(BASELINE_COMMON, view="waveform"),
        "multi-curve": dict(BASELINE_COMMON, view="waveform", curves=10),
        "multi-plot": dict(BASELINE_COMMON, view="waveform", curves=5, waveform_plots=2),
        "scalar-image": dict(BASELINE_COMMON, view="image"),
        "rgb-image": dict(BASELINE_COMMON, view="image", image_mode="rgb"),
        "multi-image": dict(BASELINE_COMMON, view="image", image_plots=4),
        "large-image": dict(BASELINE_COMMON, view="image", width=2048, height=2048),
    }
    configs = {case["name"]: case["config"] for case in suite["cases"]}
    assert list(configs) == list(expected)
    for name, config in configs.items():
        # Every published field is explicit so no consumer re-implements Config defaults.
        assert set(config) == CONFIG_FIELDS - {"generation"}, name
        assert config == expected[name], name
    assert len({Config(**config) for config in configs.values()}) == 7
    plan = prepare_suite(suite)
    assert plan.backends == ["rust"] and plan.modes == ["stream"]
    assert plan.frontends == suite["frontends"]
    assert plan.kind == "run" and len(plan.jobs) == 7 * len(suite["frontends"]) * 3


def _baseline_args(**overrides):
    args = SimpleNamespace(suite=ROOT / BASELINE_SUITE, baseline=True)
    for name, value in overrides.items():
        setattr(args, name, value)
    return args


def test_baseline_flag_refuses_a_copy_of_the_suite_at_another_path(tmp_path):
    copy = tmp_path / "scenarios" / "baseline.json"
    copy.parent.mkdir()
    copy.write_text((ROOT / "scenarios" / "smoke.json").read_text())
    with pytest.raises(ValueError, match="remove --suite"):
        plan_from_args(_baseline_args(suite=copy))


def test_baseline_flag_allows_narrowing_by_frontend_only():
    plan = plan_from_args(_baseline_args())
    assert len(plan.jobs) == 210
    plan = plan_from_args(_baseline_args(frontends=["pyqtgraph"]))
    assert plan.frontends == ["pyqtgraph"] and len(plan.jobs) == 21
    plan = plan_from_args(
        _baseline_args(output=Path("results/x"), display_context="fixed 120 Hz, 2x")
    )
    assert len(plan.jobs) == 210 and plan.suite["display_context"] == "fixed 120 Hz, 2x"


def test_baseline_flag_refuses_a_frontend_outside_the_official_baseline():
    # Only frontends listed in scenarios/baseline.json may run under --baseline,
    # even if the catalog later gains a frontend the baseline does not include.
    baseline = json.loads((ROOT / BASELINE_SUITE).read_text())
    assert "phantom-frontend" not in baseline["frontends"]
    with pytest.raises(ValueError, match="not part of it"):
        plan_from_args(_baseline_args(frontends=["phantom-frontend"]))


@pytest.mark.parametrize(
    "argument,value",
    [
        ("duration", 3),
        ("warmup", 0),
        ("cooldown", 0),
        ("repetitions", 1),
        ("limit", 2),
        ("modes", ["replay"]),
        ("backends", ["python"]),
        ("headless", True),
    ],
)
def test_baseline_flag_refuses_overrides_that_change_the_suite(argument, value):
    with pytest.raises(ValueError, match=f"unmodified; remove --{argument}"):
        plan_from_args(_baseline_args(**{argument: value}))


def test_baseline_flag_refuses_a_different_suite_file():
    args = _baseline_args(suite=ROOT / "scenarios" / "smoke.json")
    with pytest.raises(ValueError, match="remove --suite"):
        plan_from_args(args)


def test_baseline_cli_selects_the_official_suite_at_parse_time(monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr("sys.argv", ["plotbench", "run", "--baseline", "--dry-run", "--json"])
    cli.main()
    plan = json.loads(capsys.readouterr().out)
    assert plan["suite"]["name"] == "Plotbench baseline"
    assert plan["run_count"] == 210
    assert (plan["warmup_seconds"], plan["measurement_seconds"], plan["cooldown_seconds"]) == (
        5,
        30,
        2,
    )

    monkeypatch.setattr(
        "sys.argv",
        ["plotbench", "run", "--baseline", "--frontends", "pyqtgraph", "--dry-run", "--json"],
    )
    cli.main()
    plan = json.loads(capsys.readouterr().out)
    assert plan["selected_frontends"] == ["pyqtgraph"] and plan["run_count"] == 21

    monkeypatch.setattr(
        "sys.argv", ["plotbench", "run", "--baseline", "--duration", "3", "--dry-run"]
    )
    with pytest.raises(SystemExit) as exited:
        cli.main()
    assert exited.value.code == 1
    assert "remove --duration" in capsys.readouterr().err


def test_serve_derives_plot_and_curve_options_from_config(monkeypatch, tmp_path):
    launched = {}

    def launch(config, output, host, port):
        launched.update(config=config, output=output, host=host, port=port)

    monkeypatch.setattr("plotbench.backends.launch_rust_source", launch)
    monkeypatch.setattr(
        "sys.argv",
        [
            "plotbench",
            "serve",
            "--backend",
            "rust",
            "--output",
            str(tmp_path / "demo"),
            "--curves",
            "3",
            "--waveform-plots",
            "2",
            "--image-plots",
            "4",
        ],
    )
    cli.main()
    config = launched["config"]
    assert (config.curves, config.waveform_plots, config.image_plots) == (3, 2, 4)
    assert config.generation == 1 and launched["port"] == 8765
    assert not (tmp_path / "demo").exists()
