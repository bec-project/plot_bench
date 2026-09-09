"""The migrated source controls page: a self-contained single file plus opt-in QA."""

import asyncio
import os
import re
from pathlib import Path

import pytest
from aiohttp.test_utils import TestServer

from plotbench.config import Config
from plotbench.server import Server

CONTROLS = Path(__file__).parents[1] / "src/plotbench/controls.html"


def test_controls_page_is_a_self_contained_single_file():
    html = CONTROLS.read_text()
    assert html.lstrip().startswith("<!doctype html>")
    # Both the Python and Rust sources serve only this one file at "/", so it must
    # carry no external script or stylesheet references.
    assert not re.search(r"<script[^>]+\bsrc=", html), "controls page must inline its script"
    assert not re.search(r"<link[^>]+\bhref=", html), "controls page must inline its styles"
    assert "Source controls" in html
    assert "/api/config" in html and "/api/health" in html


@pytest.mark.skipif(
    not os.environ.get("PLOTBENCH_TEST_BROWSER"), reason="explicit QA browser required"
)
def test_source_controls_apply_preset_and_live_status(tmp_path):
    from playwright.async_api import async_playwright, expect

    async def exercise():
        app = Server(Config(), tmp_path / "out").app()
        async with TestServer(app) as server:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=True, executable_path=os.environ["PLOTBENCH_TEST_BROWSER"]
                )
                page = await browser.new_page(viewport={"width": 1200, "height": 1200})
                errors = []
                page.on("pageerror", lambda failure: errors.append(str(failure)))
                await page.goto(str(server.make_url("/")))

                await expect(page.locator(".backend-badge")).to_contain_text("Python")
                await expect(page.get_by_label("Target rate", exact=True)).to_have_value("30")
                await expect(page.locator(".stat").filter(has_text="Status")).to_contain_text("OK")

                # View switches the visible field groups.
                await page.get_by_role("button", name="waveform", exact=True).click()
                await expect(page.locator(".config-group > legend")).to_have_count(2)
                await page.get_by_role("button", name="both", exact=True).click()
                await expect(page.locator(".config-group > legend")).to_have_count(3)

                apply = page.get_by_role("button", name="Apply workload")
                await expect(apply).to_be_disabled()

                # Edit one field: only that change is applied to the live source.
                await page.get_by_label("Target rate", exact=True).fill("90")
                await expect(apply).to_be_enabled()
                await apply.click()
                await expect(apply).to_be_disabled()
                applied = await page.evaluate("() => fetch('/api/config').then(r => r.json())")
                assert applied["hz"] == 90
                assert applied["points"] == 10000  # untouched field unchanged

                # A resolution preset fills width and height together.
                await page.get_by_label("Image resolution preset", exact=True).select_option(
                    "1024x1024"
                )
                await expect(page.get_by_label("Image width", exact=True)).to_have_value("1024")
                await expect(page.get_by_label("Image height", exact=True)).to_have_value("1024")
                await apply.click()
                await expect(apply).to_be_disabled()
                applied = await page.evaluate("() => fetch('/api/config').then(r => r.json())")
                assert applied["width"] == applied["height"] == 1024

                # Option tooltips are present.
                assert await page.locator(".infotip").count() > 0
                assert not errors, errors
                await browser.close()

    asyncio.run(exercise())
