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
            await expect(
                page.get_by_role("button", name="Grouped", exact=True)
            ).to_have_attribute("aria-pressed", "true")
            await expect(page.locator(".result-group").first).to_be_visible()
            await page.get_by_role("button", name="Individual runs", exact=True).click()
            await expect(page.locator("tbody tr")).to_have_count(min(25, len(all_runs)))
            await page.get_by_label("Frontend", exact=True).select_option("matplotlib")
            await expect(page.locator("tbody tr")).to_have_count(matplotlib_count)
            await page.reload()
            await expect(
                page.get_by_role("button", name="Individual runs", exact=True)
            ).to_have_attribute("aria-pressed", "true")
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

            await page.get_by_role("link", name="Winners", exact=True).click()
            await expect(page.get_by_label("Winner collection")).to_have_value(
                "benchmark"
            )
            if not any(
                c["classification"] == "benchmark" for c in catalog["campaigns"]
            ):
                await expect(
                    page.get_by_role("heading", name="No eligible benchmark results")
                ).to_be_visible()
                await page.get_by_role(
                    "link", name="View smoke checks", exact=True
                ).click()
            else:
                await page.get_by_label("Winner collection").select_option("smoke")
            await expect(page.locator(".winner-board").first).to_be_visible()
            await expect(
                page.get_by_role("heading", name="Best observed smoke results")
            ).to_be_visible()
            await page.reload()
            await expect(page.get_by_label("Winner collection")).to_have_value("smoke")
            assert await page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            )
            if screenshots:
                await page.screenshot(
                    path=str(Path(screenshots) / "winners-mobile.png"), full_page=True
                )
                await page.set_viewport_size({"width": 1440, "height": 1080})
                await page.screenshot(
                    path=str(Path(screenshots) / "winners-desktop.png"), full_page=True
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
            # The public fields are proposed from the summary before the contributor edits them.
            await expect(page.get_by_label("Campaign ID", exact=True)).to_have_value(
                "test-cpu-20260914-ui-qa-campaign"
            )
            await expect(page.get_by_label("Host label", exact=True)).to_have_value("Test CPU")
            await expect(page.get_by_label("Public host ID", exact=True)).to_have_value(
                "test-cpu"
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
            await page.get_by_role(
                "button", name="Restore proposed values", exact=True
            ).click()
            await expect(page.get_by_label("Host label", exact=True)).to_have_value("Test CPU")
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


def test_grouped_campaign_weights_drilldown_dates_and_pagination():
    import asyncio
    import copy

    from playwright.async_api import async_playwright, expect

    seed = json.loads((ROOT / "results/apple-m1-max-20260914-quick.json").read_text())

    def campaign(identifier, rates, day):
        c = copy.deepcopy(seed)
        c.update(
            id=identifier,
            input_sha256=identifier[0] * 64,
            recorded_at=f"2026-09-{day}T12:00:00Z",
            planned_runs=len(rates),
            notes="UI QA fixture",
        )
        template = c["runs"][0]
        c["runs"] = []
        for index, rate in enumerate(rates):
            r = copy.deepcopy(template)
            r.update(
                id=f"run-{index+1}",
                repetition=index + 1,
                status="failed" if rate is None else "ok",
            )
            r["metrics"]["submitted_hz"] = rate
            if rate is None:
                r["samples"] = 0
                r["metrics"]["source_deadline_misses"] = 1
            c["runs"].append(r)
        return c

    fixtures = [
        campaign("aaa", [30] * 30, "14"),
        campaign("bbb", [90, 90, None], "15"),
        campaign("ccc", [None], "16"),
    ]

    async def exercise():
        base = os.environ.get("PLOTBENCH_SITE_BASE", "/plot_bench/")
        app = web.Application()

        async def index(request):
            return web.FileResponse(ROOT / "dist/index.html")

        async def catalog(request):
            return web.json_response({"schema_version": 1, "campaigns": fixtures})

        app.router.add_get(base, index)
        app.router.add_get(base + "catalog.json", catalog)
        app.router.add_static(base, ROOT / "dist")
        async with TestServer(app) as server, async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=os.environ["PLOTBENCH_TEST_BROWSER"], headless=True
            )
            page = await browser.new_page(viewport={"width": 1440, "height": 1080})
            await page.goto(str(server.make_url(base)))
            groups = page.locator(".result-group")
            await expect(groups).to_have_count(1)
            await expect(groups.locator(".rate")).to_have_text("60")
            await expect(groups).to_contain_text("45–75")
            await expect(groups).to_contain_text("32 / 34")
            await expect(groups).to_contain_text("3 campaigns")
            await expect(groups).to_contain_text("2 source-limited")
            await groups.locator(":scope > summary").click()
            await expect(page.locator(".campaign-group")).to_have_count(3)
            failed = page.locator(".campaign-group").filter(has_text="ccc")
            await failed.locator(":scope > summary").click()
            await expect(failed.locator("tbody tr")).to_have_count(1)
            await expect(failed.locator("tbody")).to_contain_text("failed")
            await failed.get_by_role("button", name="Details for").click()
            await expect(page.get_by_role("dialog")).to_be_visible()
            await page.keyboard.press("Escape")
            many = page.locator(".campaign-group").filter(has_text="aaa")
            await many.locator(":scope > summary").click()
            await expect(many.locator("tbody tr")).to_have_count(25)
            await many.get_by_role("button", name="Show more runs").click()
            await expect(many.locator("tbody tr")).to_have_count(30)
            await page.get_by_label("Acquired through (UTC)").fill("2026-09-14")
            await expect(groups.locator(".rate")).to_have_text("30")
            await expect(groups).to_contain_text("1 campaign")
            await page.reload()
            await expect(page.get_by_label("Acquired through (UTC)")).to_have_value(
                "2026-09-14"
            )
            await expect(groups.locator(".rate")).to_have_text("30")
            await page.get_by_label("Acquired from (UTC)").fill("2026-09-17")
            await expect(
                page.get_by_role("heading", name="No matching runs")
            ).to_be_visible()
            await page.get_by_role("link", name="Clear filters", exact=True).click()
            await page.get_by_role("button", name="Individual runs", exact=True).click()
            await expect(page.locator("tbody tr")).to_have_count(25)
            await page.get_by_role("button", name="Next", exact=True).click()
            await expect(page.locator("tbody tr")).to_have_count(9)
            await page.get_by_role("button", name="Grouped", exact=True).click()
            await expect(groups).to_have_count(1)
            await page.set_viewport_size({"width": 390, "height": 844})
            await groups.locator(":scope > summary").click()
            await page.locator(".campaign-group > summary").first.click()
            assert await page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            )
            # A large number of incompatible workloads still paginates by group.
            fixtures[:] = [campaign("ddd", [30] * 26, "17")]
            for index, run in enumerate(fixtures[0]["runs"]):
                run["config"]["seed"] = index
            await page.reload()
            await expect(groups).to_have_count(25)
            await page.get_by_role("button", name="Next", exact=True).click()
            await expect(groups).to_have_count(1)
            await page.get_by_label("Acquired through (UTC)").fill("2026-09-16")
            await expect(
                page.get_by_role("heading", name="No matching runs")
            ).to_be_visible()
            await page.get_by_role("link", name="Clear filters", exact=True).click()
            await expect(groups).to_have_count(25)
            await page.get_by_role("link", name="Winners", exact=True).click()
            await page.get_by_label("Winner collection").select_option("smoke")
            await expect(page.locator(".winner-board")).to_have_count(12)
            await page.get_by_role("button", name="Next cases", exact=True).click()
            await expect(page.locator(".winner-board")).to_have_count(12)
            await page.get_by_role("button", name="Next cases", exact=True).click()
            await expect(page.locator(".winner-board")).to_have_count(2)
            await page.get_by_label("Winner acquired through (UTC)").fill("2026-09-16")
            await expect(
                page.get_by_role("heading", name="No eligible smoke results")
            ).to_be_visible()
            # Cross-host ties and lower-ranked frontends, using test-only records.
            fixtures[:] = [
                campaign("aaa", [20, 30, 40], "14"),
                campaign("bbb", [60, 60, 60], "15"),
                campaign("ccc", [60.03, 60.03, 60.03], "16"),
                campaign("ddd", [50, 50, None], "17"),
            ]
            for index, c in enumerate(fixtures):
                c["host"]["id"] = f"qa-host-{index}"
                c["host"]["label"] = f"QA host {index}"
                c["classification"] = "benchmark"
                for run in c["runs"]:
                    run["frontend"] = ["alpha", "alpha", "beta", "gamma"][index]
                    run["measurement_seconds"] = 30
            await page.goto(str(server.make_url(base)) + "#winners")
            await page.reload()
            board = page.locator(".winner-board")
            await expect(board).to_have_count(1)
            await expect(board).to_contain_text("Joint winners")
            await expect(board.locator(".winner-score strong")).to_have_text("60")
            await expect(board).to_contain_text("QA host 1")
            await expect(board).to_contain_text("QA host 2")
            await expect(board).not_to_contain_text("QA host 0")
            await board.locator(".other-records > summary").click()
            await expect(board).to_contain_text("#3 gamma")
            await expect(board).to_contain_text("1 source-limited")
            await board.locator(".winner-evidence > summary").first.click()
            await board.locator(".result-group > summary").first.click()
            await board.locator(".campaign-group > summary").first.click()
            await board.get_by_role("button", name="Details for").first.click()
            await expect(page.get_by_role("dialog")).to_be_visible()
            await page.keyboard.press("Escape")
            assert await page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            )
            await board.get_by_role("link", name="QA host 1", exact=True).click()
            await expect(page.get_by_label("Host", exact=True)).to_have_value(
                "qa-host-1"
            )
            # Near-equal rates use memory, then CPU, and the tolerance survives reloads.
            for run in fixtures[1]["runs"]:
                run["metrics"].update(rss_peak_mib=300, cpu_mean_percent=1)
            for run in fixtures[2]["runs"]:
                run["metrics"].update(
                    submitted_hz=59, rss_peak_mib=100, cpu_mean_percent=40
                )
            await page.goto(str(server.make_url(base)) + "#winners")
            await page.reload()
            await expect(page.get_by_label("Close update rates")).to_have_value("2")
            await expect(board.get_by_role("heading", level=3)).to_have_text("beta")
            await expect(board).to_contain_text("Median peak RSS: 100 MiB")
            await expect(board).to_contain_text("Median mean CPU: 40%")
            await expect(board.locator(".winner-score strong")).to_have_text("59")
            await page.get_by_label("Close update rates").select_option("0")
            await expect(board.get_by_role("heading", level=3)).to_have_text("alpha")
            await page.reload()
            await expect(page.get_by_label("Close update rates")).to_have_value("0")
            await expect(board.get_by_role("heading", level=3)).to_have_text("alpha")
            await page.get_by_label("Close update rates").select_option("2")
            await expect(board.get_by_role("heading", level=3)).to_have_text("beta")
            for run in fixtures[2]["runs"]:
                run["metrics"]["rss_peak_mib"] = 300
            await page.reload()
            await expect(board.get_by_role("heading", level=3)).to_have_text("alpha")
            for run in fixtures[1]["runs"]:
                run["metrics"]["cpu_mean_percent"] = 80
            await page.reload()
            await expect(board.get_by_role("heading", level=3)).to_have_text("beta")
            for run in fixtures[2]["runs"]:
                run["metrics"]["rss_peak_mib"] = None
            await page.reload()
            await expect(board.get_by_role("heading", level=3)).to_have_text("alpha")
            assert await page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            )
            await browser.close()

    asyncio.run(exercise())
