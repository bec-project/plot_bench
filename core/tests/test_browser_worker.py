import asyncio
from types import SimpleNamespace

import pytest

from plotbench.browser_worker import BrowserCompletion, completion_grace_seconds, run_browser


def notification(event, **changes):
    state = {
        "submitted": 10,
        "running": event == "started",
        "complete": event == "stopped",
        "stop_reason": "duration" if event == "stopped" else None,
        "error": None,
        "metrics_error": None,
        "dropped_metrics": 0,
    }
    return {"event": event, "state": state | changes}


def test_completion_waits_for_flush_notification():
    async def check():
        completion = BrowserCompletion(30)
        completion.notify(notification("started"))
        task = asyncio.create_task(completion.wait())
        await asyncio.sleep(0)
        assert not task.done()
        completion.notify(notification("stopped"))
        assert (await task)["complete"] is True

    asyncio.run(check())


@pytest.mark.parametrize(
    "changes, error",
    [
        ({"stop_reason": "user"}, "interrupted"),
        ({"complete": False}, "interrupted"),
        ({"running": True}, "interrupted"),
        ({"submitted": 0}, "interrupted"),
        ({"submitted": "ten"}, "interrupted"),
        ({"error": "source disconnected"}, "source disconnected"),
        ({"metrics_error": "upload failed"}, "upload failed"),
        ({"dropped_metrics": 1}, "lost samples"),
    ],
)
def test_timed_completion_requires_successful_duration_and_telemetry(changes, error):
    async def check():
        completion = BrowserCompletion(30)
        completion.notify(notification("stopped", **changes))
        with pytest.raises(RuntimeError, match=error):
            await completion.wait()

    asyncio.run(check())


def test_window_close_interrupts_timed_run_but_interactive_stop_does_not_close_demo():
    async def check():
        timed = BrowserCompletion(30)
        timed.closed()
        with pytest.raises(RuntimeError, match="closed before duration"):
            await timed.wait()

        interactive = BrowserCompletion(0)
        interactive.notify(notification("started"))
        interactive.notify(notification("stopped", stop_reason="user"))
        assert not interactive.finished.is_set()
        interactive.closed()
        assert await interactive.wait() is None

    asyncio.run(check())


def test_startup_and_completion_timeouts_are_reported_separately():
    async def check():
        startup = BrowserCompletion(1)
        with pytest.raises(RuntimeError, match="first frame"):
            await startup.wait(startup_timeout=0)
        stalled = BrowserCompletion(0.001)
        stalled.notify(notification("started"))
        with pytest.raises(RuntimeError, match="finish and flush.*grace 0 s"):
            await stalled.wait(completion_grace=0)

    asyncio.run(check())


def test_completion_grace_scales_with_duration_and_latency_is_recorded():
    # Page teardown after a timed run grows with submitted frames; a 35.2 s run of 2048²
    # scalar heatmaps needed about 51 s after its nominal end to signal completion.
    assert completion_grace_seconds(0) == 15
    assert completion_grace_seconds(35.2) == pytest.approx(85.4)
    assert completion_grace_seconds(300) == 615
    completion = BrowserCompletion(30)
    assert completion.completion_latency_seconds() is None
    completion.notify(notification("started"))
    completion.started_at -= 40
    completion.notify(notification("stopped"))
    assert completion.completion_latency_seconds() == pytest.approx(10, abs=0.5)
    assert BrowserCompletion(0).completion_latency_seconds() is None


@pytest.mark.parametrize("page_error", [None, "rasterization failed"])
def test_browser_worker_only_captures_after_completion_and_always_exports_metadata(
    monkeypatch, tmp_path, page_error
):
    # An in-process Playwright substitute: no browser, page, HTTP server or network is started.
    import playwright.async_api

    events = []
    batches = []

    class FakePage:
        def __init__(self):
            self.handlers = {}
            self.binding = None

        async def evaluate(self, expression):
            assert expression == "window.devicePixelRatio", "no status evaluation/polling"
            return 2

        async def close(self):
            if callback := self.handlers.get("close"):
                callback(self)

        async def expose_binding(self, name, callback):
            assert name == "__plotbenchLifecycle"
            self.binding = callback

        def on(self, name, callback):
            self.handlers[name] = callback

        async def goto(self, url):
            events.append("navigation")
            self.binding({"page": self}, notification("started"))
            if page_error:
                self.handlers["pageerror"](page_error)
            else:
                events.append("frontend_flushed")
                self.binding({"page": self}, notification("stopped"))

        async def screenshot(self, *, path):
            assert events[-1] == "frontend_flushed"
            assert path == str(tmp_path / "preview.png")
            events.append("screenshot")

    class FakeBrowser:
        version = "test-browser"

        def __init__(self):
            self.handlers = {}

        async def new_page(self, **_kwargs):
            return FakePage()

        def on(self, name, callback):
            self.handlers[name] = callback

        async def close(self):
            events.append("browser_closed")
            self.handlers["disconnected"](self)

    class FakeChromium:
        async def launch(self, *, headless):
            assert not headless
            return FakeBrowser()

    class FakePlaywright:
        async def __aenter__(self):
            return SimpleNamespace(chromium=FakeChromium())

        async def __aexit__(self, *_args):
            pass

    monkeypatch.setattr(playwright.async_api, "async_playwright", FakePlaywright)
    monkeypatch.setattr("plotbench.browser_worker.request", lambda _url, data: batches.append(data))
    args = SimpleNamespace(
        headless=False,
        width=1100,
        height=820,
        duration=30,
        screenshot=tmp_path / "preview.png",
        url="http://localhost",
        mode="stream",
        run_id="test",
    )
    if page_error:
        with pytest.raises(RuntimeError, match=page_error):
            asyncio.run(run_browser(args, "http://localhost/frontend"))
        assert "screenshot" not in events
    else:
        asyncio.run(run_browser(args, "http://localhost/frontend"))
        assert events == ["navigation", "frontend_flushed", "screenshot", "browser_closed"]
    assert len(batches) == 1
    metadata = batches[0]["metadata"]
    assert batches[0]["samples"] == []
    assert metadata["termination_reason"] == ("error" if page_error else "duration")
    assert metadata["qa_screenshot"] is (page_error is None)
    assert metadata["completion_grace_seconds"] == 75
    if not page_error:
        assert isinstance(metadata["completion_latency_seconds"], float)
    assert metadata["browser_version"] == "test-browser"
    assert metadata["browser_device_scale_factor"] == 2
