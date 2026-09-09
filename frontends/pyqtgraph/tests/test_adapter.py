from types import SimpleNamespace

import numpy as np
import pytest
from plotbench.config import Config
from plotbench.palette import colorize
from plotbench.protocol import Frame
from pyqtgraph.graphicsItems.PlotDataItem import PlotDataset
from qtpy.QtCore import QLineF, Qt
from qtpy.QtGui import QImage, QPainter
from qtpy.QtWidgets import QApplication

from plotbench_pyqtgraph import app


class Source:
    error = None
    status = "Test source"
    view_pending = False
    view_error = None

    def __init__(self, *args):
        self.frame = None
        self.metadata = {}

    def start(self):
        return None

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
        self.samples.append((frame, update_ms))

    def mark_stopped(self, reason=None):
        return None

    def close(self):
        return None


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, monkeypatch):
    monkeypatch.setattr(app, "FrameSource", Source)
    monkeypatch.setattr(app, "MetricsSink", Sink)
    app.pg.setConfigOptions(useOpenGL=False, enableExperimental=False, antialias=False)
    args = SimpleNamespace(
        url="http://localhost",
        mode="stream",
        run_id="test",
        duration=0,
        width=800,
        height=600,
        opengl=False,
    )
    window = app.PlotWindow(args)
    yield window
    window.close()


@pytest.mark.parametrize("waveform_mode", ["replace", "append"])
def test_dropped_frame_replaces_complete_authoritative_window(window, waveform_mode):
    config = Config(
        points=8, append_count=2, view="waveform", waveform_mode=waveform_mode
    ).to_dict()
    for seq in (0, 4):
        waveform = np.arange(8, dtype=np.float32) / 10 + seq / 100
        window.source.frame = Frame(
            {"seq": seq, "generation": 0, "config": config}, {"waveform": waveform}
        )
        window.poll_frame()
        x, y = window.curve.getData()
        np.testing.assert_array_equal(x, np.arange(8))
        np.testing.assert_array_equal(y, waveform)
    assert window.error is None
    assert len(window.sink.samples) == 2
    assert window.curve.opts["autoDownsample"] is False


def test_image_switches_rgb_scalar_and_resolution(window):
    for generation, image_mode, shape in [
        (0, "scalar", (4, 5)),
        (1, "rgb", (6, 7, 3)),
        (2, "scalar", (3, 2)),
    ]:
        config = Config(
            width=shape[1], height=shape[0], view="image", image_mode=image_mode
        ).to_dict()
        image = np.ones(shape, dtype=np.uint8 if image_mode == "rgb" else np.float32)
        window.source.frame = Frame(
            {"seq": 0, "generation": generation, "config": config}, {"image": image}
        )
        window.poll_frame()
        expected = image if image_mode == "rgb" else np.full(shape, 255, dtype=np.uint8)
        np.testing.assert_array_equal(window.image_item.image, expected)
        assert (window.image_item.lut is None) == (image_mode == "rgb")
    assert window.error is None


def test_fixed_finite_waveform_skips_dynamic_range_bounds_scan(window, monkeypatch):
    def unexpected_bounds_scan(*args):
        raise AssertionError("Fixed finite waveform should not use dynamic-range bounds scanning")

    monkeypatch.setattr(PlotDataset, "_getArrayBounds", unexpected_bounds_scan)
    config = Config(points=8, append_count=2, view="waveform").to_dict()
    for seq in (0, 1):
        values = np.linspace(-1, 1, 8, dtype=np.float32)
        window.source.frame = Frame(
            {"seq": seq, "generation": 0, "config": config}, {"waveform": values}
        )
        window.poll_frame()
        assert window.error is None
        np.testing.assert_array_equal(window.curve.getData()[1], values)
    assert window.curve.opts["dynamicRangeLimit"] is None
    assert len(window.sink.samples) == 2


def test_hud_records_current_qt_screen_and_renderer_environment(window, monkeypatch):
    monkeypatch.setenv("QSG_RENDER_LOOP", "basic")
    monkeypatch.setattr(window.sink, "snapshot", dict, raising=False)
    monkeypatch.setattr(window.dashboard, "update_metrics", lambda *args: None)
    window.update_hud()
    assert window.metadata["versions"]["numpy"] == np.__version__
    assert window.metadata["display"]["name"] == window.screen().name()
    assert window.metadata["display"]["refresh_hz"] == window.screen().refreshRate()
    assert window.metadata["display"]["window_device_pixel_ratio"] == window.devicePixelRatioF()
    assert window.metadata["renderer_environment"]["QSG_RENDER_LOOP"] == "basic"
    assert window.metadata["qt_platform_plugin"] == QApplication.platformName()
    assert window.metadata["plot_viewport_units"].startswith("physical pixels")


@pytest.mark.parametrize("pixel_ratio", [1, 2])
def test_cosmetic_waveform_pen_is_one_physical_pixel(window, pixel_ratio):
    image = QImage(40, 40, QImage.Format.Format_RGB32)
    image.setDevicePixelRatio(pixel_ratio)
    image.fill(Qt.GlobalColor.black)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.setPen(window.curve.opts["pen"])
    painter.drawLine(QLineF(2, 5, 14, 5))
    painter.end()
    painted_rows = [
        y for y in range(image.height()) if image.pixelColor(8 * pixel_ratio, y).green() > 0
    ]
    assert len(painted_rows) == 1


def test_native_image_lut_matches_protocol_at_every_index_boundary(window):
    boundaries = np.arange(256, dtype=np.float32) / 255
    values = np.concatenate(
        [
            np.array([-0.1, 0.5, 0.999, 1.1], dtype=np.float32),
            boundaries,
            np.nextafter(boundaries, np.float32(-np.inf)),
            np.nextafter(boundaries, np.float32(np.inf)),
        ]
    )[None, :]
    config = Config(width=values.shape[1], height=1, view="image", image_mode="scalar").to_dict()
    window.source.frame = Frame({"seq": 0, "generation": 0, "config": config}, {"image": values})
    window.poll_frame()
    window.image_item.render()
    actual = np.array(
        [[window.image_item.qimage.pixelColor(x, 0).getRgb()[:3] for x in range(values.shape[1])]],
        dtype=np.uint8,
    )
    np.testing.assert_array_equal(actual, colorize(values))
