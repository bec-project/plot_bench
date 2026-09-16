from types import SimpleNamespace

import numpy as np
import pytest
from plotbench.config import Config
from plotbench.palette import CURVE_COLORS, colorize
from plotbench.protocol import Frame
from pyqtgraph.graphicsItems.PlotDataItem import PlotDataset
from qtpy.QtCore import QLineF, Qt
from qtpy.QtGui import QImage, QPainter
from qtpy.QtWidgets import QApplication

from plotbench_pyqtgraph import app
from plotbench_pyqtgraph.dashboard import grid_shape


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
        waveform = (np.arange(8, dtype=np.float32) / 10 + seq / 100).reshape(1, 1, 8)
        window.source.frame = Frame(
            {"seq": seq, "generation": 0, "config": config}, {"waveform": waveform}
        )
        window.poll_frame()
        x, y = window.curve.getData()
        np.testing.assert_array_equal(x, np.arange(8))
        np.testing.assert_array_equal(y, waveform[0, 0])
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
        image = np.ones((1, *shape), dtype=np.uint8 if image_mode == "rgb" else np.float32)
        window.source.frame = Frame(
            {"seq": 0, "generation": generation, "config": config}, {"image": image}
        )
        window.poll_frame()
        expected = image[0] if image_mode == "rgb" else np.full(shape, 255, dtype=np.uint8)
        np.testing.assert_array_equal(window.image_item.image, expected)
        assert (window.image_item.lut is None) == (image_mode == "rgb")
    assert window.error is None


def test_fixed_finite_waveform_skips_dynamic_range_bounds_scan(window, monkeypatch):
    def unexpected_bounds_scan(*args):
        raise AssertionError("Fixed finite waveform should not use dynamic-range bounds scanning")

    monkeypatch.setattr(PlotDataset, "_getArrayBounds", unexpected_bounds_scan)
    config = Config(points=8, append_count=2, view="waveform").to_dict()
    for seq in (0, 1):
        values = np.linspace(-1, 1, 8, dtype=np.float32).reshape(1, 1, 8)
        window.source.frame = Frame(
            {"seq": seq, "generation": 0, "config": config}, {"waveform": values}
        )
        window.poll_frame()
        assert window.error is None
        np.testing.assert_array_equal(window.curve.getData()[1], values[0, 0])
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
    )[None, None, :]
    config = Config(width=values.shape[2], height=1, view="image", image_mode="scalar").to_dict()
    window.source.frame = Frame({"seq": 0, "generation": 0, "config": config}, {"image": values})
    window.poll_frame()
    window.image_item.render()
    actual = np.array(
        [[window.image_item.qimage.pixelColor(x, 0).getRgb()[:3] for x in range(values.shape[2])]],
        dtype=np.uint8,
    )
    np.testing.assert_array_equal(actual, colorize(values[0]))


def submit(window, config, generation=0, seq=0):
    """Feed one synthetic frame whose arrays have the protocol v2 shapes for `config`."""
    arrays = {}
    if config["view"] != "image":
        shape = (config["waveform_plots"], config["curves"], config["points"])
        arrays["waveform"] = np.arange(np.prod(shape), dtype=np.float32).reshape(shape) / 100
    if config["view"] != "waveform":
        shape = (config["image_plots"], config["height"], config["width"])
        if config["image_mode"] == "rgb":
            shape += (3,)
        dtype = np.uint8 if config["image_mode"] == "rgb" else np.float32
        arrays["image"] = (np.arange(np.prod(shape)) % 251).astype(dtype).reshape(shape)
        if dtype is np.float32:
            arrays["image"] /= 250
    window.source.frame = Frame({"seq": seq, "generation": generation, "config": config}, arrays)
    window.poll_frame()
    assert window.error is None
    return arrays


def test_multi_plot_frame_updates_every_curve_of_every_plot_with_its_slice(window):
    config = Config(points=6, append_count=1, curves=3, waveform_plots=2, view="waveform").to_dict()
    arrays = submit(window, config)
    waveform = arrays["waveform"]
    assert len(window.curves) == 2 and all(len(curves) == 3 for curves in window.curves)
    assert window.image_plots == [] and window.image_items == []
    for plot_index, curves in enumerate(window.curves):
        for curve_index, curve in enumerate(curves):
            x, y = curve.getData()
            np.testing.assert_array_equal(x, np.arange(6))
            np.testing.assert_array_equal(y, waveform[plot_index, curve_index])
            assert np.shares_memory(curve.yData, waveform), "curves must hold NumPy views"
            assert curve.opts["pen"].color().name() == CURVE_COLORS[curve_index % 8]
            assert curve.opts["autoDownsample"] is False
            assert curve.opts["dynamicRangeLimit"] is None
    assert [card.title.text() for card in window.waveform_cards] == ["Waveform 1", "Waveform 2"]
    assert all(
        card.subtitle.text() == "6 points · replace · 3 curves" for card in window.waveform_cards
    )
    for plot in window.waveform_plots:
        assert plot.getViewBox().viewRange() == [[0, 5], [-1.5, 1.5]]
    assert len(window.sink.samples) == 1


def test_count_changes_rebuild_widgets_and_reuse_survivors(window):
    config = Config(
        points=4, append_count=1, curves=2, waveform_plots=2, image_plots=2, width=3, height=2
    )
    submit(window, config.to_dict(), generation=0)
    first_waveform, first_image = window.waveform_plots[0], window.image_plots[0]
    second_waveform_card = window.waveform_cards[1]
    first_curves = list(window.curves[0])
    assert window.dashboard.plots.count() == 4

    config = config.updated({"waveform_plots": 3, "curves": 1, "image_plots": 1})
    submit(window, config.to_dict(), generation=config.generation)
    assert window.waveform_plots[0] is first_waveform
    assert window.image_plots == [first_image]
    assert len(window.waveform_plots) == 3 and len(window.curves) == 3
    assert all(len(curves) == 1 for curves in window.curves)
    assert window.curves[0] == [first_curves[0]]
    assert first_curves[1] not in first_waveform.getPlotItem().listDataItems()
    assert second_waveform_card is window.waveform_cards[1]
    assert window.dashboard.plots.count() == 4
    assert [card.title.text() for card in window.waveform_cards] == [
        "Waveform 1",
        "Waveform 2",
        "Waveform 3",
    ]
    assert window.image_cards[0].title.text() == "Image"
    assert window.waveform_cards[0].subtitle.text() == "4 points · replace"

    config = config.updated({"waveform_plots": 1, "curves": 4, "view": "waveform"})
    submit(window, config.to_dict(), generation=config.generation)
    assert window.waveform_plots == [first_waveform]
    assert len(window.curves[0]) == 4 and window.curves[0][0] is first_curves[0]
    assert window.image_plots == [] and window.image_item is None
    assert window.dashboard.plots.count() == 1
    assert window.waveform_cards[0].title.text() == "Waveform"
    assert not second_waveform_card.isVisible() and second_waveform_card.parent() is None

    config = config.updated({"view": "image", "image_plots": 3})
    submit(window, config.to_dict(), generation=config.generation)
    assert window.waveform_plots == [] and window.curve is None and window.waveform is None
    assert len(window.image_plots) == 3 and window.dashboard.plots.count() == 3
    assert [card.title.text() for card in window.image_cards] == ["Image 1", "Image 2", "Image 3"]


@pytest.mark.parametrize("image_mode", ["scalar", "rgb"])
def test_image_plots_receive_their_own_plane_in_both_modes(window, image_mode):
    config = Config(view="image", image_plots=3, width=5, height=4, image_mode=image_mode).to_dict()
    arrays = submit(window, config)
    assert len(window.image_items) == 3
    for plot_index, item in enumerate(window.image_items):
        plane = arrays["image"][plot_index]
        expected = plane if image_mode == "rgb" else (np.clip(plane, 0, 1) * 255).astype(np.uint8)
        np.testing.assert_array_equal(item.image, expected)
        assert item.image.dtype == np.uint8
        assert (item.lut is None) == (image_mode == "rgb")
        if image_mode == "rgb":
            assert np.shares_memory(item.image, arrays["image"])
    assert [card.subtitle.text() for card in window.image_cards] == [
        f"5 × 4 · {'RGB' if image_mode == 'rgb' else 'scalar colormap'}"
    ] * 3


def test_image_plots_switch_scalar_and_rgb_per_generation(window):
    scalar = Config(view="image", image_plots=2, width=3, height=2)
    submit(window, scalar.to_dict(), generation=0)
    items = list(window.image_items)
    assert all(item.lut is not None for item in items)
    rgb = scalar.updated({"image_mode": "rgb"})
    arrays = submit(window, rgb.to_dict(), generation=rgb.generation)
    assert window.image_items == items, "unchanged counts reuse the ImageItems"
    for plot_index, item in enumerate(items):
        assert item.lut is None
        np.testing.assert_array_equal(item.image, arrays["image"][plot_index])


def test_mismatched_frame_shape_is_reported_not_silently_truncated(window, monkeypatch):
    monkeypatch.setattr(window, "update_hud", lambda: None)
    config = Config(points=4, append_count=1, curves=2, waveform_plots=2, view="waveform").to_dict()
    window.source.frame = Frame(
        {"seq": 0, "generation": 0, "config": config},
        {"waveform": np.zeros((2, 1, 4), dtype=np.float32)},
    )
    window.poll_frame()
    assert window.error is not None and "Plot update failed" in window.error
    assert window.sink.samples == []


@pytest.mark.parametrize(
    "count, expected",
    [(1, (1, 1)), (2, (2, 1)), (3, (2, 2)), (4, (2, 2)), (5, (3, 2)), (6, (3, 2)), (9, (3, 3))],
)
def test_grid_shape_follows_shared_layout_rule(count, expected):
    assert grid_shape(count) == expected
    assert grid_shape(0) == (0, 0)


@pytest.mark.parametrize("waveform_plots, image_plots", [(2, 3), (3, 0), (0, 5), (4, 5)])
def test_plots_are_laid_out_row_major_with_equal_stretch(window, waveform_plots, image_plots):
    view = "both" if waveform_plots and image_plots else ("waveform" if waveform_plots else "image")
    config = Config(
        points=4,
        append_count=1,
        waveform_plots=waveform_plots or 1,
        image_plots=image_plots or 1,
        width=3,
        height=2,
        view=view,
    ).to_dict()
    submit(window, config)
    grid = window.dashboard.plots
    cards = window.waveform_cards + window.image_cards
    count = waveform_plots + image_plots
    columns, rows = grid_shape(count)
    assert grid.count() == count == len(cards)
    for index, card in enumerate(cards):
        row, column, row_span, column_span = grid.getItemPosition(grid.indexOf(card))
        assert (row, column, row_span, column_span) == (index // columns, index % columns, 1, 1)
    assert [grid.columnStretch(column) for column in range(grid.columnCount())] == [1] * columns
    assert [grid.rowStretch(row) for row in range(grid.rowCount())] == [1] * rows


def test_hud_records_plot_counts_curves_and_first_plot_viewports(window, monkeypatch):
    monkeypatch.setattr(window.sink, "snapshot", dict, raising=False)
    monkeypatch.setattr(window.dashboard, "update_metrics", lambda *args: None)
    config = Config(
        points=4, append_count=1, curves=3, waveform_plots=2, image_plots=3, width=3, height=2
    )
    submit(window, config.to_dict())
    window.show()
    QApplication.processEvents()
    window.update_hud()
    assert window.metadata["plot_counts"] == {"waveform": 2, "image": 3}
    assert window.metadata["curves"] == 3
    first = window.waveform_plots[0].getViewBox().rect()
    ratio = window.devicePixelRatioF()
    assert window.metadata["plot_viewports"]["waveform"] == [
        first.width() * ratio,
        first.height() * ratio,
    ]
    assert window.metadata["plot_viewports"]["image"] is not None
    config = config.updated({"view": "image"})
    submit(window, config.to_dict(), generation=config.generation)
    window.update_hud()
    assert window.metadata["plot_counts"] == {"waveform": 0, "image": 3}
    assert window.metadata["plot_viewports"]["waveform"] is None


@pytest.mark.parametrize(
    "view,plots,width,height",
    [
        ("waveform", 2, 512, 512),
        ("waveform", 4, 512, 512),
        ("image", 1, 640, 360),
        ("image", 4, 32, 64),
    ],
)
def test_render_contract_measures_every_data_area(
    window, qapp, monkeypatch, view, plots, width, height
):
    from plotbench.render_contract import geometry_errors

    monkeypatch.setattr(window.sink, "snapshot", dict, raising=False)
    monkeypatch.setattr(window.dashboard, "update_metrics", lambda *args: None)
    window.resize(1100, 820)
    config = Config(
        view=view,
        points=16,
        append_count=4,
        waveform_plots=plots,
        image_plots=plots,
        width=width,
        height=height,
    ).to_dict()
    submit(window, config)
    window.show()
    for _ in range(5):
        qapp.processEvents()
    window.update_hud()
    assert geometry_errors(window.metadata, config) == []
    for plot in window.waveform_plots + window.image_plots:
        if plot.getAxis("left").isVisible():
            assert abs(plot.getAxis("left").height() - plot.getViewBox().height()) < 1
            assert abs(plot.getAxis("bottom").width() - plot.getViewBox().width()) < 1

    for card, plot in zip(
        window.waveform_cards + window.image_cards,
        window.waveform_plots + window.image_plots,
        strict=True,
    ):
        assert plot.mapTo(card, plot.rect().bottomRight()).y() <= card.height() - 4
