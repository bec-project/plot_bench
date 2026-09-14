from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from plotbench.config import Config
from plotbench.palette import CURVE_COLORS, colorize
from plotbench.protocol import Frame
from qtpy.QtCore import QObject, QSize, QUrl
from qtpy.QtGui import QGuiApplication
from qtpy.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from qtpy.QtQuick import QQuickItem
from qtpy.QtQuickControls2 import QQuickStyle

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
        self.samples.append((frame, update_ms, extra))

    def snapshot(self):
        return {
            "updates_hz": 0.0,
            "update_ms": 0.0,
            "skipped": 0,
            "receive_age_ms": None,
            "count": 0,
        }

    def mark_stopped(self, reason=None):
        return None

    def close(self):
        return None


def plot_tree(plots, curves, images=1):
    """Headless stand-in for the QML object tree: named series plus first-plot placeholders."""
    root = QObject()
    for p in range(plots):
        for c in range(curves):
            app.QLineSeries(root).setObjectName(f"waveformSeries-{p}-{c}")
    if plots:
        QObject(root).setObjectName("waveformGraph-0")
    if images:
        QObject(root).setObjectName("streamImage-0")
    return root


def waveform_frame(config, seq, generation=0):
    """Distinct values per plot and curve: value = curve + plot/10 + sample/100 + seq/1000."""
    plots, curves, points = config["waveform_plots"], config["curves"], config["points"]
    y = np.empty((plots, curves, points), dtype=np.float32)
    for p in range(plots):
        for c in range(curves):
            y[p, c] = c + p / 10 + np.arange(points) / 100 + seq / 1000
    return Frame({"seq": seq, "generation": generation, "config": config}, {"waveform": y})


@pytest.fixture(scope="module")
def qapp():
    return QGuiApplication.instance() or QGuiApplication([])


def test_provider_owns_rgb_data_and_respects_requested_size(qapp):
    provider = app.FrameImageProvider()
    rgb = np.full((3, 5, 3), [12, 34, 56], dtype=np.uint8)
    provider.update_image(0, rgb)
    rgb.fill(0)
    size = QSize()
    image = provider.requestImage("0/1/7", size, QSize())
    assert size == QSize(5, 3)
    assert image.pixelColor(0, 0).getRgb() == (12, 34, 56, 255)
    resized = provider.requestImage("0/1/7", size, QSize(10, 6))
    assert resized.size() == QSize(10, 6)
    assert size == QSize(5, 3)


def test_scalar_provider_uses_shared_fixed_lut(qapp):
    provider = app.FrameImageProvider()
    scalar = np.array([[0.0, 0.5, 1.0]], dtype=np.float32)
    provider.update_image(0, scalar)
    image = provider.requestImage("0/0/0", QSize(), QSize())
    expected = colorize(scalar)
    for x in range(3):
        assert image.pixelColor(x, 0).getRgb()[:3] == tuple(expected[0, x])


def test_provider_keeps_one_image_per_plot(qapp):
    provider = app.FrameImageProvider()
    provider.update_image(2, np.full((2, 3, 3), [9, 8, 7], dtype=np.uint8))
    provider.update_image(0, np.full((4, 1, 3), [1, 2, 3], dtype=np.uint8))
    size = QSize()
    assert provider.requestImage("2/0/0", size, QSize()).pixelColor(0, 0).getRgb()[:3] == (9, 8, 7)
    assert size == QSize(3, 2)
    assert provider.requestImage("0/5/5", size, QSize()).pixelColor(0, 0).getRgb()[:3] == (1, 2, 3)
    assert size == QSize(1, 4)
    for missing in ("1/0/0", "7/0/0", "frame"):
        assert provider.requestImage(missing, size, QSize()).isNull()
        assert size == QSize(0, 0)


@pytest.mark.parametrize("count, columns", [(1, 1), (2, 2), (3, 2), (4, 2), (5, 3), (6, 3), (9, 3)])
def test_grid_columns_follow_shared_layout_rule(count, columns):
    assert app.grid_columns(count) == columns


def test_plural():
    assert app.plural(1, "plot") == "1 plot"
    assert app.plural(3, "curve") == "3 curves"


def test_iter_objects_visits_each_object_once(qapp):
    root = QQuickItem()
    child = QQuickItem(root)  # QObject child *and* Qt Quick child item
    child.setParentItem(root)
    loose = QQuickItem()  # Qt Quick child item only, like a Repeater delegate
    loose.setParentItem(root)
    grandchild = QObject(loose)
    objects = list(app.iter_objects(root))
    assert len(objects) == 4
    assert {id(o) for o in objects} == {id(root), id(child), id(loose), id(grandchild)}


def test_plot_titles():
    assert app.plot_titles("Waveform", 1) == ["Waveform"]
    assert app.plot_titles("Image", 3) == ["Image 1", "Image 2", "Image 3"]
    assert app.plot_titles("Image", 0) == []


@pytest.fixture
def make_controller(qapp, monkeypatch):
    monkeypatch.setattr(app, "FrameSource", Source)
    monkeypatch.setattr(app, "MetricsSink", Sink)
    controllers = []

    def make(**args):
        args = {
            "url": "http://localhost",
            "mode": "stream",
            "run_id": "test",
            "duration": 0,
            **args,
        }
        controller = app.Controller(SimpleNamespace(**args), app.FrameImageProvider())
        controllers.append(controller)
        return controller

    yield make
    for controller in controllers:
        controller.close()


@pytest.fixture
def controller(make_controller):
    controller = make_controller()
    controller.window = plot_tree(1, 1)
    return controller


@pytest.mark.parametrize("waveform_mode", ["replace", "append"])
def test_controller_replaces_native_series_after_skipped_input(controller, waveform_mode):
    config = Config(
        points=8, append_count=2, view="waveform", waveform_mode=waveform_mode
    ).to_dict()
    for seq in (0, 4):
        y = np.arange(8, dtype=np.float32) / 10 + seq / 100
        controller.source.frame = Frame(
            {"seq": seq, "generation": 0, "config": config}, {"waveform": y.reshape(1, 1, 8)}
        )
        controller.poll_frame()
        series = controller.series[0][0]
        assert series.count() == 8
        np.testing.assert_allclose([series.at(i).y() for i in range(8)], y)
    assert controller.error is None
    assert len(controller.sink.samples) == 2
    assert controller.sink.metadata["plot_counts"] == {"waveform": 1, "image": 0}
    assert controller.sink.metadata["curves"] == 1
    controller.close()


def test_every_series_receives_its_plot_and_curve_slice(make_controller):
    controller = make_controller()
    controller.window = plot_tree(2, 3, images=0)
    config = Config(points=6, append_count=2, view="waveform", curves=3, waveform_plots=2).to_dict()
    for seq in (0, 1):
        frame = waveform_frame(config, seq)
        controller.source.frame = frame
        controller.poll_frame()
        assert controller.error is None
        assert [len(row) for row in controller.series] == [3, 3]
        for p in range(2):
            for c in range(3):
                series = controller.series[p][c]
                assert series.objectName() == f"waveformSeries-{p}-{c}"
                assert series.count() == 6
                np.testing.assert_allclose(
                    [series.at(i).y() for i in range(6)], frame.arrays["waveform"][p, c]
                )
                np.testing.assert_allclose([series.at(i).x() for i in range(6)], np.arange(6))
    assert len(controller.sink.samples) == 2
    assert controller.sink.metadata["plot_counts"] == {"waveform": 2, "image": 0}
    assert controller.sink.metadata["curves"] == 3


def test_missing_series_fails_loudly(make_controller, monkeypatch):
    controller = make_controller()
    controller.window = plot_tree(2, 2)
    config = Config(points=4, append_count=1, view="waveform", curves=3, waveform_plots=2).to_dict()
    controller.source.frame = waveform_frame(config, 0)
    # update_hud needs a real window; only the loud failure itself is under test here.
    monkeypatch.setattr(controller, "update_hud", lambda: None)
    controller.poll_frame()
    assert "waveformSeries-0-2" in controller.error
    assert controller.sink.samples == []


def test_images_are_converted_per_plot_and_addressed_by_plot_index(make_controller):
    controller = make_controller()
    controller.window = plot_tree(1, 1)
    config = Config(width=3, height=2, image_plots=3, image_mode="rgb").to_dict()
    images = np.zeros((3, 2, 3, 3), dtype=np.uint8)
    for p in range(3):
        images[p] = [p * 10, p * 10 + 1, p * 10 + 2]
    waveform = np.zeros((1, 1, config["points"]), dtype=np.float32)
    controller.source.frame = Frame(
        {"seq": 5, "generation": 2, "config": config}, {"waveform": waveform, "image": images}
    )
    controller.poll_frame()
    assert controller.error is None
    assert controller.imageUrls == [f"image://frames/{p}/2/5" for p in range(3)]
    size = QSize()
    for p in range(3):
        image = controller.provider.requestImage(f"{p}/2/5", size, QSize())
        assert size == QSize(3, 2)
        assert image.pixelColor(2, 1).getRgb()[:3] == (p * 10, p * 10 + 1, p * 10 + 2)
    assert controller.sink.metadata["plot_counts"] == {"waveform": 1, "image": 3}
    ((_, _, extra),) = controller.sink.samples
    assert extra["conversion_ms"] >= 0


def test_workload_summary_and_subtitles_follow_plot_counts(controller):
    assert controller.workload["waveformSubtitle"] == "Waiting for source"
    assert controller.waveformPlots == 1 and controller.imagePlots == 1 and controller.curves == 1
    assert controller.gridColumns == 2
    assert controller.waveformTitles == ["Waveform"] and controller.imageTitles == ["Image"]
    controller._config = Config().to_dict()
    assert controller.workload["waveform"] == "10,000 · replace"
    assert controller.workload["image"] == "512 × 512 · scalar"
    assert controller.workload["waveformSubtitle"] == "10,000 points · replace"
    controller._config = Config(
        curves=3, waveform_plots=2, image_plots=3, waveform_mode="append", image_mode="rgb"
    ).to_dict()
    assert controller.workload["waveform"] == "10,000 · append · 2 plots × 3 curves"
    assert controller.workload["image"] == "512 × 512 · RGB · 3 plots"
    assert controller.workload["waveformSubtitle"] == "10,000 points · append · 3 curves"
    assert controller.workload["imageSubtitle"] == "512 × 512 · RGB"
    assert controller.waveformTitles == ["Waveform 1", "Waveform 2"]
    assert controller.imageTitles == ["Image 1", "Image 2", "Image 3"]
    assert controller.gridColumns == 3
    controller._config = Config(
        curves=2, waveform_plots=4, view="waveform", image_plots=3
    ).to_dict()
    assert controller.workload["waveform"] == "10,000 · replace · 4 plots × 2 curves"
    assert controller.workload["image"] == "512 × 512 · scalar · 3 plots"
    assert controller.waveformPlots == 4 and controller.imagePlots == 0
    controller._config = Config(curves=3, waveform_plots=1).to_dict()
    assert controller.workload["waveform"] == "10,000 · replace · 1 plot × 3 curves"
    controller._config = Config(curves=1, waveform_plots=4).to_dict()
    assert controller.workload["waveform"] == "10,000 · replace · 4 plots × 1 curve"
    controller._config = Config(
        curves=2, waveform_plots=4, view="waveform", image_plots=3
    ).to_dict()
    assert controller.imageTitles == []
    assert controller.gridColumns == 2
    controller._config = Config(view="image", waveform_plots=5, image_plots=1).to_dict()
    assert controller.waveformPlots == 0 and controller.imagePlots == 1
    assert controller.gridColumns == 1
    assert controller.curveColors == list(CURVE_COLORS)


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
    assert controller.error is None
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
def test_metric_targets_follow_received_rate_and_replay_has_no_age(make_controller, mode):
    controller = make_controller(mode=mode)
    controller.window = plot_tree(1, 1)
    assert controller.metricTargets["submitted"] == "(waiting for source)"
    assert controller.metricTargets["update"] == "(waiting for source)"
    for generation, (hz, period) in enumerate([(30, "33.33"), (120, "8.33"), (59.94, "16.68")]):
        controller.source.frame = Frame(
            {"seq": 0, "generation": generation, "config": Config(hz=hz).to_dict()}, {}
        )
        controller.poll_frame()
        assert controller.error is None
        expected_age = "(N/A in replay)" if mode == "replay" else f"(goal <{period} ms)"
        assert controller.metricTargets == {
            "submitted": f"(target {hz:g}/s)",
            "update": f"(budget ≤{period} ms)",
            "skipped": "(target 0)",
            "age": expected_age,
        }
    assert "deferred GPU" in controller.metricGuide
    assert "indicative" in controller.metricGuide


def qml_eval(obj, expression):
    value, undefined = QQmlExpression(QQmlEngine.contextForObject(obj), obj, expression).evaluate()
    assert not undefined, expression
    return value


@pytest.fixture
def qml_window(make_controller):
    controller = make_controller()
    controller._config = Config(curves=3, waveform_plots=2, image_plots=3).to_dict()
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda entries: warnings.extend(w.toString() for w in entries))
    engine.addImageProvider("frames", controller.provider)
    engine.rootContext().setContextProperty("benchmark", controller)
    engine.load(QUrl.fromLocalFile(str(Path(app.__file__).with_name("Main.qml"))))
    assert engine.rootObjects(), warnings
    window = engine.rootObjects()[0]
    yield controller, window, warnings
    window.close()
    del window
    del engine  # destroys the QML tree while the controller it binds to is still alive


def test_qml_builds_series_and_images_per_plot(qml_window):
    controller, window, warnings = qml_window
    assert warnings == []
    named = app.named_objects(window)
    assert named["plotGrid"].property("columns") == 3
    for p in range(2):
        assert named[f"waveformGraph-{p}"].metaObject().className() == "QGraphsView"
        for c in range(3):
            series = named[f"waveformSeries-{p}-{c}"]
            assert isinstance(series, app.QLineSeries)
            assert series.color().name() == CURVE_COLORS[c]
    assert "waveformSeries-0-3" not in named and "waveformGraph-2" not in named
    for p in range(3):
        assert named[f"streamImage-{p}"].metaObject().className() == "QQuickImage"
    assert "streamImage-3" not in named
    assert named["waveformToggle"].property("checked") and named["imageToggle"].property("checked")
    controller.start(window)
    assert [[s.objectName() for s in row] for row in controller.series] == [
        [f"waveformSeries-{p}-{c}" for c in range(3)] for p in range(2)
    ]
    assert controller.first_graph is named["waveformGraph-0"]
    assert controller.first_image is named["streamImage-0"]
    assert warnings == []


def test_qml_rebuilds_plots_when_the_generation_changes(qml_window):
    controller, window, warnings = qml_window
    controller.start(window)
    config = Config(
        points=16, append_count=4, curves=2, waveform_plots=3, image_plots=1, width=8, height=6
    ).to_dict()
    frame = waveform_frame(config, seq=3, generation=1)
    frame.arrays["image"] = np.linspace(0, 1, 6 * 8, dtype=np.float32).reshape(1, 6, 8)
    controller.source.frame = frame
    controller.poll_frame()
    assert controller.error is None
    named = app.named_objects(window)
    assert named["plotGrid"].property("columns") == 2
    assert [[s.objectName() for s in row] for row in controller.series] == [
        [f"waveformSeries-{p}-{c}" for c in range(2)] for p in range(3)
    ]
    assert "waveformSeries-0-2" not in named and "streamImage-1" not in named
    for p in range(3):
        for c in range(2):
            series = named[f"waveformSeries-{p}-{c}"]
            assert series is controller.series[p][c]
            assert series.count() == 16
            np.testing.assert_allclose(
                [series.at(i).y() for i in range(16)], frame.arrays["waveform"][p, c]
            )
    image = named["streamImage-0"]
    assert image.property("source").toString() == "image://frames/0/1/3"
    assert qml_eval(image, "status === Image.Ready")  # loaded synchronously from the provider
    assert image.property("sourceSize") == QSize(8, 6)
    assert controller.sink.metadata["plot_counts"] == {"waveform": 3, "image": 1}
    assert controller.sink.metadata["curves"] == 2
    assert warnings == []
