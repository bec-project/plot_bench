"""Opt-in UI QA: PLOTBENCH_TEST_BROWSER=/path/to/chromium pytest this file.

Build website/dist first. No benchmark executes. PLOTBENCH_QA_SCREENSHOTS may
name an ignored/local directory in which to retain desktop and mobile screenshots.
"""

import json
import os
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    not os.environ.get("PLOTBENCH_TEST_BROWSER"), reason="explicit QA browser required"
)


def test_results_filters_details_submission_and_mobile():
    import asyncio

    from playwright.async_api import async_playwright, expect

    async def exercise():
        base = os.environ.get("PLOTBENCH_SITE_BASE", "/plot_bench/")
        app = web.Application()

        async def index(request):
            return web.FileResponse(ROOT / "dist/index.html")

        app.router.add_get(base, index)
        app.router.add_static(base, ROOT / "dist")
        async with TestServer(app) as server, async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=os.environ["PLOTBENCH_TEST_BROWSER"], headless=True
            )
            page = await browser.new_page(viewport={"width": 1440, "height": 1080})
            errors, requests = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append(request))
            url = str(server.make_url(base))
            await page.goto(url)
            catalog = json.loads((ROOT / "dist/catalog.json").read_text())
            seed = next(
                c
                for c in catalog["campaigns"]
                if c["id"] == "apple-m1-max-20260914-quick"
            )
            all_runs = [r for c in catalog["campaigns"] for r in c["runs"]]
            matplotlib_count = min(
                25, sum(r["frontend"] == "matplotlib" for r in all_runs)
            )
            await expect(page.locator("tbody tr")).to_have_count(min(25, len(all_runs)))
            await page.get_by_label("Frontend", exact=True).select_option("matplotlib")
            await expect(page.locator("tbody tr")).to_have_count(matplotlib_count)
            await page.reload()
            await expect(page.get_by_label("Frontend", exact=True)).to_have_value(
                "matplotlib"
            )
            await expect(page.locator("tbody tr")).to_have_count(matplotlib_count)
            await page.get_by_role("button", name="Details for").first.click()
            await expect(page.get_by_role("dialog")).to_be_visible()
            await expect(page.get_by_role("dialog")).to_contain_text("Source commit")
            await page.keyboard.press("Escape")
            await expect(page.get_by_role("dialog")).to_have_count(0)
            await page.get_by_role("link", name="Hosts", exact=True).click()
            await page.get_by_role("link", name="Explore results").first.click()
            await expect(page.get_by_label("Host", exact=True)).not_to_have_value("")
            await page.get_by_role("link", name="Reset", exact=True).click()

            screenshots = os.environ.get("PLOTBENCH_QA_SCREENSHOTS")
            if screenshots:
                Path(screenshots).mkdir(parents=True, exist_ok=True)
                await page.screenshot(
                    path=str(Path(screenshots) / "results-desktop.png"), full_page=True
                )
            await page.set_viewport_size({"width": 390, "height": 844})
            if screenshots:
                await page.screenshot(
                    path=str(Path(screenshots) / "results-mobile.png"), full_page=True
                )
            assert await page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), await page.evaluate(
                """() => [...document.querySelectorAll('body *')]
                .filter(e => e.getBoundingClientRect().right > innerWidth)
                .map(e => [e.tagName, e.className, e.getBoundingClientRect().width]).slice(0, 20)"""
            )

            await page.get_by_role("link", name="Contribute", exact=True).click()
            assert await page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            )
            raw = {
                "campaign": {
                    "manifest_present": True,
                    "started_at": seed["recorded_at"],
                    "suite_name": "UI QA campaign",
                    "completion_status": "complete",
                    "runs_planned": 1,
                    "headless": False,
                    "hardware": {"cpu_model": "Test CPU", "hostname": "PRIVATE_HOST"},
                },
                "runs": [
                    {
                        **seed["runs"][0],
                        **seed["runs"][0]["metrics"],
                        "run_id": "qa-run",
                        "metadata": {"headless": False, "qt_platform_plugin": "cocoa"},
                        "private_path": "/PRIVATE_PATH",
                    }
                ],
            }
            await page.get_by_label("Campaign summary", exact=True).set_input_files(
                {
                    "name": "summary.json",
                    "mimeType": "application/json",
                    "buffer": json.dumps(raw).encode(),
                }
            )
            await page.get_by_label("Campaign ID", exact=True).fill("qa-campaign")
            await page.get_by_label("Public host ID", exact=True).fill("qa-host")
            await page.get_by_label("Host label", exact=True).fill("QA workstation")
            await page.get_by_role(
                "button", name="Preview public submission", exact=True
            ).click()
            await expect(
                page.get_by_role("heading", name="Ready to review")
            ).to_be_visible()
            download = page.get_by_role(
                "button", name="Download qa-campaign.json", exact=True
            )
            await expect(download).to_be_disabled()
            await page.get_by_role("checkbox").check()
            async with page.expect_download() as info:
                await download.click()
            downloaded = await info.value
            public = json.loads(Path(await downloaded.path()).read_text())
            assert public["host"]["id"] == "qa-host"
            assert "PRIVATE_" not in json.dumps(public)
            assert not [
                r for r in requests if r.method != "GET" or not r.url.startswith(url)
            ]
            await page.get_by_label("Host label", exact=True).fill("Changed host")
            await expect(
                page.get_by_role("heading", name="Ready to review")
            ).to_have_count(0)
            await page.get_by_label("Campaign summary", exact=True).set_input_files(
                {
                    "name": "bad.json",
                    "mimeType": "application/json",
                    "buffer": b"not json",
                }
            )
            await expect(page.get_by_role("alert")).to_be_visible()
            assert not errors
            await browser.close()

    asyncio.run(exercise())
