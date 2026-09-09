"""Opt-in browser QA: PLOTBENCH_TEST_BROWSER=/path/to/chromium pytest this file."""

import asyncio
import json
import os
from pathlib import Path

import pytest
from aiohttp.test_utils import TestServer

from plotbench import matrix
from plotbench.matrix import create_app


@pytest.mark.skipif(
    not os.environ.get("PLOTBENCH_TEST_BROWSER"), reason="explicit QA browser required"
)
def test_matrix_build_preview_export_save_and_mobile_layout(tmp_path):
    from playwright.async_api import async_playwright, expect

    original_custom = matrix.CUSTOM_DIR
    matrix.CUSTOM_DIR = tmp_path / "scenarios_custom"

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
                await expect(page.locator("#plan-summary")).to_contain_text("1 workloads")
                # The live command reflects the current config and its pending save path.
                await expect(page.locator(".run-here")).to_contain_text("save it first")
                await expect(page.locator(".run-here")).to_contain_text(
                    "scenarios_custom/my-suite.json --dry-run"
                )

                await page.get_by_role("button", name="+ Add workload", exact=True).click()
                await page.locator("#cases article").nth(1).get_by_label(
                    "Target rate", exact=True
                ).fill("60")
                await page.get_by_role("button", name="+ Add group", exact=True).click()
                # The default group already varies points across two values → four workloads.
                await expect(page.locator("#plan-summary")).to_contain_text("4 workloads")
                group = page.locator("#groups article").first
                await group.get_by_label("Matrix points values", exact=True).fill(
                    "1000, 2000, 3000"
                )
                await expect(page.locator("#plan-summary")).to_contain_text("5 workloads")

                for label, value in (("Warmup", "0"), ("Measured", "2"), ("Cooldown", "0")):
                    await page.get_by_label(label, exact=True).fill(value)
                await page.get_by_label("Repetitions", exact=True).fill("2")
                await expect(page.locator("#plan-summary")).to_contain_text("10 runs")

                async with page.expect_download() as download_info:
                    await page.get_by_role("button", name="Export JSON", exact=True).click()
                download = await download_info.value
                exported = json.loads(Path(await download.path()).read_text())
                assert exported["case_groups"][0]["matrix"]["points"] == [1000, 2000, 3000]
                assert exported["measurement_seconds"] == 2
                assert exported["warmup_seconds"] == exported["cooldown_seconds"] == 0

                # Invalid input blocks preview, export and save.
                await page.get_by_label("Repetitions", exact=True).fill("1.5")
                await expect(page.locator("#plan-error")).to_contain_text("repetitions")
                await expect(
                    page.get_by_role("button", name="Export JSON", exact=True)
                ).to_be_disabled()
                await expect(
                    page.get_by_role("button", name="Save to scenarios_custom", exact=True)
                ).to_be_disabled()
                await page.get_by_label("Repetitions", exact=True).fill("2")
                await expect(
                    page.get_by_role("button", name="Export JSON", exact=True)
                ).to_be_enabled()

                # Save writes the validated suite into scenarios_custom and shows the launcher.
                await page.get_by_label("File name", exact=True).fill("qa suite")
                await page.get_by_role(
                    "button", name="Save to scenarios_custom", exact=True
                ).click()
                await expect(page.locator(".launcher")).to_contain_text(
                    "scenarios_custom/qa-suite.json"
                )
                await expect(page.locator(".launcher")).to_contain_text("--dry-run")
                saved = json.loads((matrix.CUSTOM_DIR / "qa-suite.json").read_text())
                assert saved["case_groups"][0]["matrix"]["points"] == [1000, 2000, 3000]
                # The saved suite appears in the collapsible custom box, and the live
                # command now targets the saved file with no "save first" note.
                await expect(page.locator(".custom-box")).to_contain_text("Matrix QA")
                await expect(page.locator(".run-here")).to_contain_text(
                    "scenarios_custom/qa-suite.json"
                )
                await expect(page.locator(".run-here")).not_to_contain_text("save it first")

                # Switching to probe disables the ignored frontend selection.
                await page.locator("#kind").select_option("probe")
                await expect(page.get_by_label("pyqtgraph", exact=True)).to_be_disabled()
                await expect(
                    page.get_by_role("button", name="Export JSON", exact=True)
                ).to_be_enabled()

                await page.screenshot(path=str(tmp_path / "matrix-desktop.png"), full_page=True)
                await page.set_viewport_size({"width": 390, "height": 844})
                await page.screenshot(path=str(tmp_path / "matrix-mobile.png"), full_page=True)
                assert await page.evaluate(
                    "() => document.documentElement.scrollWidth <= innerWidth"
                )
                assert not errors, errors
                await browser.close()

    try:
        asyncio.run(exercise())
    finally:
        matrix.CUSTOM_DIR = original_custom


@pytest.mark.skipif(
    not os.environ.get("PLOTBENCH_TEST_BROWSER"), reason="explicit QA browser required"
)
def test_editor_defaults_to_rust_and_preserves_python_selection():
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
                source_cell = page.locator("table tbody tr").first.locator("td").nth(3)
                await expect(
                    page.get_by_role("button", name="Export JSON", exact=True)
                ).to_be_enabled()
                for kind in ("run", "probe"):
                    await page.locator("#kind").select_option(kind)
                    await expect(page.get_by_label("rust", exact=True)).to_be_checked()
                    await expect(page.get_by_label("python", exact=True)).not_to_be_checked()
                    await expect(page.locator("table tbody tr")).to_have_count(1)
                    await expect(source_cell).to_have_text("rust")

                await page.locator("#kind").select_option("run")
                await page.get_by_label("python", exact=True).check()
                await page.get_by_label("rust", exact=True).uncheck()
                await expect(source_cell).to_have_text("python")
                async with page.expect_download() as download_info:
                    await page.get_by_role("button", name="Export JSON", exact=True).click()
                download = await download_info.value
                exported = json.loads(Path(await download.path()).read_text())
                assert exported["backends"] == ["python"]
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.skipif(
    not os.environ.get("PLOTBENCH_TEST_BROWSER"), reason="explicit QA browser required"
)
def test_editor_rejects_seed_rounding_and_recovers_probe_with_no_frontends():
    from playwright.async_api import async_playwright, expect

    async def exercise():
        suite = dict(
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
                page = await browser.new_page()
                await page.goto(str(server.make_url("/")))
                await expect(
                    page.get_by_role("button", name="Export JSON", exact=True)
                ).to_be_enabled()

                # A number the browser cannot hold exactly is kept raw, never rounded.
                seed = page.get_by_label("Data seed", exact=True)
                await seed.fill("9007199254740993")
                await expect(page.locator(".field-error").first).to_contain_text("Too large")
                await expect(
                    page.get_by_role("button", name="Export JSON", exact=True)
                ).to_be_disabled()
                raw = await page.locator("#raw").input_value()
                assert "9007199254740993" in raw and "9007199254740992" not in raw
                await seed.fill("42")
                await expect(
                    page.get_by_role("button", name="Export JSON", exact=True)
                ).to_be_enabled()

                # Raw JSON is validated by Python; a bad token is reported and not applied.
                await page.locator("#advanced").evaluate("element => (element.open = true)")
                bad = json.dumps(dict(suite, order_seed="TOKEN")).replace('"TOKEN"', "1e0")
                await page.locator("#raw").fill(bad)
                await page.get_by_role("button", name="Apply JSON", exact=True).click()
                await expect(page.locator("#advanced .alert")).to_contain_text("must be an integer")

                await page.locator("#raw").fill(json.dumps(suite))
                await page.get_by_role("button", name="Apply JSON", exact=True).click()
                await expect(
                    page.get_by_role("button", name="Export JSON", exact=True)
                ).to_be_enabled()

                # Removing the only frontend/mode is invalid for a run, valid for a probe.
                await page.get_by_label("pyqtgraph", exact=True).uncheck()
                await page.get_by_label("stream", exact=True).uncheck()
                await expect(
                    page.get_by_role("button", name="Export JSON", exact=True)
                ).to_be_disabled()
                await page.locator("#kind").select_option("probe")
                await expect(page.locator("#plan-summary")).to_contain_text("1 runs")
                await expect(page.get_by_label("pyqtgraph", exact=True)).to_be_disabled()
                async with page.expect_download() as download_info:
                    await page.get_by_role("button", name="Export JSON", exact=True).click()
                download = await download_info.value
                exported = json.loads(Path(await download.path()).read_text())
                assert exported["frontends"] == exported["modes"] == []
                await browser.close()

    asyncio.run(exercise())
