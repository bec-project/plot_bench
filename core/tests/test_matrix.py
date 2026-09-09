"""Real loopback HTTP tests for the pure suite-preview editor."""

import asyncio
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from plotbench.matrix import create_app
from plotbench.suites import prepare_suite


def suite():
    return dict(
        name="<script>alert(1)</script>",
        cases=[dict(name="wave", config={})],
        frontends=["pyqtgraph"],
        backends=["python"],
        modes=["stream"],
        repetitions=1,
    )


def test_editor_load_preview_export_round_trip_and_static_assets():
    async def exercise():
        original = suite()
        async with TestClient(TestServer(create_app(original))) as client:
            for asset in ("/", "/editor.js", "/style.css"):
                response = await client.get(asset)
                assert response.status == 200
                assert "script-src 'self'" in response.headers["Content-Security-Policy"]
                assert "<script>alert(1)</script>" not in await response.text()
            response = await client.get("/api/initial")
            initial = await response.json()
            assert initial["suite"] == original
            assert initial["default_backend"] == "rust"
            for kind in ("run", "probe"):
                response = await client.post("/api/preview", json={"suite": original, "kind": kind})
                assert response.status == 200
                preview = await response.json()
                assert preview == prepare_suite(original, kind=kind).to_dict()
                exported = json.loads(json.dumps(preview["suite"]))
                assert prepare_suite(exported, kind=kind).to_dict() == preview
            assert (await client.get("/api/run")).status == 404
            assert (await client.get("/../cli.py")).status == 404

    asyncio.run(exercise())


def test_editor_errors_are_field_specific_and_do_not_mutate_original():
    async def exercise():
        original = suite()
        async with TestClient(TestServer(create_app(original))) as client:
            invalid = dict(original, repetitions=1.5)
            response = await client.post("/api/preview", json={"suite": invalid})
            assert response.status == 400
            assert "repetitions" in (await response.json())["error"]
            response = await client.post(
                "/api/preview", json={"suite": original, "kind": "unknown"}
            )
            assert response.status == 400
            response = await client.post(
                "/api/preview", data="not JSON", headers={"Content-Type": "application/json"}
            )
            assert response.status == 400
            response = await client.post("/api/preview", json=[original])
            assert response.status == 400
            response = await client.get("/api/initial")
            assert (await response.json())["suite"] == original

    asyncio.run(exercise())


def test_editor_rejects_cross_origin_requests_and_non_json_posts():
    async def exercise():
        async with TestClient(TestServer(create_app(suite()))) as client:
            response = await client.post(
                "/api/preview", json={"suite": suite()}, headers={"Origin": "https://example.org"}
            )
            assert response.status == 403
            response = await client.get("/", headers={"Host": "example.org"})
            assert response.status == 403
            response = await client.post("/api/preview", data="{}")
            assert response.status == 415

    asyncio.run(exercise())


@pytest.mark.parametrize("field", ["order_seed", "seed"])
def test_initial_suite_rejects_integers_that_the_browser_cannot_preserve(field):
    original = suite()
    target = original if field == "order_seed" else original["cases"][0]["config"]
    target[field] = 9007199254740993
    with pytest.raises(ValueError, match="Use the CLI for larger integer seeds"):
        create_app(original)


def test_raw_import_validates_original_number_tokens_and_keeps_original_on_error():
    async def exercise():
        original = suite()
        async with TestClient(TestServer(create_app(original))) as client:
            for field in ("order_seed", "seed"):
                for token, message in (
                    ("9007199254740993", "Use the CLI for larger integer seeds"),
                    ("1.0000000000000001", "must be an integer"),
                    ("1e0", "must be an integer"),
                ):
                    candidate = suite()
                    target = candidate if field == "order_seed" else candidate["cases"][0]["config"]
                    target[field] = "TOKEN"
                    raw = json.dumps(candidate).replace('"TOKEN"', token)
                    response = await client.post("/api/preview", json={"suite_json": raw})
                    assert response.status == 400
                    assert message in (await response.json())["error"]
            valid = dict(original, order_seed=9007199254740991)
            response = await client.post("/api/preview", json={"suite_json": json.dumps(valid)})
            assert response.status == 200
            assert (await response.json())["suite"] == valid
            assert (await (await client.get("/api/initial")).json())["suite"] == original

    asyncio.run(exercise())


def test_preview_handles_overflow_and_unused_probe_selections():
    async def exercise():
        async with TestClient(TestServer(create_app(suite()))) as client:
            response = await client.post(
                "/api/preview", json={"suite": dict(suite(), measurement_seconds=1e308)}
            )
            assert response.status == 400
            assert "derived schedule durations" in (await response.json())["error"]
            response = await client.post(
                "/api/preview",
                json={"suite": dict(suite(), frontends=float("nan")), "kind": "probe"},
            )
            assert response.status == 400
            assert "must be finite" in (await response.json())["error"]
            response = await client.post(
                "/api/preview",
                json={"suite": dict(suite(), frontends=[], modes=[]), "kind": "probe"},
            )
            assert response.status == 200
            preview = await response.json()
            assert preview["run_count"] == 1
            assert preview["selected_frontends"] == preview["selected_modes"] == []

    asyncio.run(exercise())
