"""Command-line entry points for the standalone benchmark."""

import argparse
import json
import signal
from datetime import datetime
from pathlib import Path

from .backends import BACKENDS, DEFAULT_BACKEND
from .config import Config
from .suites import BASELINE_SUITE, FRONTENDS


class BaselineAction(argparse.Action):
    """`run --baseline`: select the official suite at parse time.

    Setting `suite` here (instead of resolving a flag later in `main`) keeps every
    documented `run --baseline` example expanding the real baseline file.
    """

    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, default=False, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, True)
        namespace.suite = Path(BASELINE_SUITE)


def add_suite_options(parser):
    parser.add_argument("--duration", type=float, help="override measured seconds per repetition")
    parser.add_argument("--warmup", type=float, help="override warmup seconds")
    parser.add_argument("--cooldown", type=float, help="override cooldown seconds after each run")
    parser.add_argument("--repetitions", type=int, help="override repetition count")
    parser.add_argument(
        "--dry-run", action="store_true", help="validate and preview without launching"
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable preview; requires --dry-run"
    )


def _raise_keyboard_interrupt(signum, frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description="Plotbench streaming and rendering benchmark")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="start the unified source and live controls")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--config", type=Path)
    serve.add_argument("--backend", choices=BACKENDS, default=DEFAULT_BACKEND)
    serve.add_argument(
        "--output",
        type=Path,
        default=Path("results") / datetime.now().strftime("demo-%Y%m%d-%H%M%S"),
    )
    for name, default in Config().to_dict().items():
        if name != "generation":
            serve.add_argument("--" + name.replace("_", "-"), type=type(default), default=None)
    run = sub.add_parser("run", help="run a suite sequentially and generate a report")
    # argparse enforces the exclusion in both argument orders; the guard in
    # suites.check_baseline_overrides covers programmatic callers.
    suite_group = run.add_mutually_exclusive_group()
    suite_group.add_argument("--suite", type=Path, default=Path("scenarios/smoke.json"))
    suite_group.add_argument(
        "--baseline",
        action=BaselineAction,
        help="run the official baseline suite unmodified; only --frontends may narrow it",
    )
    run.add_argument("--frontends", nargs="+", choices=FRONTENDS)
    run.add_argument("--modes", nargs="+", choices=("stream", "replay"))
    run.add_argument("--backends", nargs="+", choices=BACKENDS)
    run.add_argument(
        "--limit", type=int, help="maximum number of cases (before frontend/repetition expansion)"
    )
    run.add_argument("--output", type=Path)
    run.add_argument(
        "--display-context",
        help="operator-recorded display identity, configured refresh/scaling and placement; also accepted in suite JSON",
    )
    run.add_argument(
        "--headless",
        action="store_true",
        help="browser diagnostic only; not comparable to visible GUIs",
    )
    run.add_argument(
        "--browser-executable", type=Path, help="use this Chromium executable for Plotly"
    )
    add_suite_options(run)
    report = sub.add_parser(
        "report", help="regenerate HTML, CSV and JSON summaries from raw measurements"
    )
    report.add_argument("path", type=Path)
    report.add_argument(
        "--probe", action="store_true", help="regenerate a receiver-only backend probe report"
    )
    demo = sub.add_parser("demo", help="launch a frontend and start a source if needed")
    demo.add_argument("frontend", choices=FRONTENDS)
    demo.add_argument("--mode", choices=("stream", "replay"), default="stream")
    demo.add_argument("--url", default="http://127.0.0.1:8765")
    demo.add_argument(
        "--browser-executable", type=Path, help="use this Chromium executable for Plotly"
    )
    demo.add_argument(
        "--backend",
        choices=BACKENDS,
        default=DEFAULT_BACKEND,
        help="source to start or require when connecting (default: rust)",
    )
    probe = sub.add_parser("probe", help="measure source and WebSocket delivery without plotting")
    probe.add_argument("--suite", type=Path, default=Path("scenarios/backend-probe.json"))
    probe.add_argument("--backends", nargs="+", choices=BACKENDS)
    probe.add_argument("--limit", type=int, help="limit expanded cases before repetitions/backends")
    probe.add_argument("--output", type=Path)
    add_suite_options(probe)
    matrix = sub.add_parser("matrix", help="open the local suite editor and export benchmark JSON")
    matrix.add_argument("--suite", type=Path, default=Path("scenarios/smoke.json"))
    matrix.add_argument(
        "--port", type=int, default=0, help="loopback port (default: choose a free port)"
    )
    matrix.add_argument(
        "--no-open", action="store_true", help="print the URL without opening a browser"
    )
    sub.add_parser("tui", help="interactive launcher for sources, setup, suites and the editor")
    doctor = sub.add_parser("doctor", help="check selected dependencies, builds and desktop access")
    doctor.add_argument("--frontends", nargs="+", choices=FRONTENDS)
    doctor.add_argument("--backends", nargs="+", choices=BACKENDS)
    doctor.add_argument("--browser-executable", type=Path)
    doctor.add_argument("--headless", action="store_true", help="check a Plotly diagnostic runtime")
    doctor.add_argument("--json", action="store_true", help="emit machine-readable check results")
    args = parser.parse_args()
    if args.command in ("run", "demo", "probe"):
        # A SIGTERM (from the TUI, a service manager or `kill`) must clean up the
        # child source and frontend exactly like Ctrl+C does.
        signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
    try:
        if args.command == "serve":
            config = Config(**(json.loads(args.config.read_text()) if args.config else {}))
            overrides = {
                key: getattr(args, key)
                for key in config.to_dict()
                if key != "generation" and getattr(args, key) is not None
            }
            if overrides:
                config = config.updated(overrides)
            if args.backend == "rust":
                from .backends import launch_rust_source

                launch_rust_source(config, args.output, args.host, args.port)
            else:
                from aiohttp import web

                from .server import Server

                web.run_app(Server(config, args.output).app(), host=args.host, port=args.port)
        elif args.command == "run":
            from .runner import run_suite

            run_suite(args)
        elif args.command == "report":
            if args.probe:
                from .probe import build_probe_report

                print(build_probe_report(args.path))
            else:
                from .report import build_report

                print(build_report(args.path))
        elif args.command == "demo":
            from .runner import launch_demo

            launch_demo(args)
        elif args.command == "probe":
            from .probe import run_probe_suite

            run_probe_suite(args)
        elif args.command == "matrix":
            from .matrix import serve_matrix

            serve_matrix(args)
        elif args.command == "tui":
            try:
                from .tui import run_tui
            except ImportError as exc:
                raise RuntimeError(
                    f"the TUI dependencies are unavailable; run ./scripts/setup core ({exc})"
                ) from exc
            run_tui()
        elif args.command == "doctor":
            from .runtime import doctor

            if not doctor(args):
                parser.exit(1)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        parser.exit(1, f"plotbench: {exc}\n")


if __name__ == "__main__":
    main()
