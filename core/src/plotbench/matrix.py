"""Loopback-only suite editor. Preview, save and export never start benchmark processes."""

import json
import math
import re
import socket
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web

from .backends import BACKENDS, DEFAULT_BACKEND
from .config import Config
from .suites import BASELINE_FILENAME, FRONTENDS, MODES, load_suite, prepare_suite

ASSETS = Path(__file__).with_name("matrix_assets")
ROOT = Path(__file__).resolve().parents[3]
SCENARIOS_DIR = ROOT / "scenarios"
CUSTOM_DIR = ROOT / "scenarios_custom"
MAX_EDITOR_INTEGER = 2**53 - 1
SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name):
    """Reduce a requested file name to a safe, traversal-proof stem."""
    return SLUG_RE.sub("-", str(name).strip().lower()).strip("-")


def preset_kind(suite):
    """Suites without frontends or modes are receiver-only probe campaigns."""
    return "run" if suite.get("frontends") or suite.get("modes") else "probe"


def preset_entry(path, source):
    """Summarize one scenario file for the editor gallery; never raises."""
    directory = "scenarios_custom" if source == "custom" else "scenarios"
    # Official status derives from location alone: an edited copy saved to
    # scenarios_custom is never the published baseline, whatever it is called.
    entry = dict(
        filename=path.name,
        path=f"{directory}/{path.name}",
        source=source,
        official=source == "bundled" and path.name == BASELINE_FILENAME,
    )
    try:
        suite = json.loads(path.read_text())
        kind = preset_kind(suite)
        data = prepare_suite(suite, kind=kind).to_dict()
        entry.update(
            name=suite.get("name", path.stem),
            description=suite.get("description", ""),
            kind=kind,
            case_count=data["case_count"],
            run_count=data["run_count"],
            minimum_minutes=data["estimate"]["minimum_seconds"] / 60,
            suite=suite,
        )
    except (ValueError, OSError, UnicodeError) as exc:
        entry.update(
            name=path.stem,
            description="",
            kind="run",
            case_count=0,
            run_count=0,
            minimum_minutes=0.0,
            suite={},
            error=str(exc),
        )
    return entry


def run_commands(relative_path, kind, slug):
    """Copy-ready terminal commands for the saved suite. The editor never runs them."""
    command = "run" if kind == "run" else "probe"
    return dict(
        dry_run=f"./scripts/plotbench {command} --suite {relative_path} --dry-run",
        quick_check=(
            f"./scripts/plotbench {command} --suite {relative_path} "
            "--warmup 1 --duration 3 --repetitions 1 --output results/quick-check"
        ),
        full=f"./scripts/plotbench {command} --suite {relative_path} --output results/{slug}",
    )


def validate_editor_numbers(value, path="suite"):
    """The CLI accepts large integers; browser Numbers cannot preserve them."""
    if isinstance(value, dict):
        for key, item in value.items():
            validate_editor_numbers(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_editor_numbers(item, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path}: editor numbers must be finite")
    elif isinstance(value, (int, float)) and abs(value) > MAX_EDITOR_INTEGER:
        raise ValueError(
            f"{path}: the editor supports numbers only between "
            f"{-MAX_EDITOR_INTEGER} and {MAX_EDITOR_INTEGER} to avoid rounding. "
            "Use the CLI for larger integer seeds."
        )


@web.middleware
async def local_requests(request, handler):
    if urlsplit("//" + request.host).hostname not in ("127.0.0.1", "localhost"):
        raise web.HTTPForbidden(text="The matrix editor accepts loopback requests only.")
    origin = request.headers.get("Origin")
    if origin is not None and origin != f"{request.scheme}://{request.host}":
        raise web.HTTPForbidden(text="The matrix editor accepts same-origin requests only.")
    response = await handler(request)
    response.headers.update(
        {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
            ),
        }
    )
    return response


def create_app(suite):
    prepare_suite(suite)
    validate_editor_numbers(suite)
    app = web.Application(middlewares=[local_requests], client_max_size=1024 * 1024)

    async def initial(request):
        return web.json_response(
            dict(
                suite=suite,
                frontends=FRONTENDS,
                backends=BACKENDS,
                default_backend=DEFAULT_BACKEND,
                modes=MODES,
                config=Config().to_dict(),
            )
        )

    async def preview(request):
        if request.content_type != "application/json":
            raise web.HTTPUnsupportedMediaType(text="Send suite JSON as application/json.")
        try:
            body = await request.json()
            if (
                not isinstance(body, dict)
                or set(body) - {"suite", "suite_json", "kind"}
                or ("suite" in body) == ("suite_json" in body)
            ):
                raise ValueError("request: expected either suite or suite_json, and optional kind")
            if "suite_json" in body:
                if not isinstance(body["suite_json"], str):
                    raise ValueError("suite_json: must be JSON text")
                candidate = json.loads(body["suite_json"])
            else:
                candidate = body["suite"]
            plan = prepare_suite(candidate, kind=body.get("kind", "run"))
            validate_editor_numbers(candidate)
            payload = plan.to_dict()
        except (ValueError, UnicodeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(payload, dumps=lambda value: json.dumps(value, allow_nan=False))

    async def environment(request):
        """A fast, filesystem-only probe of which components are installed."""
        from .runtime import component_installed, setup_component

        frontends = {
            name: {"installed": component_installed(name), "setup": setup_component(name)}
            for name in FRONTENDS
        }
        backends = {
            name: {
                "installed": component_installed(name),
                "setup": None if name == "python" else name,
            }
            for name in BACKENDS
        }
        return web.json_response(dict(frontends=frontends, backends=backends))

    async def presets(request):
        items = []
        for directory, source in ((SCENARIOS_DIR, "bundled"), (CUSTOM_DIR, "custom")):
            if directory.is_dir():
                entries = [preset_entry(path, source) for path in sorted(directory.glob("*.json"))]
                items.extend(sorted(entries, key=lambda entry: not entry["official"]))
        return web.json_response(dict(presets=items))

    async def save(request):
        """Write a validated suite to scenarios_custom. Writing JSON is not a run."""
        if request.content_type != "application/json":
            raise web.HTTPUnsupportedMediaType(text="Send suite JSON as application/json.")
        try:
            body = await request.json()
            if not isinstance(body, dict) or set(body) - {"suite", "filename", "kind"}:
                raise ValueError("request: expected suite, filename and optional kind")
            if not isinstance(body.get("filename"), str):
                raise ValueError("filename: must be text")
            slug = slugify(body["filename"])
            if not slug:
                raise ValueError("filename: use letters, digits or hyphens")
            if len(slug) > 100:
                raise ValueError("filename: at most 100 characters after simplification")
            kind = body.get("kind", "run")
            plan = prepare_suite(body.get("suite"), kind=kind)
            validate_editor_numbers(body.get("suite"))
            target = (CUSTOM_DIR / f"{slug}.json").resolve()
            if target.parent != CUSTOM_DIR.resolve():
                raise ValueError("filename: refusing to write outside scenarios_custom")
            CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(plan.suite, indent=2) + "\n")
            data = plan.to_dict()
            relative = f"scenarios_custom/{slug}.json"
            payload = dict(
                path=relative,
                name=slug,
                run_count=data["run_count"],
                minimum_minutes=data["estimate"]["minimum_seconds"] / 60,
                commands=run_commands(relative, kind, slug),
            )
        except (ValueError, UnicodeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(payload, dumps=lambda value: json.dumps(value, allow_nan=False))

    async def asset(request):
        name = request.match_info.get("name", "index.html")
        if name not in ("index.html", "editor.js", "style.css"):
            raise web.HTTPNotFound()
        return web.FileResponse(ASSETS / name)

    app.add_routes(
        [
            web.get("/", asset),
            web.get("/{name:index.html|editor.js|style.css}", asset),
            web.get("/api/initial", initial),
            web.get("/api/environment", environment),
            web.get("/api/presets", presets),
            web.post("/api/preview", preview),
            web.post("/api/save", save),
        ]
    )
    return app


def serve_matrix(args):
    if not 0 <= args.port <= 65535:
        raise ValueError("port: must be between 0 and 65535")
    app = create_app(load_suite(args.suite))
    listener = socket.socket()
    try:
        listener.bind(("127.0.0.1", args.port))
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"

        def ready(message):
            print(
                f"Matrix editor: {url}\nExport a suite, then run it with the CLI. Stop with Ctrl+C.",
                flush=True,
            )
            if not args.no_open:
                webbrowser.open(url)

        # aiohttp calls this after the socket starts listening, before opening the browser.
        web.run_app(app, sock=listener, print=ready)
    finally:
        listener.close()
