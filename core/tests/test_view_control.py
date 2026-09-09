"""Plot controls change the actual input workload without blocking GUI callers."""

import asyncio
import json
import threading
import time

import pytest
from aiohttp.test_utils import TestServer

from plotbench.client import FrameSource
from plotbench.config import Config
from plotbench.generator import make_packet
from plotbench.protocol import decode_frame
from plotbench.server import Server


def wait_for_frame(client, view):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        frame = client.take_latest()
        if frame is not None and frame.header["config"]["view"] == view:
            return frame
        time.sleep(0.005)
    raise AssertionError(f"No {view} frame received: {client.error or client.view_error}")


@pytest.mark.parametrize("mode", ["stream", "replay"])
def test_switching_view_removes_disabled_payload_and_preserves_other_settings(tmp_path, mode):
    async def exercise():
        server = Server(Config(hz=60, points=32, append_count=4, width=8, height=6), tmp_path)
        async with TestServer(server.app()) as endpoint:
            client = FrameSource(str(endpoint.make_url("/")), mode)
            client.start()
            try:
                first = await asyncio.to_thread(wait_for_frame, client, "both")
                assert set(first.arrays) == {"waveform", "image"}
                generation = first.generation
                for view, arrays in (
                    ("waveform", {"waveform"}),
                    ("image", {"image"}),
                    ("both", {"waveform", "image"}),
                ):
                    assert client.request_view(view)
                    assert not client.request_view("both")
                    frame = await asyncio.to_thread(wait_for_frame, client, view)
                    assert set(frame.arrays) == arrays
                    assert frame.generation > generation
                    assert frame.header["config"]["points"] == 32
                    assert frame.header["config"]["width"] == 8
                    assert not client.view_pending
                    assert client.view_error is None
                    generation = frame.generation
                    if mode == "replay":
                        assert frame.receive_age_ms is None
                        assert client.metadata["config"]["view"] == view
            finally:
                await asyncio.to_thread(client.close)

    asyncio.run(exercise())


def test_request_is_nonblocking_and_failure_releases_controls(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def failing_request(url, data, **kwargs):
        calls.append(data)
        entered.set()
        assert release.wait(2)
        raise OSError("source unavailable")

    monkeypatch.setattr("plotbench.client.request", failing_request)
    client = FrameSource("http://localhost")
    try:
        assert client.request_view("image")
        assert entered.wait(1)
        assert client.view_pending
        assert not client.request_view("waveform")
        release.set()
        client._view_thread.join(2)
        assert not client.view_pending
        assert "source unavailable" in client.view_error
        assert calls == [{"view": "image"}]
        monkeypatch.setattr(
            "plotbench.client.request",
            lambda *args, **kwargs: json.dumps({"view": "waveform", "generation": 1}),
        )
        assert client.request_view("waveform")
        client._view_thread.join(2)
        assert client.view_pending  # HTTP acceptance alone does not complete the switch.
        client._publish(decode_frame(make_packet(Config(view="waveform", generation=1), 0)))
        assert not client.view_pending
        assert client.view_error is None
    finally:
        release.set()
        client.close()
    assert not client.request_view("both")


def test_controls_reject_an_empty_or_unknown_plot_selection():
    client = FrameSource("http://localhost")
    with pytest.raises(ValueError, match="view must be"):
        client.request_view("none")
    assert not client.view_pending


def test_stream_frame_can_arrive_before_the_http_acknowledgement(monkeypatch):
    client = FrameSource("http://localhost")

    def fast_source(*args, **kwargs):
        client._publish(decode_frame(make_packet(Config(view="image", generation=1), 0)))
        return json.dumps({"view": "image", "generation": 1})

    monkeypatch.setattr("plotbench.client.request", fast_source)
    try:
        assert client.request_view("image")
        client._view_thread.join(2)
        assert not client.view_pending
        assert set(client.take_latest().arrays) == {"image"}
    finally:
        client.close()
