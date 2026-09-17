"""Shared suite validation, deterministic expansion and read-only execution plans."""

import itertools
import json
import math
import random
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from .backends import BACKENDS, DEFAULT_BACKEND, ROOT
from .config import Config

FRONTENDS = (
    "pyqtgraph",
    "pyqtgraph-gl",
    "matplotlib",
    "qtgraphs",
    "qtgraphs-cpp",
    "iced",
    "fyne",
    "fyne-wasm",
    "jfreechart",
    "plotly",
)
MODES = ("stream", "replay")
# The official comparison suite: the only suite the community results site publishes.
# Identity is structural (the site re-checks every run), so the CLI refuses overrides
# that would change what `--baseline` measures.
BASELINE_SUITE = "scenarios/baseline.json"
BASELINE_FILENAME = "baseline.json"
BASELINE_LOCKED_ARGUMENTS = (
    "duration",
    "warmup",
    "cooldown",
    "repetitions",
    "limit",
    "modes",
    "backends",
    "headless",
)
CONFIG_FIELDS = set(Config().to_dict())
SUITE_FIELDS = {
    "name",
    "description",
    "cases",
    "case_groups",
    "frontends",
    "backends",
    "modes",
    "warmup_seconds",
    "measurement_seconds",
    "cooldown_seconds",
    "repetitions",
    "order_seed",
    "display_context",
}
MAX_CASES = 10_000
MAX_RUNS = 100_000


def _object(value, path, allowed):
    if not isinstance(value, dict):
        raise ValueError(f"{path}: must be an object")
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{path}: unknown fields: {', '.join(sorted(unknown))}")


def _name(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: must be a nonempty string")


def _integer(value, path, minimum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path}: must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{path}: must be at least {minimum}")
    return value


def _timing(value, path, positive=False):
    try:
        finite = isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        finite = False
    if isinstance(value, bool) or not finite or (value <= 0 if positive else value < 0):
        constraint = "positive" if positive else "nonnegative"
        raise ValueError(f"{path}: timing must be a finite {constraint} number")
    return float(value)


def _selection(value, path, allowed):
    if not isinstance(value, list) or not value:
        raise ValueError(f"{path}: choose at least one value in an array")
    for index, item in enumerate(value):
        if not isinstance(item, str) or item not in allowed:
            raise ValueError(f"{path}[{index}]: must be one of {', '.join(allowed)}")
    if len(set(value)) != len(value):
        raise ValueError(f"{path}: choose values without duplicates")
    return value


def _config(value, path):
    _object(value, path, CONFIG_FIELDS)
    try:
        Config(**value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{path}: {exc}") from None


def expand_cases(suite):
    """Expand the established cases/case_groups format without changing its order."""
    _object(suite, "suite", SUITE_FIELDS)
    cases = []
    explicit = suite.get("cases", [])
    groups = suite.get("case_groups", [])
    if not isinstance(explicit, list):
        raise ValueError("cases: must be an array")
    if not isinstance(groups, list):
        raise ValueError("case_groups: must be an array")
    if len(explicit) > MAX_CASES:
        raise ValueError(f"cases: suite exceeds {MAX_CASES:,} expanded cases")
    for index, case in enumerate(explicit):
        path = f"cases[{index}]"
        _object(case, path, {"name", "config"})
        _name(case.get("name"), f"{path}.name")
        _config(case.get("config"), f"{path}.config")
        cases.append(deepcopy(case))
    for index, group in enumerate(groups):
        path = f"case_groups[{index}]"
        _object(group, path, {"name", "base", "matrix"})
        _name(group.get("name"), f"{path}.name")
        base = group.get("base", {})
        _object(base, f"{path}.base", CONFIG_FIELDS | {"resolution"})
        base = dict(base)
        if "resolution" in base:
            base["width"] = base["height"] = base.pop("resolution")
        matrix = group.get("matrix")
        _object(matrix, f"{path}.matrix", CONFIG_FIELDS | {"resolution"})
        if not matrix:
            raise ValueError(f"{path}.matrix: choose at least one axis")
        if "resolution" in matrix and {"width", "height"} & matrix.keys():
            raise ValueError(
                f"{path}.matrix: resolution cannot be combined with width or height axes"
            )
        for key, values in matrix.items():
            if not isinstance(values, list) or not values:
                raise ValueError(f"{path}.matrix.{key}: must be a nonempty array")
        count = math.prod(len(values) for values in matrix.values())
        if len(cases) + count > MAX_CASES:
            raise ValueError(f"{path}.matrix: suite exceeds {MAX_CASES:,} expanded cases")
        keys = list(matrix)
        for combination in itertools.product(*(matrix[key] for key in keys)):
            values = dict(zip(keys, combination, strict=True))
            if "resolution" in values:
                values["width"] = values["height"] = values.pop("resolution")
            config = dict(base, **values)
            if "points" in config and "append_count" not in config:
                _integer(config["points"], f"{path}.points", 1)
                config["append_count"] = max(1, config["points"] // 10)
            _config(config, f"{path}.config ({dict(zip(keys, combination, strict=True))})")
            label = "-".join(str(value) for value in combination)
            cases.append(dict(name=f"{group['name']}-{label}", config=config))
    if not cases:
        raise ValueError("suite has no cases")
    if len(cases) > MAX_CASES:
        raise ValueError(f"cases: suite exceeds {MAX_CASES:,} expanded cases")
    names = [case["name"] for case in cases]
    if len(set(names)) != len(names):
        raise ValueError("scenario names must be unique to keep different workloads separate")
    return cases


@dataclass(frozen=True)
class SuitePlan:
    kind: str
    suite: dict
    cases: list
    frontends: list
    modes: list
    backends: list
    repetitions: int
    warmup: float
    measurement: float
    cooldown: float
    jobs: list

    def to_dict(self):
        jobs = []
        for number, job in enumerate(self.jobs, 1):
            if self.kind == "run":
                case, mode, repetition, frontend, backend = job
            else:
                case, backend, repetition = job
                mode, frontend = "probe", None
            jobs.append(
                dict(
                    run_id=f"run-{number:04d}",
                    scenario=case["name"],
                    mode=mode,
                    repetition=repetition + 1,
                    frontend=frontend,
                    backend=backend,
                    config=Config(**case["config"]).to_dict(),
                )
            )
        count = len(jobs)
        sampling = count * (self.warmup + self.measurement)
        cooldown = count * self.cooldown
        return dict(
            kind=self.kind,
            suite=self.suite,
            case_count=len(self.cases),
            run_count=count,
            selected_frontends=self.frontends,
            selected_modes=self.modes,
            selected_backends=self.backends,
            repetitions=self.repetitions,
            warmup_seconds=self.warmup,
            measurement_seconds=self.measurement,
            cooldown_seconds=self.cooldown,
            estimate=dict(
                sampling_seconds=sampling,
                cooldown_seconds=cooldown,
                minimum_seconds=sampling + cooldown,
                note="Excludes process startup, preload, teardown and report generation.",
            ),
            jobs=jobs,
        )


def prepare_suite(suite, *, kind="run", overrides=None, limit=None):
    """Validate and resolve a suite; explicitly provided CLI values take precedence."""
    if kind not in ("run", "probe"):
        raise ValueError("kind: must be run or probe")
    _object(suite, "suite", SUITE_FIELDS)
    effective = deepcopy(suite)
    for key, value in (overrides or {}).items():
        if value is not None:
            effective[key] = deepcopy(value)
    _object(effective, "suite", SUITE_FIELDS)
    if "name" in effective:
        _name(effective["name"], "name")
    for key in ("description", "display_context"):
        if key in effective and not isinstance(effective[key], str):
            raise ValueError(f"{key}: must be a string")
    cases = expand_cases(effective)
    if limit is not None:
        cases = cases[: _integer(limit, "limit", 1)]
    probe = kind == "probe"
    frontends = (
        []
        if probe
        else _selection(effective.get("frontends", list(FRONTENDS)), "frontends", FRONTENDS)
    )
    modes = [] if probe else _selection(effective.get("modes", list(MODES)), "modes", MODES)
    backends = _selection(effective.get("backends", [DEFAULT_BACKEND]), "backends", BACKENDS)
    repetitions = _integer(effective.get("repetitions", 3), "repetitions", 1)
    seed = _integer(effective.get("order_seed", 42), "order_seed")
    warmup = _timing(effective.get("warmup_seconds", 2 if probe else 5), "warmup_seconds")
    measurement = _timing(
        effective.get("measurement_seconds", 10 if probe else 30),
        "measurement_seconds",
        positive=True,
    )
    cooldown = _timing(effective.get("cooldown_seconds", 0.5 if probe else 1), "cooldown_seconds")
    count = len(cases) * len(backends) * repetitions
    if not probe:
        count *= len(modes) * len(frontends)
    if count > MAX_RUNS:
        raise ValueError(f"suite: exceeds {MAX_RUNS:,} runs; narrow the matrix or use --limit")
    sampling = count * (warmup + measurement)
    cooldown_total = count * cooldown
    derived_durations = (
        sampling,
        cooldown_total,
        sampling + cooldown_total,
        count * (warmup + measurement + cooldown),
        3 * (warmup + measurement) + 90,
        (warmup + measurement) * 1000,
    )
    if not all(math.isfinite(value) for value in derived_durations):
        raise ValueError(
            "timings: derived schedule durations and timeouts must stay finite; "
            "reduce timings or repetitions"
        )
    jobs = list(
        itertools.product(cases, backends, range(repetitions))
        if probe
        else itertools.product(cases, modes, range(repetitions), frontends, backends)
    )
    random.Random(seed).shuffle(jobs)
    return SuitePlan(
        kind,
        effective,
        cases,
        frontends,
        modes,
        backends,
        repetitions,
        warmup,
        measurement,
        cooldown,
        jobs,
    )


def load_suite(path):
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError(f"{path}: invalid suite JSON: {exc}") from None


def check_baseline_overrides(args):
    """Refuse CLI overrides that would turn a `--baseline` run into an unpublishable one."""
    if not getattr(args, "baseline", False):
        return
    if Path(args.suite).resolve() != (ROOT / BASELINE_SUITE).resolve():
        raise ValueError("--baseline runs the official suite unmodified; remove --suite")
    for name in BASELINE_LOCKED_ARGUMENTS:
        value = getattr(args, name, None)
        if value is not None and value is not False:
            raise ValueError(
                f"--baseline runs the official suite unmodified; remove --{name} "
                "(only --frontends may narrow it)"
            )


def plan_from_args(args, *, kind="run"):
    check_baseline_overrides(args)
    overrides = {
        name: getattr(args, name, None)
        for name in ("frontends", "modes", "backends", "repetitions", "display_context")
    }
    for argument, field in (
        ("warmup", "warmup_seconds"),
        ("duration", "measurement_seconds"),
        ("cooldown", "cooldown_seconds"),
    ):
        overrides[field] = getattr(args, argument, None)
    return prepare_suite(
        load_suite(args.suite), kind=kind, overrides=overrides, limit=getattr(args, "limit", None)
    )


def print_plan(plan, *, json_output=False, detailed=True):
    """Print a preview without inspecting or starting installed frontends."""
    if json_output:
        print(json.dumps(plan.to_dict(), indent=2, allow_nan=False))
        return
    count = len(plan.jobs)
    label = "sequential" if plan.kind == "run" else "receiver-only"
    minimum = count * (plan.warmup + plan.measurement + plan.cooldown)
    print(
        f"{count} {label} runs · {count * (plan.warmup + plan.measurement) / 60:.1f} "
        f"minutes of sampling · at least {minimum / 60:.1f} minutes including cooldown; "
        "plus startup/preload/teardown",
        flush=True,
    )
    if detailed:
        for job in plan.jobs:
            if plan.kind == "run":
                case, mode, rep, frontend, backend = job
                print(f"{case['name']} / {mode} / {frontend} / {backend} / repeat {rep + 1}")
            else:
                case, backend, rep = job
                print(f"{case['name']} / {backend} / repeat {rep + 1}")
