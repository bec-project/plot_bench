"""Isolated visible Chromium process tree used for browser frontend measurements."""

import asyncio
import os
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlencode

from .browser_controller import BrowserController
from .client import frontend_parser, request
from .provenance import file_hash
from .runtime import BROWSER_FRONTENDS, ROOT, browser_launch_options, display_session


def completion_grace_seconds(duration):
    """Grace after the nominal duration for the page to finish, flush and signal completion.

    Keep the existing duration-scaled allowance for slow frontend telemetry flushes.
    Completion latency is recorded separately from measured adapter timings.
    """
    return 15 + 2 * duration


class BrowserCompletion:
    """Receive two frontend lifecycle notifications without evaluating page status in a loop."""

    def __init__(self, duration):
        self.duration = duration
        self.started = asyncio.Event()
        self.finished = asyncio.Event()
        self.state = None
        self.error = None
        self.started_at = None
        self.finished_at = None

    def notify(self, message):
        if self.finished.is_set():
            return
        if not isinstance(message, dict) or not isinstance(message.get("state"), dict):
            self.fail("Invalid browser lifecycle notification")
            return
        event, state = message.get("event"), message["state"]
        if event not in {"started", "stopped"}:
            self.fail("Unknown browser lifecycle event")
            return
        self.state = state
        if state.get("error") or state.get("metrics_error"):
            self.fail(str(state.get("error") or state["metrics_error"]))
            return
        if state.get("dropped_metrics", 0):
            self.fail("Browser telemetry lost samples")
            return
        if event == "started":
            submitted = state.get("submitted")
            if not isinstance(submitted, int) or isinstance(submitted, bool) or submitted <= 0:
                self.fail("Browser startup notification has no submitted frame")
                return
            self.started_at = time.monotonic()
            self.started.set()
        elif self.duration:
            self.finished_at = time.monotonic()
            self.started.set()
            self.finished.set()

    def completion_latency_seconds(self):
        """Seconds between the nominal end of the run and the flushed completion signal."""
        if self.started_at is None or self.finished_at is None or not self.duration:
            return None
        return self.finished_at - (self.started_at + self.duration)

    def fail(self, error):
        if not self.finished.is_set():
            self.error = str(error)
            self.started.set()
            self.finished.set()

    def closed(self):
        if self.finished.is_set():
            return
        if self.duration:
            self.fail("Browser closed before duration completion")
        else:
            # An interactive demo remains open after Stop and exits when its window closes.
            self.state = None
            self.started.set()
            self.finished.set()

    async def wait(self, *, startup_timeout=60, completion_grace=None):
        if completion_grace is None:
            completion_grace = completion_grace_seconds(self.duration)
        try:
            await asyncio.wait_for(self.started.wait(), timeout=startup_timeout)
        except TimeoutError as exc:
            raise RuntimeError("Browser frontend did not submit its first frame") from exc
        if self.error:
            raise RuntimeError(self.error)
        try:
            await asyncio.wait_for(
                self.finished.wait(),
                timeout=self.duration + completion_grace if self.duration else None,
            )
        except TimeoutError as exc:
            raise RuntimeError(
                "Browser frontend did not finish and flush after its duration "
                f"(grace {completion_grace:g} s after the nominal end)"
            ) from exc
        if self.error:
            raise RuntimeError(self.error)
        if self.duration and (
            not self.state
            or self.state.get("stop_reason") != "duration"
            or self.state.get("complete") is not True
            or self.state.get("running") is not False
            or not isinstance(self.state.get("submitted"), int)
            or isinstance(self.state.get("submitted"), bool)
            or self.state.get("submitted", 0) <= 0
        ):
            raise RuntimeError("Timed browser run was interrupted before duration completion")
        return self.state


async def run_unobserved_page(args, page_url, options, metadata):
    completion = BrowserCompletion(args.duration)
    metadata["completion_grace_seconds"] = completion_grace_seconds(args.duration)
    controller = await BrowserController.launch(completion, metadata)
    failure = None
    try:
        options = dict(options)
        options["executablePath"] = options.pop("executable_path")
        await controller.send(
            "start", options=options, width=args.width, height=args.height, url=page_url
        )
        state = await completion.wait()
        metadata["termination_reason"] = "duration" if args.duration else "user"
        metadata["completion_latency_seconds"] = completion.completion_latency_seconds()
        if state is not None:
            print(state, flush=True)
        if args.screenshot:
            await controller.call("screenshot", path=str(args.screenshot))
            metadata["qa_screenshot"] = True
    except Exception as exc:
        failure = exc
        raise
    finally:
        try:
            await controller.close()
        except Exception as exc:
            if failure is None:
                raise
            failure.add_note(f"Browser controller cleanup also failed: {exc}")


async def run_browser(args, page_url):
    from playwright.async_api import async_playwright

    metadata = {
        "headless": args.headless,
        "termination_reason": "error",
        "qa_screenshot_requested": args.screenshot is not None,
        "qa_screenshot": False,
        "qa_screenshot_stage": "after duration completion and final frontend telemetry flush",
        "automation_status_monitor": "exposed binding for first submission and flushed completion; no status polling",
        "resource_scope": "browser worker and all descendants, including Playwright driver and Chromium GPU process; excludes desktop compositor and source",
        "playwright_version": version("playwright"),
        "display_session": display_session(),
    }
    failure = None
    try:
        async with async_playwright() as playwright:
            options = browser_launch_options(
                browser_executable=getattr(args, "browser_executable", None), headless=args.headless
            )
            metadata["browser_selection"] = (
                "custom" if options.get("executable_path") else "bundled"
            )
            metadata["browser_executable"] = (
                options.get("executable_path") or playwright.chromium.executable_path
            )
            # Pin the checked executable in both modes. Otherwise Playwright silently
            # selects its separate headless-shell binary for a headless bundled launch.
            options["executable_path"] = metadata["browser_executable"]
            metadata["browser_executable_sha256"] = file_hash(metadata["browser_executable"])
            metadata["browser_launch_arguments"] = options.get("args", [])
            metadata["display_protocol_requested"] = (
                "headless" if args.headless else ("wayland" if options.get("args") else "native")
            )
        # End the temporary Python Playwright connection before starting the Node
        # controller. Only that in-process API can disable its original CDP session.
        await run_unobserved_page(args, page_url, options, metadata)
    except Exception as exc:
        failure = exc
        metadata["termination_reason"] = "error"
        metadata["browser_worker_error"] = str(exc)
        raise
    finally:
        try:
            await asyncio.to_thread(
                request,
                args.url + "/api/metrics",
                {
                    "frontend": getattr(args, "frontend", "plotly"),
                    "mode": args.mode,
                    "run_id": args.run_id,
                    "samples": [],
                    "metadata": metadata,
                },
            )
        except Exception as exc:
            if failure is None:
                raise
            failure.add_note(f"Final browser telemetry export also failed: {exc}")


def main():
    parser = frontend_parser("Run a production frontend in an isolated browser")
    parser.add_argument("--frontend", choices=BROWSER_FRONTENDS, default="plotly")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--browser-executable", type=Path, help="native Chromium/Chrome executable")
    args = parser.parse_args()
    if args.screenshot and not args.duration:
        parser.error(
            "--screenshot requires a positive --duration; previews are captured after completion"
        )
    dist = ROOT / f"frontends/{args.frontend}/dist"
    if not (dist / "index.html").exists():
        raise RuntimeError(f"{args.frontend} build missing; run ./scripts/setup {args.frontend}")
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache/playwright"))
    server = ThreadingHTTPServer(
        ("127.0.0.1", 5173 if args.interactive else 0),
        partial(SimpleHTTPRequestHandler, directory=str(dist)),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    query = urlencode(
        dict(
            url=args.url,
            mode=args.mode,
            run_id=args.run_id,
            duration=args.duration,
            width=args.width,
            height=args.height,
        )
    )
    try:
        asyncio.run(run_browser(args, f"http://127.0.0.1:{server.server_port}/?{query}"))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
