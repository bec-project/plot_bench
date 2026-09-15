"""Opt-in UI QA: PLOTBENCH_TEST_BROWSER=/path/to/chromium pytest this file.

Build website/dist first. No benchmark executes. PLOTBENCH_QA_SCREENSHOTS may
name an ignored/local directory in which to retain desktop and mobile screenshots.

The catalogue is validated in the browser, so every campaign these tests serve
must itself be a complete run of the official baseline suite: one frontend,
seven sections, three repetitions, complete context, a clean recorded commit.
"""

import copy
import hashlib
import json
import os
import re
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/baseline-campaign.json"
SUITE = json.loads((ROOT.parent / "scenarios/baseline.json").read_text())
SECTIONS = [(case["name"], case["config"]) for case in SUITE["cases"]]
FRONTENDS = SUITE["frontends"]
NO_OVERFLOW = "document.documentElement.scrollWidth <= innerWidth"
OVERFLOWING = """() => [...document.querySelectorAll('body *')]
    .filter(e => e.getBoundingClientRect().right > innerWidth)
    .map(e => [e.tagName, e.className, e.getBoundingClientRect().width]).slice(0, 20)"""
pytestmark = pytest.mark.skipif(
    not os.environ.get("PLOTBENCH_TEST_BROWSER"), reason="explicit QA browser required"
)


def campaign(
    identifier,
    frontend,
    rates,
    day,
    host="test-host",
    label="Test host",
    overrides=None,
    metrics=None,
):
    """A complete 21-run baseline campaign of one frontend, cloned from the fixture's
    first run: every section carries `rates` (None = failed and source-limited) unless
    `overrides` names other rates for a section slug."""
    seed = json.loads(FIXTURE.read_text())
    c = {key: value for key, value in seed.items() if key != "runs"}
    c.update(
        id=identifier,
        title="Plotbench baseline",
        input_sha256=hashlib.sha256(identifier.encode()).hexdigest(),
        recorded_at=f"2026-09-{day}T12:00:00Z",
        planned_runs=3 * len(SECTIONS),
        notes="UI QA fixture",
        host={**seed["host"], "id": host, "label": label},
    )
    template = seed["runs"][0]
    c["runs"] = []
    for slug, config in SECTIONS:
        for repetition, rate in enumerate((overrides or {}).get(slug, rates), 1):
            r = copy.deepcopy(template)
            r.update(
                id=f"run-{len(c['runs']) + 1:04d}",
                scenario=slug,
                frontend=frontend,
                repetition=repetition,
                status="failed" if rate is None else "ok",
                config=dict(config),
            )
            r["context"]["plot_viewports"] = (
                {"waveform": [1949.5, 722.6], "image": None}
                if config["view"] == "waveform"
                else {"waveform": None, "image": [721.6, 721.6]}
            )
            r["metrics"]["submitted_hz"] = rate
            if metrics:
                r["metrics"].update(metrics)
            if rate is None:
                r["samples"] = 0
                r["metrics"]["source_deadline_misses"] = 1
            c["runs"].append(r)
    return c


def raw_summary(seed):
    """A summary.json as the runner writes it, rebuilt from a published fixture."""
    runs = []
    for r in seed["runs"]:
        x = r["context"]
        runs.append(
            {
                "run_id": r["id"],
                "scenario": r["scenario"],
                "frontend": r["frontend"],
                "backend": r["backend"],
                "mode": r["mode"],
                "repetition": r["repetition"],
                "status": r["status"],
                "config": {**r["config"], "generation": 1},
                "measurement_seconds": r["measurement_seconds"],
                "warmup_seconds": r["warmup_seconds"],
                "samples": r["samples"],
                **r["metrics"],
                "metadata": {
                    "headless": False,
                    "qt_platform_plugin": "cocoa",
                    "renderer": x["renderer"],
                    "measurement_stage": x["measurement_stage"],
                    "versions": x["versions"],
                    "pixel_ratio": x["pixel_ratio"],
                    "viewport_size": x["viewport_size"],
                    "plot_viewports": x["plot_viewports"],
                    "display": {
                        "refresh_hz": x["refresh_hz"],
                        "name": "PRIVATE_DISPLAY",
                    },
                },
                "provenance": {
                    "source_sha256": x["source_hash"],
                    "git": {"commit": x["commit"], "dirty": False},
                },
                "private_path": "/PRIVATE_PATH",
            }
        )
    x = seed["runs"][0]["context"]
    return {
        "campaign": {
            "manifest_present": True,
            "started_at": seed["recorded_at"],
            "suite_name": "Plotbench baseline",
            "completion_status": "completed",
            "runs_planned": len(runs),
            "headless": False,
            "cooldown_seconds": 2,
            "repetitions": 3,
            "modes": ["stream"],
            "backends": ["rust"],
            "cases": [{"name": slug} for slug, _ in SECTIONS],
            "hardware": {
                "cpu_model": "Test CPU",
                "os": "Test OS 1.0",
                "architecture": "arm64",
                "memory_gib": 16,
                "hostname": "PRIVATE_HOST",
            },
            "provenance": {
                "source_sha256": x["source_hash"],
                "git": {"commit": x["commit"], "dirty": False},
            },
        },
        "runs": runs,
    }


def serve(campaigns):
    """An aiohttp app serving the built site with `campaigns` (a live list) as catalogue."""
    base = os.environ.get("PLOTBENCH_SITE_BASE", "/plot_bench/")
    app = web.Application()

    async def index(request):
        return web.FileResponse(ROOT / "dist/index.html")

    async def catalog(request):
        return web.json_response({"schema_version": 1, "campaigns": campaigns})

    app.router.add_get(base, index)
    app.router.add_get(base + "catalog.json", catalog)
    app.router.add_static(base, ROOT / "dist")
    return app, base


async def launch(playwright):
    browser = await playwright.chromium.launch(
        executable_path=os.environ["PLOTBENCH_TEST_BROWSER"], headless=True
    )
    page = await browser.new_page(viewport={"width": 1440, "height": 1080})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    return browser, page, errors


def test_results_filters_details_submission_and_mobile():
    import asyncio

    from playwright.async_api import async_playwright, expect

    seed = json.loads(FIXTURE.read_text())
    other = campaign(
        "qtgraphs-b", "qtgraphs", [30, 30, 30], "14", "qa-host-b", "QA host B"
    )
    catalog = [seed, other]
    app, base = serve(catalog)

    async def exercise():
        async with TestServer(app) as server, async_playwright() as playwright:
            browser, page, errors = await launch(playwright)
            requests = []
            page.on("request", lambda request: requests.append(request))
            url = str(server.make_url(base))
            await page.goto(url)
            rail = page.get_by_role("navigation", name="Sections")
            nav = page.get_by_role("navigation", name="Main navigation")
            # The site opens on the Winners page; every board pairs facts with a chart.
            await expect(
                nav.get_by_role("link", name="Winners", exact=True)
            ).to_have_attribute("aria-current", "page")
            await expect(page.locator(".winner-board")).to_have_count(7)
            await expect(page.locator(".board-chart .chart-rows")).to_have_count(7)
            await page.goto(url + "#results")
            await expect(rail.get_by_role("link")).to_have_count(8)
            await expect(
                rail.get_by_role("link", name="All sections")
            ).to_have_attribute("aria-current", "page")
            await expect(
                page.get_by_role("button", name="Grouped", exact=True)
            ).to_have_attribute("aria-pressed", "true")
            groups = page.locator(".result-group")
            await expect(groups.first).to_be_visible()
            # Two frontends on the fixture host plus one on the other: 3 groups per section.
            await expect(groups).to_have_count(21)
            await expect(page.locator(".section-divider")).to_have_count(7)
            # Groups are ordered by median updates/s inside a section: the 30 Hz qtgraphs
            # group on the other host comes last; the Order selector persists in the URL.
            await expect(groups.nth(2)).to_contain_text("qtgraphs")
            await expect(groups.first.locator(".rate")).to_have_text("60")
            await page.get_by_label("Order", exact=True).select_option("frontend")
            await expect(groups.first).to_contain_text("matplotlib")
            await page.reload()
            await expect(page.get_by_label("Order", exact=True)).to_have_value(
                "frontend"
            )
            await page.get_by_label("Order", exact=True).select_option("")
            await expect(groups.nth(2)).to_contain_text("qtgraphs")
            await rail.get_by_role("link", name="2 Multi-curve").click()
            await expect(
                rail.get_by_role("link", name="2 Multi-curve")
            ).to_have_attribute("aria-current", "page")
            await expect(page.locator(".section-head h2")).to_have_text(
                "Multi-curve waveform"
            )
            await expect(groups).to_have_count(3)
            await expect(page.locator(".section-divider")).to_have_count(0)
            await page.get_by_role("button", name="Individual runs", exact=True).click()
            await expect(page.locator("tbody tr")).to_have_count(9)
            await page.get_by_label("Frontend", exact=True).select_option("matplotlib")
            await expect(page.locator("tbody tr")).to_have_count(3)
            await page.get_by_label("Host", exact=True).select_option("test-host")
            await expect(page.locator("tbody tr")).to_have_count(3)
            await page.reload()
            await expect(
                page.get_by_role("button", name="Individual runs", exact=True)
            ).to_have_attribute("aria-pressed", "true")
            await expect(page.get_by_label("Frontend", exact=True)).to_have_value(
                "matplotlib"
            )
            await expect(page.get_by_label("Host", exact=True)).to_have_value(
                "test-host"
            )
            await expect(
                rail.get_by_role("link", name="2 Multi-curve")
            ).to_have_attribute("aria-current", "page")
            await expect(page.locator("tbody tr")).to_have_count(3)
            await page.get_by_role("button", name="Details for").first.click()
            dialog = page.get_by_role("dialog")
            await expect(dialog).to_be_visible()
            await expect(dialog).to_contain_text("Source commit")
            await expect(dialog).to_contain_text("Multi-curve waveform")
            await page.keyboard.press("Escape")
            await expect(dialog).to_have_count(0)
            await nav.get_by_role("link", name="Hosts", exact=True).click()
            await expect(page.locator(".host-card")).to_have_count(2)
            await expect(page.locator(".host-card .coverage-chips")).to_have_count(2)
            await expect(page.locator(".host-card .chip-on")).to_have_count(14)
            await page.get_by_role("link", name="Explore results").first.click()
            await expect(page.get_by_label("Host", exact=True)).to_have_value(
                "qa-host-b"
            )
            await expect(groups).to_have_count(7)
            await page.get_by_role("link", name="Reset", exact=True).click()
            await expect(page.get_by_label("Host", exact=True)).to_have_value("")
            await expect(groups).to_have_count(21)
            # Old links with retired keys, and unknown sections, degrade to the unfiltered page.
            await page.goto(
                url + "#results?workload=x&kind=smoke&platform=y&section=nope"
            )
            await expect(
                rail.get_by_role("link", name="All sections")
            ).to_have_attribute("aria-current", "page")
            await expect(groups).to_have_count(21)
            await page.goto(url + "#results")

            screenshots = os.environ.get("PLOTBENCH_QA_SCREENSHOTS")
            if screenshots:
                Path(screenshots).mkdir(parents=True, exist_ok=True)
                await page.screenshot(
                    path=str(Path(screenshots) / "results-desktop.png"), full_page=True
                )
            await page.set_viewport_size({"width": 390, "height": 844})
            await expect(groups.first).to_be_visible()
            if screenshots:
                await page.screenshot(
                    path=str(Path(screenshots) / "results-mobile.png"), full_page=True
                )
            assert await page.evaluate(NO_OVERFLOW), await page.evaluate(OVERFLOWING)

            await nav.get_by_role("link", name="Winners", exact=True).click()
            await expect(page.get_by_label("Close update rates")).to_have_value("2")
            boards = page.locator(".winner-board")
            await expect(boards).to_have_count(7)
            await expect(boards.first).to_contain_text("Waveform")
            await expect(boards.first).to_contain_text(
                "spans 1 source revision · 2 hosts"
            )
            await expect(boards.last).to_contain_text("device pixels")
            await page.reload()
            await expect(boards).to_have_count(7)
            assert await page.evaluate(NO_OVERFLOW), await page.evaluate(OVERFLOWING)
            if screenshots:
                await page.screenshot(
                    path=str(Path(screenshots) / "winners-mobile.png"), full_page=True
                )
            await page.set_viewport_size({"width": 1440, "height": 1080})
            if screenshots:
                await page.screenshot(
                    path=str(Path(screenshots) / "winners-desktop.png"), full_page=True
                )
            await page.goto(url + "#winners?kind=smoke&section=waveform")
            await expect(boards).to_have_count(1)
            await nav.get_by_role("link", name="Overall", exact=True).click()
            await expect(page.locator(".overall-table tbody tr")).to_have_count(3)
            await expect(page.locator(".incomplete-list")).to_have_count(0)
            if screenshots:
                await page.screenshot(
                    path=str(Path(screenshots) / "overall-desktop.png"), full_page=True
                )
            await nav.get_by_role("link", name="Suite", exact=True).click()
            await expect(page.locator(".suite-table tbody tr")).to_have_count(7)
            await expect(page.locator("pre")).to_contain_text(
                "plotbench run --baseline"
            )

            await nav.get_by_role("link", name="Contribute", exact=True).click()
            assert await page.evaluate(NO_OVERFLOW), await page.evaluate(OVERFLOWING)
            raw = raw_summary(seed)
            await page.get_by_label("Campaign summary", exact=True).set_input_files(
                {
                    "name": "summary.json",
                    "mimeType": "application/json",
                    "buffer": json.dumps(raw).encode(),
                }
            )
            # The public fields are proposed from the summary before the contributor edits them.
            await expect(page.get_by_label("Campaign ID", exact=True)).to_have_value(
                re.compile(r"^test-cpu.*-plotbench-baseline$")
            )
            await expect(page.get_by_label("Host label", exact=True)).to_have_value(
                re.compile(r"^Test CPU")
            )
            await expect(page.get_by_label("Public host ID", exact=True)).to_have_value(
                re.compile(r"^test-cpu")
            )
            await page.get_by_label("Campaign ID", exact=True).fill("qa-campaign")
            await page.get_by_label("Public host ID", exact=True).fill("qa-host")
            await page.get_by_label("Host label", exact=True).fill("QA workstation")
            await page.get_by_role(
                "button", name="Preview public submission", exact=True
            ).click()
            ready = page.get_by_role("heading", name="Ready to review")
            await expect(ready).to_be_visible()
            await expect(page.locator(".submission-preview")).to_contain_text(
                "7 of 7 sections · 2 frontends · 3 repetitions each"
            )
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
            assert public["classification"] == "benchmark"
            assert len(public["runs"]) == 42
            assert "PRIVATE_" not in json.dumps(public)
            assert not [
                r for r in requests if r.method != "GET" or not r.url.startswith(url)
            ]
            await page.get_by_label("Host label", exact=True).fill("Changed host")
            await expect(ready).to_have_count(0)
            await page.get_by_role(
                "button", name="Restore proposed values", exact=True
            ).click()
            await expect(page.get_by_label("Host label", exact=True)).to_have_value(
                re.compile(r"^Test CPU")
            )
            # A campaign of any other suite is refused before it can be previewed.
            partial = raw_summary(seed)
            partial["runs"] = partial["runs"][:1]
            partial["campaign"]["runs_planned"] = 1
            await page.get_by_label("Campaign summary", exact=True).set_input_files(
                {
                    "name": "partial.json",
                    "mimeType": "application/json",
                    "buffer": json.dumps(partial).encode(),
                }
            )
            await page.get_by_role(
                "button", name="Preview public submission", exact=True
            ).click()
            await expect(page.get_by_role("alert")).to_contain_text(
                "official baseline suite"
            )
            await expect(ready).to_have_count(0)
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


def test_grouped_campaign_weights_drilldown_dates_pagination_winners_and_overall():
    import asyncio

    from playwright.async_api import async_playwright, expect

    fixtures = [
        campaign("aaa", "pyqtgraph", [30, 30, 30], "14"),
        campaign("bbb", "pyqtgraph", [90, 90, None], "15"),
        campaign("ccc", "pyqtgraph", [None, None, None], "16"),
    ]
    app, base = serve(fixtures)

    async def exercise():
        async with TestServer(app) as server, async_playwright() as playwright:
            browser, page, errors = await launch(playwright)
            url = str(server.make_url(base))
            await page.goto(url + "#results")
            rail = page.get_by_role("navigation", name="Sections")
            nav = page.get_by_role("navigation", name="Main navigation")
            groups = page.locator(".result-group")
            await expect(groups).to_have_count(7)
            await rail.get_by_role("link", name="1 Waveform").click()
            await expect(groups).to_have_count(1)
            await expect(groups.locator(".rate")).to_have_text("60")
            await expect(groups).to_contain_text("45–75")
            await expect(groups).to_contain_text("5 / 9")
            await expect(groups).to_contain_text("3 campaigns")
            await expect(groups).to_contain_text("4 source-limited")
            await groups.locator(":scope > summary").click()
            await expect(page.locator(".campaign-group")).to_have_count(3)
            failed = page.locator(".campaign-group").filter(has_text="ccc")
            await failed.locator(":scope > summary").click()
            await expect(failed.locator("tbody tr")).to_have_count(3)
            await expect(failed.locator("tbody")).to_contain_text("failed")
            await failed.get_by_role("button", name="Details for").first.click()
            await expect(page.get_by_role("dialog")).to_be_visible()
            await page.keyboard.press("Escape")
            await page.get_by_label("Acquired through (UTC)").fill("2026-09-14")
            await expect(groups.locator(".rate")).to_have_text("30")
            await expect(groups).to_contain_text("1 campaign")
            await page.reload()
            await expect(page.get_by_label("Acquired through (UTC)")).to_have_value(
                "2026-09-14"
            )
            await expect(rail.get_by_role("link", name="1 Waveform")).to_have_attribute(
                "aria-current", "page"
            )
            await expect(groups.locator(".rate")).to_have_text("30")
            await page.get_by_label("Acquired from (UTC)").fill("2026-09-17")
            await expect(
                page.get_by_role("heading", name="No matching runs")
            ).to_be_visible()
            await page.get_by_role("link", name="Clear filters", exact=True).click()
            await expect(groups).to_have_count(7)
            await page.get_by_role("button", name="Individual runs", exact=True).click()
            await expect(page.locator("tbody tr")).to_have_count(25)
            await page.get_by_role("button", name="Next", exact=True).click()
            await expect(page.locator("tbody tr")).to_have_count(25)
            await page.get_by_role("button", name="Next", exact=True).click()
            await expect(page.locator("tbody tr")).to_have_count(13)
            await page.get_by_role("button", name="Grouped", exact=True).click()
            await expect(groups).to_have_count(7)
            await page.set_viewport_size({"width": 390, "height": 844})
            await groups.first.locator(":scope > summary").click()
            await page.locator(".campaign-group > summary").first.click()
            assert await page.evaluate(NO_OVERFLOW), await page.evaluate(OVERFLOWING)
            await page.set_viewport_size({"width": 1440, "height": 1080})
            # Every baseline frontend at once still paginates by group: 9 x 7 = 63.
            fixtures[:] = [
                campaign(f"all-{i}", frontend, [30 - i] * 3, "17")
                for i, frontend in enumerate(FRONTENDS)
            ]
            await page.reload()
            await expect(groups).to_have_count(25)
            await page.get_by_role("button", name="Next", exact=True).click()
            await expect(groups).to_have_count(25)
            await page.get_by_role("button", name="Next", exact=True).click()
            await expect(groups).to_have_count(13)
            await page.get_by_label("Acquired through (UTC)").fill("2026-09-16")
            await expect(
                page.get_by_role("heading", name="No matching runs")
            ).to_be_visible()
            await page.get_by_role("link", name="Clear filters", exact=True).click()
            await expect(groups).to_have_count(25)
            await nav.get_by_role("link", name="Winners", exact=True).click()
            board = page.locator(".winner-board")
            await expect(board).to_have_count(7)
            await page.goto(url + "#winners?section=waveform")
            await expect(board).to_have_count(1)
            await expect(board.locator(".frontend-record")).to_have_count(1)
            await board.locator(".other-records > summary").click()
            await expect(board.locator(".frontend-record")).to_have_count(9)
            await expect(board.locator(".board-chart .chart-row")).to_have_count(9)
            await expect(board.locator(".board-chart .chart-row-winner")).to_have_count(
                1
            )
            widths = await board.locator(
                ".board-chart .chart-row > .chart-track > .chart-bar"
            ).evaluate_all("els => els.map(e => e.getBoundingClientRect().width)")
            assert widths[0] > widths[-1] > 0, widths
            await page.get_by_label("Acquired through (UTC)").fill("2026-09-16")
            await expect(
                page.get_by_role("heading", name="No eligible benchmark results")
            ).to_be_visible()
            # Cross-host ties and lower-ranked frontends.
            fixtures[:] = [
                campaign(
                    "aaa", "pyqtgraph", [20, 30, 40], "14", "qa-host-0", "QA host 0"
                ),
                campaign(
                    "bbb", "pyqtgraph", [60, 60, 60], "15", "qa-host-1", "QA host 1"
                ),
                campaign(
                    "ccc", "matplotlib", [60.03] * 3, "16", "qa-host-2", "QA host 2"
                ),
                campaign(
                    "ddd", "qtgraphs", [50, 50, None], "17", "qa-host-3", "QA host 3"
                ),
            ]
            await page.goto(url + "#winners?section=waveform")
            await page.reload()
            await expect(board).to_have_count(1)
            await expect(board).to_contain_text("Joint winners")
            await expect(board.locator(".winner-score strong")).to_have_text("60")
            await expect(board).to_contain_text("QA host 1")
            await expect(board).to_contain_text("QA host 2")
            await expect(board).not_to_contain_text("QA host 0")
            await expect(board).to_contain_text("spans 1 source revision · 4 hosts")
            await expect(board).to_contain_text("2x · 120 Hz refresh · native")
            await board.locator(".other-records > summary").click()
            await expect(board).to_contain_text("#3 qtgraphs")
            await expect(board).to_contain_text("1 source-limited")
            await board.locator(".winner-evidence > summary").first.click()
            await board.locator(".result-group > summary").first.click()
            await board.locator(".campaign-group > summary").first.click()
            await board.get_by_role("button", name="Details for").first.click()
            await expect(page.get_by_role("dialog")).to_be_visible()
            await page.keyboard.press("Escape")
            assert await page.evaluate(NO_OVERFLOW), await page.evaluate(OVERFLOWING)
            await board.get_by_role("link", name="QA host 1", exact=True).click()
            await expect(page.get_by_label("Host", exact=True)).to_have_value(
                "qa-host-1"
            )
            await expect(rail.get_by_role("link", name="1 Waveform")).to_have_attribute(
                "aria-current", "page"
            )
            # Near-equal rates use memory, then CPU, and the tolerance survives reloads
            # together with the section.
            for run in fixtures[1]["runs"]:
                run["metrics"].update(rss_peak_mib=300, cpu_mean_percent=1)
            for run in fixtures[2]["runs"]:
                run["metrics"].update(
                    submitted_hz=59, rss_peak_mib=100, cpu_mean_percent=40
                )
            await page.goto(url + "#winners?section=waveform")
            await page.reload()
            await expect(page.get_by_label("Close update rates")).to_have_value("2")
            await expect(board.get_by_role("heading", level=3)).to_have_text(
                "matplotlib"
            )
            await expect(board).to_contain_text("Median peak RSS: 100 MiB")
            await expect(board).to_contain_text("Median mean CPU: 40%")
            await expect(board.locator(".winner-score strong")).to_have_text("59")
            await page.get_by_label("Close update rates").select_option("0")
            await expect(board.get_by_role("heading", level=3)).to_have_text(
                "pyqtgraph"
            )
            await page.reload()
            await expect(page.get_by_label("Close update rates")).to_have_value("0")
            await expect(rail.get_by_role("link", name="1 Waveform")).to_have_attribute(
                "aria-current", "page"
            )
            await expect(board).to_have_count(1)
            await expect(board.get_by_role("heading", level=3)).to_have_text(
                "pyqtgraph"
            )
            await page.get_by_label("Close update rates").select_option("2")
            await expect(board.get_by_role("heading", level=3)).to_have_text(
                "matplotlib"
            )
            for run in fixtures[2]["runs"]:
                run["metrics"]["rss_peak_mib"] = 300
            await page.reload()
            await expect(board.get_by_role("heading", level=3)).to_have_text(
                "pyqtgraph"
            )
            for run in fixtures[1]["runs"]:
                run["metrics"]["cpu_mean_percent"] = 80
            await page.reload()
            await expect(board.get_by_role("heading", level=3)).to_have_text(
                "matplotlib"
            )
            for run in fixtures[2]["runs"]:
                run["metrics"]["rss_peak_mib"] = None
            await page.reload()
            await expect(board.get_by_role("heading", level=3)).to_have_text(
                "pyqtgraph"
            )
            assert await page.evaluate(NO_OVERFLOW), await page.evaluate(OVERFLOWING)
            # Overall: placements summed for complete frontends; a frontend without a
            # valid rate in one section is listed with the section it misses.
            fixtures[:] = [
                campaign(
                    "bbb",
                    "pyqtgraph",
                    [60, 60, 60],
                    "15",
                    "qa-host-1",
                    "QA host 1",
                    metrics={"rss_peak_mib": 300, "cpu_mean_percent": 1},
                ),
                campaign(
                    "ccc",
                    "matplotlib",
                    [59, 59, 59],
                    "16",
                    "qa-host-2",
                    "QA host 2",
                    metrics={"rss_peak_mib": 100, "cpu_mean_percent": 40},
                ),
                campaign(
                    "ddd",
                    "qtgraphs",
                    [50, 50, None],
                    "17",
                    "qa-host-3",
                    "QA host 3",
                    overrides={"large-image": [None, None, None]},
                ),
            ]
            await page.goto(url + "#overall")
            await page.reload()
            rows = page.locator(".overall-table tbody tr")
            await expect(rows).to_have_count(2)
            await expect(rows.nth(0)).to_contain_text("#1")
            await expect(rows.nth(0)).to_contain_text("matplotlib")
            await expect(rows.nth(0).locator(".overall-total")).to_have_text("7")
            await expect(rows.nth(0).locator(".placement-win")).to_have_count(7)
            await expect(rows.nth(1)).to_contain_text("#2")
            await expect(rows.nth(1)).to_contain_text("pyqtgraph")
            await expect(rows.nth(1).locator(".overall-total")).to_have_text("14")
            incomplete = page.locator(".incomplete-list")
            await expect(incomplete).to_contain_text("qtgraphs")
            await expect(incomplete).to_contain_text("Large scalar image")
            await expect(incomplete).to_contain_text("6 of 7 sections")
            await page.get_by_label("Close update rates").select_option("0")
            await expect(rows.nth(0)).to_contain_text("pyqtgraph")
            await page.reload()
            await expect(page.get_by_label("Close update rates")).to_have_value("0")
            await expect(rows.nth(0)).to_contain_text("pyqtgraph")
            await expect(rows.nth(1)).to_contain_text("matplotlib")
            await rows.nth(0).locator(".placement").first.click()
            await expect(board).to_have_count(1)
            await expect(rail.get_by_role("link", name="1 Waveform")).to_have_attribute(
                "aria-current", "page"
            )
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.goto(url + "#overall")
            await expect(rows).to_have_count(2)
            assert await page.evaluate(NO_OVERFLOW), await page.evaluate(OVERFLOWING)
            assert not errors
            await browser.close()

    asyncio.run(exercise())


def test_built_catalogue_renders_results_or_the_empty_state():
    """The reviewed collection may be empty; either way the built site must render."""
    import asyncio

    from playwright.async_api import async_playwright, expect

    catalog = json.loads((ROOT / "dist/catalog.json").read_text())

    async def exercise():
        base = os.environ.get("PLOTBENCH_SITE_BASE", "/plot_bench/")
        app = web.Application()

        async def index(request):
            return web.FileResponse(ROOT / "dist/index.html")

        app.router.add_get(base, index)
        app.router.add_static(base, ROOT / "dist")
        async with TestServer(app) as server, async_playwright() as playwright:
            browser, page, errors = await launch(playwright)
            await page.goto(str(server.make_url(base)))
            rail = page.get_by_role("navigation", name="Sections")
            nav = page.get_by_role("navigation", name="Main navigation")
            await expect(rail.get_by_role("link")).to_have_count(8)
            await expect(
                nav.get_by_role("link", name="Winners", exact=True)
            ).to_have_attribute("aria-current", "page")
            await nav.get_by_role("link", name="Results", exact=True).click()
            if catalog["campaigns"]:
                await expect(page.locator(".result-group").first).to_be_visible()
                await nav.get_by_role("link", name="Hosts", exact=True).click()
                await expect(page.locator(".host-card")).to_have_count(
                    len({c["host"]["id"] for c in catalog["campaigns"]})
                )
            else:
                await expect(
                    page.get_by_role("heading", name="The collection starts here")
                ).to_be_visible()
                await nav.get_by_role("link", name="Winners", exact=True).click()
                await expect(
                    page.get_by_role("heading", name="No eligible benchmark results")
                ).to_be_visible()
                await nav.get_by_role("link", name="Overall", exact=True).click()
                await expect(
                    page.get_by_role("heading", name="No overall ranking yet")
                ).to_be_visible()
            await nav.get_by_role("link", name="Suite", exact=True).click()
            await expect(page.locator(".suite-table tbody tr")).to_have_count(7)
            assert not errors
            await browser.close()

    asyncio.run(exercise())
