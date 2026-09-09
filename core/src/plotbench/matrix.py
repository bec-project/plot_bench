"""Loopback-only suite editor. Preview and export never start benchmark processes."""

import json
import math
import socket
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web

from .backends import BACKENDS, DEFAULT_BACKEND
from .config import Config
from .suites import FRONTENDS, MODES, load_suite, prepare_suite

ASSETS = Path(__file__).with_name("matrix_assets")
MAX_EDITOR_INTEGER = 2**53 - 1


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
            web.post("/api/preview", preview),
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
