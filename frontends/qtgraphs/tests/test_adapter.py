from types import SimpleNamespace

import numpy as np
import pytest
from plotbench.config import Config
from plotbench.palette import colorize
from plotbench.protocol import Frame
from qtpy.QtCore import QSize
from qtpy.QtGui import QGuiApplication

from plotbench_qtgraphs import app


class Source:
    error = None
    status = "Test source"
    view_pending = False
    view_error = None

    def __init__(self, *args):
        self.frame = None
        self.metadata = {}
        self.requests = []

    def request_view(self, view):
        self.requests.append(view)
        self.view_pending = True
        return True

    def close(self):
        return None

    def take_latest(self):
        frame, self.frame = self.frame, None
        return frame


class Sink:
    error = None

    def __init__(self, *args, metadata, expected_duration):
        self.metadata = metadata
        self.samples = []

    def record(self, frame, update_ms, **extra):
        self.samples.append((frame, update_ms, extra))

    def mark_stopped(self, reason=None):
        return None

    def close(self):
        return None


@pytest.fixture(scope="module")
def qapp():
    return QGuiApplication.instance() or QGuiApplication([])


def test_provider_owns_rgb_data_and_respects_requested_size(qapp):
    provider = app.FrameImageProvider()
    rgb = np.full((3, 5, 3), [12, 34, 56], dtype=np.uint8)
    provider.update_image(rgb)
    rgb.fill(0)
    size = QSize()
    image = provider.requestImage("frame", size, QSize())
    assert size == QSize(5, 3)
    assert image.pixelColor(0, 0).getRgb() == (12, 34, 56, 255)
    resized = provider.requestImage("frame", size, QSize(10, 6))
    assert resized.size() == QSize(10, 6)
    assert size == QSize(5, 3)


def test_scalar_provider_uses_shared_fixed_lut(qapp):
    provider = app.FrameImageProvider()
    scalar = np.array([[0.0, 0.5, 1.0]], dtype=np.float32)
    provider.update_image(scalar)
    image = provider.requestImage("frame", QSize(), QSize())
    expected = colorize(scalar)
    for x in range(3):
        assert image.pixelColor(x, 0).getRgb()[:3] == tuple(expected[0, x])


@pytest.mark.parametrize("waveform_mode", ["replace", "append"])
def test_controller_replaces_native_series_after_skipped_input(qapp, monkeypatch, waveform_mode):
    monkeypatch.setattr(app, "FrameSource", Source)
    monkeypatch.setattr(app, "MetricsSink", Sink)
    args = SimpleNamespace(url="http://localhost", mode="stream", run_id="test", duration=0)
    controller = app.Controller(args, app.FrameImageProvider())
    controller.series = app.QLineSeries()
    config = Config(
        points=8, append_count=2, view="waveform", waveform_mode=waveform_mode
    ).to_dict()
    for seq in (0, 4):
        y = np.arange(8, dtype=np.float32) / 10 + seq / 100
        controller.source.frame = Frame(
            {"seq": seq, "generation": 0, "config": config}, {"waveform": y}
        )
        controller.poll_frame()
        assert controller.series.count() == 8
        np.testing.assert_allclose([controller.series.at(i).y() for i in range(8)], y)
    assert controller.error is None
    assert len(controller.sink.samples) == 2
    controller.close()


@pytest.fixture
def controller(qapp, monkeypatch):
    monkeypatch.setattr(app, "FrameSource", Source)
    monkeypatch.setattr(app, "MetricsSink", Sink)
    args = SimpleNamespace(url="http://localhost", mode="stream", run_id="test", duration=0)
    controller = app.Controller(args, app.FrameImageProvider())
    yield controller
    controller.close()


@pytest.mark.parametrize(
    "initial, clicked, expected",
    [
        ("both", "image", "waveform"),
        ("both", "waveform", "image"),
        ("waveform", "image", "both"),
        ("image", "waveform", "both"),
    ],
)
def test_toggle_requests_view_and_retains_frame_state_while_pending(
    controller, initial, clicked, expected
):
    controller._config = Config(view=initial).to_dict()
    controller.toggle_plot(clicked)
    assert controller.source.requests == [expected]
    assert not controller.plotControls["waveformEnabled"]
    assert not controller.plotControls["imageEnabled"]
    assert controller.plotControls["waveformChecked"] == (initial in ("both", "waveform"))
    assert controller.plotControls["imageChecked"] == (initial in ("both", "image"))
    controller.toggle_plot(clicked)
    assert controller.source.requests == [expected]
    controller.source.view_pending = False
    controller.source.frame = Frame(
        {"seq": 0, "generation": 1, "config": Config(view=expected).to_dict()}, {}
    )
    controller.poll_frame()
    assert controller.plotControls["waveformEnabled"] == (expected != "waveform")
    assert controller.plotControls["imageEnabled"] == (expected != "image")
    assert controller.plotControls["waveformChecked"] == (expected in ("both", "waveform"))
    assert controller.plotControls["imageChecked"] == (expected in ("both", "image"))
    assert controller.source.requests == [expected]


@pytest.mark.parametrize("view", ["waveform", "image"])
def test_last_plot_guard(controller, view):
    controller._config = Config(view=view).to_dict()
    assert not controller.plotControls[view + "Enabled"]
    controller.toggle_plot(view)
    assert controller.source.requests == []


def test_control_locks_and_failure_state(controller):
    controller.toggle_plot("image")
    assert not controller.plotControls["imageEnabled"]
    controller._config = Config(view="both").to_dict()
    controller.args.duration = 10
    controller.toggle_plot("image")
    assert "Locked during recorded runs" in controller.plotControls["imageTooltip"]
    assert controller.source.requests == []
    controller.args.duration = 0
    controller.source.view_pending = True
    controller.toggle_plot("image")
    assert controller.source.requests == []
    controller.source.view_pending = False
    controller.source.view_error = "Source unavailable"
    assert controller.plotControls["imageEnabled"]
    assert controller.plotControls["imageChecked"]
    assert "Source unavailable" in controller.plotControls["imageTooltip"]


@pytest.mark.parametrize("mode", ["stream", "replay"])
def test_metric_targets_follow_received_rate_and_replay_has_no_age(controller, mode):
    controller.args.mode = mode
    assert controller.metricTargets["submitted"] == "(waiting for source)"
    assert controller.metricTargets["update"] == "(waiting for source)"
    for generation, (hz, period) in enumerate([(30, "33.33"), (120, "8.33"), (59.94, "16.68")]):
        controller.source.frame = Frame(
            {"seq": 0, "generation": generation, "config": Config(hz=hz).to_dict()}, {}
        )
        controller.poll_frame()
        expected_age = "(N/A in replay)" if mode == "replay" else f"(goal <{period} ms)"
        assert controller.metricTargets == {
            "submitted": f"(target {hz:g}/s)",
            "update": f"(budget ≤{period} ms)",
            "skipped": "(target 0)",
            "age": expected_age,
        }
    assert "deferred GPU" in controller.metricGuide
    assert "indicative" in controller.metricGuide
