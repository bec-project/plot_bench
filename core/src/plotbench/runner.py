"""Sequential process-isolated scenario runner, including a visible browser worker."""

import itertools
import json
import math
import os
import random
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import psutil

from .backends import backend_from_health, validate_backend
from .campaign import finalize_campaign_manifest, write_campaign_manifest
from .client import request
from .config import Config
from .provenance import capture_provenance, require_current_artifact

FRONTENDS = (
    "pyqtgraph",
    "pyqtgraph-gl",
    "matplotlib",
    "qtgraphs",
    "qtgraphs-cpp",
    "iced",
    "plotly",
)
BUILT_COMPONENTS = ("rust", "iced", "plotly", "qtgraphs-cpp")
ROOT = Path(__file__).resolve().parents[3]


def frontend_command(name, url, mode, run_id, duration=0, headless=False, screenshot=None):
    args = ["--url", url, "--mode", mode, "--run-id", run_id, "--duration", str(duration)]
    if name == "iced":
        executable = ROOT / "frontends/iced/target/release/plotbench-iced"
    elif name == "qtgraphs-cpp":
        executable = ROOT / "frontends/qtgraphs-cpp/build/plotbench-qtgraphs-cpp"
    elif name == "plotly":
        command = [sys.executable, "-m", "plotbench.browser_worker", *args]
        if headless:
            command.append("--headless")
        if screenshot:
            command.extend(["--screenshot", str(screenshot)])
        return command
    else:
        package = "pyqtgraph" if name == "pyqtgraph-gl" else name
        executable = ROOT / f".envs/plotting-benchmark-{package}/bin/plotbench-{package}"
        if name == "pyqtgraph-gl":
            args.append("--opengl")
    if not executable.exists():
        raise FileNotFoundError(f"{executable} is missing; run ./scripts/setup {name}")
    return [str(executable), *args]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop_process(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def wait_health(url, process, timeout=20, backend=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("source exited during startup; see server.log")
        try:
            health = json.loads(request(url + "/api/health", timeout=1))
            if health["status"] == "ok":
                if backend is not None and backend_from_health(health) != backend:
                    raise RuntimeError(f"source backend does not match requested {backend}")
                return health
        except OSError:
            pass
        time.sleep(0.1)
    raise RuntimeError("source startup timed out")


@contextmanager
def source_process(output, config=None, port=None, backend="python"):
    validate_backend(backend)
    port = port or free_port()
    url = f"http://127.0.0.1:{port}"
    output.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "plotbench.cli",
        "serve",
        "--backend",
        backend,
        "--port",
        str(port),
        "--output",
        str(output),
    ]
    if config is not None:
        config_file = output / "config.json"
        config_file.write_text(json.dumps(config.to_dict(), indent=2) + "\n")
        cmd += ["--config", str(config_file)]
    with (output / "server.log").open("w") as log:
        process = subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True)
        try:
            wait_health(url, process, backend=backend)
            yield url
        finally:
            stop_process(process)


def frontend_timeout(warmup, measurement):
    """Hard limit per frontend process, above the browser worker's scaled completion grace."""
    return 3 * (warmup + measurement) + 90


def monitor_process(process, path, timeout):
    started = time.monotonic()
    tracked = {}
    with path.open("w") as output:
        while process.poll() is None:
            if time.monotonic() - started > timeout:
                stop_process(process)
                return "timeout"
            try:
                root = psutil.Process(process.pid)
                processes = [root, *root.children(recursive=True)]
                cpu, rss = 0.0, 0
                for current in processes:
                    try:
                        known = tracked.setdefault(current.pid, current)
                        cpu += known.cpu_percent()
                        rss += known.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                output.write(
                    json.dumps(
                        dict(
                            time_ms=time.time_ns() / 1e6,
                            cpu_percent=cpu,
                            rss_bytes=rss,
                            process_count=len(processes),
                        )
                    )
                    + "\n"
                )
            except psutil.NoSuchProcess:
                pass
            time.sleep(0.25)
    return "ok" if process.returncode == 0 else f"exit-{process.returncode}"


def expand_cases(suite):
    cases = list(suite.get("cases", []))
    for group in suite.get("case_groups", []):
        keys = list(group["matrix"])
        for combination in itertools.product(*(group["matrix"][key] for key in keys)):
            config = dict(group.get("base", {}), **dict(zip(keys, combination, strict=True)))
            if "resolution" in config:
                config["width"] = config["height"] = config.pop("resolution")
            if "points" in config and "append_count" not in config:
                config["append_count"] = max(1, config["points"] // 10)
            label = "-".join(str(value) for value in combination)
            cases.append(dict(name=f"{group['name']}-{label}", config=config))
    if not cases:
        raise ValueError("suite has no cases")
    names = [case["name"] for case in cases]
    if len(set(names)) != len(names):
        raise ValueError("scenario names must be unique to keep different workloads separate")
    for case in cases:
        Config(**case["config"])
    return cases


def run_suite(args):
    suite = json.loads(args.suite.read_text())
    cases = expand_cases(suite)
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("limit must be positive")
        cases = cases[: args.limit]
    frontends = args.frontends or suite.get("frontends", list(FRONTENDS))
    if set(frontends) - set(FRONTENDS):
        raise ValueError(f"frontends must be drawn from {FRONTENDS}")
    modes = args.modes or suite.get("modes", ["stream", "replay"])
    backends = getattr(args, "backends", None) or suite.get("backends", ["python"])
    if not backends or len(set(backends)) != len(backends):
        raise ValueError("choose at least one backend, without duplicates")
    for backend in backends:
        validate_backend(backend)
    repetitions = int(suite.get("repetitions", 3))
    warmup = float(suite.get("warmup_seconds", 5))
    measurement = float(suite.get("measurement_seconds", 30))
    cooldown = float(suite.get("cooldown_seconds", 1))
    if (
        not all(math.isfinite(value) for value in (warmup, measurement, cooldown))
        or repetitions < 1
        or warmup < 0
        or measurement <= 0
        or cooldown < 0
    ):
        raise ValueError("invalid repetition count or timing")
    jobs = list(itertools.product(cases, modes, range(repetitions), frontends, backends))
    random.Random(suite.get("order_seed", 42)).shuffle(jobs)
    nominal = len(jobs) * (warmup + measurement)
    print(
        f"{len(jobs)} sequential runs · {nominal / 60:.1f} minutes of sampling, plus startup/preload/cooldown",
        flush=True,
    )
    if args.dry_run:
        for case, mode, rep, frontend, backend in jobs:
            print(f"{case['name']} / {mode} / {frontend} / {backend} / repeat {rep + 1}")
        return
    artifacts = {
        component: require_current_artifact(component)
        for component in BUILT_COMPONENTS
        if component in backends or component in frontends
    }
    display_context = getattr(args, "display_context", None) or suite.get("display_context")
    provenance = dict(capture_provenance(), artifacts=artifacts, display_context=display_context)
    output = (
        args.output or ROOT / "results" / datetime.now().strftime("suite-%Y%m%d-%H%M%S")
    ).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "suite.json").exists():
        raise ValueError(
            "output already contains a suite; use a new directory to preserve previous results"
        )
    # The hardware/display snapshot and timezone-aware start are recorded once here,
    # before the first measured window; no per-run hardware queries are added.
    write_campaign_manifest(
        output,
        jobs=[
            dict(
                scenario=case["name"],
                mode=mode,
                repetition=rep + 1,
                frontend=frontend,
                backend=backend,
            )
            for case, mode, rep, frontend, backend in jobs
        ],
        suite=suite,
        selected_frontends=frontends,
        selected_modes=modes,
        selected_backends=backends,
        repetitions=repetitions,
        warmup_seconds=warmup,
        measurement_seconds=measurement,
        cooldown_seconds=cooldown,
        headless=args.headless,
        argv=sys.argv,
        provenance=provenance,
    )
    failed = 0
    attempted = 0
    completion = "completed"
    try:
        for number, (case, mode, rep, frontend, backend) in enumerate(jobs, 1):
            attempted = number
            run_id = f"run-{number:04d}"
            folder = output / run_id
            config = Config(**case["config"])
            manifest = dict(
                run_id=run_id,
                frontend=frontend,
                backend=backend,
                mode=mode,
                repetition=rep + 1,
                scenario=case["name"],
                config=config.to_dict(),
                warmup_seconds=warmup,
                measurement_seconds=measurement,
                headless=args.headless,
                status="starting",
                provenance=provenance,
            )
            print(
                f"[{number}/{len(jobs)}] {frontend} · {backend} · {mode} · {case['name']}",
                flush=True,
            )
            folder.mkdir()
            try:
                manifest["provenance"] = dict(
                    capture_provenance(),
                    artifacts={
                        component: require_current_artifact(component)
                        for component in BUILT_COMPONENTS
                        if component in (backend, frontend)
                    },
                    display_context=display_context,
                )
                with source_process(folder, config, backend=backend) as url:
                    command = frontend_command(
                        frontend, url, mode, run_id, warmup + measurement + 0.2, args.headless, None
                    )
                    manifest["command"] = command
                    with (folder / "frontend.log").open("w") as log:
                        process = subprocess.Popen(
                            command, stdout=log, stderr=log, start_new_session=True
                        )
                        try:
                            manifest["status"] = monitor_process(
                                process,
                                folder / "resources.jsonl",
                                frontend_timeout(warmup, measurement),
                            )
                        finally:
                            stop_process(process)
                    manifest["source_health"] = json.loads(request(url + "/api/health"))
                after = capture_provenance()
                manifest["provenance_after"] = after
                if after["source_sha256"] != manifest["provenance"]["source_sha256"]:
                    manifest["status"] = "provenance-changed"
                    manifest["error"] = "source files changed during the run"
                for component, before in manifest["provenance"]["artifacts"].items():
                    if require_current_artifact(component)["files"] != before["files"]:
                        manifest["status"] = "provenance-changed"
                        manifest["error"] = f"{component} artifact changed during the run"
            except (OSError, RuntimeError, ValueError) as exc:
                manifest["status"], manifest["error"] = "failed", str(exc)
            except KeyboardInterrupt:
                manifest["status"] = "interrupted"
                raise
            finally:
                (folder / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")
            if manifest["status"] == "ok":
                from .report import summarize_run

                manifest["status"] = summarize_run(folder)["status"]
                (folder / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")
            if manifest["status"] != "ok":
                failed += 1
                print(
                    f"  {manifest['status']}: {manifest.get('error', 'see frontend.log')}",
                    flush=True,
                )
            time.sleep(cooldown)
    except KeyboardInterrupt:
        completion = "interrupted"
        raise
    except BaseException:
        completion = "error"
        raise
    finally:
        finalize_campaign_manifest(output, status=completion, attempted=attempted, failed=failed)
        from .report import build_report

        print(f"Report: {build_report(output)}", flush=True)
    if failed:
        raise RuntimeError(f"{failed} runs failed; their errors are retained in the report")


def launch_demo(args):
    owned_source = None
    requested_backend = getattr(args, "backend", None)
    try:
        try:
            health = json.loads(request(args.url + "/api/health", timeout=1))
            actual_backend = backend_from_health(health)
            if requested_backend is not None and requested_backend != actual_backend:
                raise RuntimeError(
                    f"{args.url} is running {actual_backend}, but {requested_backend} was requested. "
                    "Use a different --url port or stop that source first."
                )
        except OSError:
            parsed = urlparse(args.url)
            if parsed.hostname not in ("127.0.0.1", "localhost"):
                raise RuntimeError("remote source unavailable") from None
            output = ROOT / "results" / datetime.now().strftime("demo-%Y%m%d-%H%M%S")
            actual_backend = requested_backend or "python"
            owned_source = source_process(output, port=parsed.port or 8765, backend=actual_backend)
            owned_source.__enter__()
        print(f"Source backend: {actual_backend} · Live workload controls: {args.url}", flush=True)
        command = frontend_command(args.frontend, args.url, args.mode, "demo")
        if args.frontend == "plotly":
            command.append("--interactive")
        process = subprocess.Popen(command, start_new_session=True)
        try:
            process.wait()
        except KeyboardInterrupt:
            stop_process(process)
        if process.returncode not in (0, -signal.SIGTERM):
            raise RuntimeError(f"frontend exited with {process.returncode}")
    finally:
        if owned_source is not None:
            owned_source.__exit__(None, None, None)
