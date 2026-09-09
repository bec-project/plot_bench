"""Opt-in browser QA: PLOTBENCH_TEST_BROWSER=/path/to/chromium pytest this file."""

import asyncio
import json
import os
from pathlib import Path

import pytest
from aiohttp.test_utils import TestServer

from plotbench.matrix import create_app


@pytest.mark.skipif(
    not os.environ.get("PLOTBENCH_TEST_BROWSER"), reason="explicit QA browser required"
)
def test_matrix_forms_validation_preview_export_and_mobile_layout(tmp_path):
    from playwright.async_api import async_playwright, expect

    async def exercise():
        suite = dict(
            name="Matrix QA",
            cases=[dict(name="wave", config={"view": "waveform"})],
            frontends=["pyqtgraph"],
            modes=["stream"],
            backends=["python"],
            repetitions=1,
        )
        async with TestServer(create_app(suite)) as server:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=True, executable_path=os.environ["PLOTBENCH_TEST_BROWSER"]
                )
                page = await browser.new_page(viewport={"width": 1280, "height": 1000})
                errors = []
                page.on("pageerror", lambda failure: errors.append(str(failure)))
                await page.goto(str(server.make_url("/")))
                await expect(page.locator("#summary")).to_contain_text("1 workloads")
                await page.get_by_role("button", name="Add workload", exact=True).click()
                await page.locator("#cases article").nth(1).get_by_label(
                    "Target rate (Hz)", exact=True
                ).fill("60")
                await page.get_by_role("button", name="Add group", exact=True).click()
                group = page.locator("#groups article").first
                await group.get_by_role("button", name="Add matrix axis", exact=True).click()
                await group.get_by_label("Matrix field", exact=True).nth(1).select_option("points")
                await group.get_by_label("Matrix points values", exact=True).fill("1000, 2000")
                await expect(page.locator("#summary")).to_contain_text("6 workloads")
                for label, value in (
                    ("Warmup (seconds)", "0"),
                    ("Measured (seconds)", "2"),
                    ("Cooldown (seconds)", "0"),
                    ("Repetitions", "2"),
                ):
                    await page.get_by_label(label, exact=True).fill(value)
                await expect(page.locator("#summary")).to_contain_text("12 runs")
                async with page.expect_download() as download_info:
                    await page.get_by_role("button", name="Export suite JSON", exact=True).click()
                download = await download_info.value
                exported = json.loads(Path(await download.path()).read_text())
                assert exported["case_groups"][0]["matrix"]["points"] == [1000, 2000]
                assert exported["measurement_seconds"] == 2
                assert exported["warmup_seconds"] == exported["cooldown_seconds"] == 0
                await page.get_by_label("Repetitions", exact=True).fill("1.5")
                await expect(page.locator("#error")).to_contain_text("repetitions")
                await expect(page.locator("#export")).to_be_disabled()
                await page.get_by_label("Repetitions", exact=True).fill("2")
                await expect(page.locator("#export")).to_be_enabled()
                await page.locator("#kind").select_option("probe")
                await expect(page.locator("#command")).to_contain_text("probe")
                await expect(page.locator("#selections fieldset input").first).to_be_disabled()
                await page.locator("#import").set_input_files(
                    {
                        "name": "bad.json",
                        "mimeType": "application/json",
                        "buffer": b'{"invalid":true}',
                    }
                )
                await expect(page.locator("#error")).to_contain_text("unknown fields")
                await expect(page.locator("#export")).to_be_disabled()
                await page.locator("#raw").fill(json.dumps(exported))
                await page.get_by_role("button", name="Apply JSON", exact=True).click()
                await expect(page.locator("#export")).to_be_enabled()
                await page.locator("#advanced").evaluate("element => element.open = false")
                await page.screenshot(path=str(tmp_path / "matrix-desktop.png"), full_page=True)
                await page.set_viewport_size({"width": 390, "height": 844})
                await page.screenshot(path=str(tmp_path / "matrix-mobile.png"), full_page=True)
                assert await page.evaluate(
                    "() => document.documentElement.scrollWidth <= innerWidth"
                )
                assert not errors, errors
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.skipif(
    not os.environ.get("PLOTBENCH_TEST_BROWSER"), reason="explicit QA browser required"
)
def test_editor_defaults_to_rust_for_run_and_probe_and_preserves_python_selection():
    from playwright.async_api import async_playwright, expect

    async def exercise():
        suite = dict(
            cases=[dict(name="wave", config={"view": "waveform"})],
            frontends=["pyqtgraph"],
            modes=["stream"],
            repetitions=1,
        )
        async with TestServer(create_app(suite)) as server:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=True, executable_path=os.environ["PLOTBENCH_TEST_BROWSER"]
                )
                page = await browser.new_page()
                await page.goto(str(server.make_url("/")))
                source_cell = page.locator("#jobs tr").first.locator("td").nth(3)
                await expect(page.locator("#export")).to_be_enabled()
                for kind in ("run", "probe"):
                    await page.locator("#kind").select_option(kind)
                    await expect(page.locator("#export")).to_be_enabled()
                    await expect(page.get_by_label("rust", exact=True)).to_be_checked()
                    await expect(page.get_by_label("python", exact=True)).not_to_be_checked()
                    await expect(page.locator("#jobs tr")).to_have_count(1)
                    await expect(source_cell).to_have_text("rust")
                    await expect(page.locator("#command")).to_contain_text(f"{kind} --suite")
                    assert json.loads(await page.locator("#raw").input_value()) == suite

                await page.get_by_label("python", exact=True).check()
                await page.get_by_label("rust", exact=True).uncheck()
                await expect(page.locator("#export")).to_be_enabled()
                await expect(page.locator("#jobs tr")).to_have_count(1)
                await expect(source_cell).to_have_text("python")
                async with page.expect_download() as download_info:
                    await page.get_by_role("button", name="Export suite JSON", exact=True).click()
                download = await download_info.value
                exported = json.loads(Path(await download.path()).read_text())
                assert exported == dict(suite, backends=["python"])
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.skipif(
    not os.environ.get("PLOTBENCH_TEST_BROWSER"), reason="explicit QA browser required"
)
def test_editor_rejects_seed_rounding_and_recovers_probe_with_no_frontends():
    from playwright.async_api import async_playwright, expect

    async def exercise():
        suite = dict(
            cases=[dict(name="wave", config={})],
            frontends=["pyqtgraph"],
            modes=["stream"],
            backends=["python"],
            repetitions=1,
        )
        async with TestServer(create_app(suite)) as server:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=True, executable_path=os.environ["PLOTBENCH_TEST_BROWSER"]
                )
                page = await browser.new_page()
                await page.goto(str(server.make_url("/")))
                await expect(page.locator("#export")).to_be_enabled()
                for label in ("Data seed", "Run order seed"):
                    await page.get_by_label(label, exact=True).fill("9007199254740993")
                    await expect(page.locator("#error")).to_contain_text("avoid rounding")
                    await expect(page.locator("#export")).to_be_disabled()
                    assert "9007199254740993" in await page.locator("#raw").input_value()
                    assert "9007199254740992" not in await page.locator("#raw").input_value()
                    await page.get_by_label(label, exact=True).fill("42")
                    await expect(page.locator("#export")).to_be_enabled()

                await page.locator("#advanced").evaluate("element => element.open = true")
                for token, message in (
                    ("9007199254740993", "Use the CLI for larger integer seeds"),
                    ("1.0000000000000001", "must be an integer"),
                    ("1e0", "must be an integer"),
                ):
                    raw = json.dumps(dict(suite, order_seed="TOKEN")).replace('"TOKEN"', token)
                    await page.locator("#raw").fill(raw)
                    await page.get_by_role("button", name="Apply JSON", exact=True).click()
                    await expect(page.locator("#error")).to_contain_text(message)
                    await expect(page.locator("#export")).to_be_disabled()
                    assert await page.locator("#raw").input_value() == raw
                    assert await page.locator("#command").text_content() == ""

                await page.locator("#raw").fill(json.dumps(suite))
                await page.get_by_role("button", name="Apply JSON", exact=True).click()
                await expect(page.locator("#export")).to_be_enabled()
                await page.get_by_label("pyqtgraph", exact=True).uncheck()
                await page.get_by_label("stream", exact=True).uncheck()
                await expect(page.locator("#export")).to_be_disabled()
                await page.locator("#kind").select_option("probe")
                await expect(page.locator("#export")).to_be_enabled()
                await expect(page.locator("#summary")).to_contain_text("1 runs")
                await expect(page.get_by_label("pyqtgraph", exact=True)).to_be_disabled()
                async with page.expect_download() as download_info:
                    await page.get_by_role("button", name="Export suite JSON", exact=True).click()
                download = await download_info.value
                exported = json.loads(Path(await download.path()).read_text())
                assert exported["frontends"] == exported["modes"] == []
                await browser.close()

    asyncio.run(exercise())
