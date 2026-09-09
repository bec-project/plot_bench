"""Command-line entry points for the standalone benchmark."""

import argparse
import json
from datetime import datetime
from pathlib import Path

from .backends import BACKENDS
from .config import Config


def main():
    parser = argparse.ArgumentParser(description="Plotbench streaming and rendering benchmark")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="start the unified source and live controls")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--config", type=Path)
    serve.add_argument("--backend", choices=BACKENDS, default="python")
    serve.add_argument(
        "--output",
        type=Path,
        default=Path("results") / datetime.now().strftime("demo-%Y%m%d-%H%M%S"),
    )
    for name, default in Config().to_dict().items():
        if name != "generation":
            serve.add_argument("--" + name.replace("_", "-"), type=type(default), default=None)
    run = sub.add_parser("run", help="run a suite sequentially and generate a report")
    run.add_argument("--suite", type=Path, default=Path("scenarios/smoke.json"))
    run.add_argument("--frontends", nargs="+")
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
    run.add_argument("--dry-run", action="store_true")
    report = sub.add_parser(
        "report", help="regenerate HTML, CSV and JSON summaries from raw measurements"
    )
    report.add_argument("path", type=Path)
    report.add_argument(
        "--probe", action="store_true", help="regenerate a receiver-only backend probe report"
    )
    demo = sub.add_parser("demo", help="launch a frontend and start a source if needed")
    demo.add_argument(
        "frontend",
        choices=(
            "pyqtgraph",
            "pyqtgraph-gl",
            "matplotlib",
            "qtgraphs",
            "qtgraphs-cpp",
            "iced",
            "plotly",
        ),
    )
    demo.add_argument("--mode", choices=("stream", "replay"), default="stream")
    demo.add_argument("--url", default="http://127.0.0.1:8765")
    demo.add_argument(
        "--backend",
        choices=BACKENDS,
        help="source to start; when connecting, require this backend (default: use existing or Python)",
    )
    probe = sub.add_parser("probe", help="measure source and WebSocket delivery without plotting")
    probe.add_argument("--suite", type=Path, default=Path("scenarios/backend-probe.json"))
    probe.add_argument("--backends", nargs="+", choices=BACKENDS)
    probe.add_argument("--duration", type=float, help="override measured seconds per repetition")
    probe.add_argument("--warmup", type=float, help="override warmup seconds")
    probe.add_argument("--repetitions", type=int)
    probe.add_argument("--output", type=Path)
    probe.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
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
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        parser.exit(1, f"plotbench: {exc}\n")


if __name__ == "__main__":
    main()
