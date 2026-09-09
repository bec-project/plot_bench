"""Qt Graphs LineSeries and a custom QQuickImageProvider fed by the central source."""

import logging
import os
import platform
import sys
from importlib.metadata import version
from pathlib import Path
from threading import Lock
from time import perf_counter

import numpy as np
import psutil
from plotbench.client import FrameSource, MetricsSink, frontend_parser
from plotbench.palette import colorize
from plotbench.qt_metadata import qt_window_metadata

# qtpy has no QtGraphs wrapper; all other Qt types use qtpy.
from PySide6.QtGraphs import QLineSeries
from qtpy.QtCore import Property, QObject, Qt, QTimer, QUrl, Signal, Slot, qVersion
from qtpy.QtGui import QDesktopServices, QGuiApplication, QImage
from qtpy.QtQml import QQmlApplicationEngine
from qtpy.QtQuick import QQuickImageProvider
from qtpy.QtQuickControls2 import QQuickStyle

logger = logging.getLogger(__name__)
METRIC_GUIDE = "Targets follow the current input frame rate. The update budget is one source period and excludes deferred GPU and display presentation work. The receive-age goal is indicative; it is not a latency guarantee. These are not displayed-FPS measurements. Replay has no receive age."


class FrameImageProvider(QQuickImageProvider):
    """Own one detached RGB image; Qt Quick handles its texture upload and display."""

    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._image = QImage()
        self._lock = Lock()

    def update_image(self, array):
        rgb = colorize(array) if array.ndim == 2 else np.ascontiguousarray(array)
        height, width, _ = rgb.shape
        image = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888).copy()
        with self._lock:
            self._image = image

    def requestImage(self, image_id, size, requested_size):
        with self._lock:
            image = QImage(self._image)
        size.setWidth(image.width())
        size.setHeight(image.height())
        if requested_size.isValid() and requested_size != image.size():
            return image.scaled(
                requested_size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        return image


class Controller(QObject):
    configChanged = Signal()
    imageChanged = Signal()
    hudChanged = Signal()
    plotControlsChanged = Signal()

    def __init__(self, args, provider):
        super().__init__()
        self.args = args
        self.provider = provider
        self.error = None
        self.duration_started = False
        self._config = {}
        self._image_url = ""
        self._view_request_pending = False
        self._presentation = {
            "submitted": "—",
            "update": "—",
            "skipped": "—",
            "age": "—",
            "ageUnit": "",
            "state": "Connecting",
            "error": False,
            "details": "Connecting to the shared producer",
            "resources": "Custom Qt Quick image",
            "renderer": "Qt Quick",
        }
        self.generation = None
        self.x = np.empty(0, dtype=np.float32)
        self.window = None
        self.series = None
        self.process = psutil.Process()
        self.process.cpu_percent()
        self.source = FrameSource(args.url, args.mode)
        self.sink = MetricsSink(
            args.url,
            "qtgraphs",
            args.mode,
            args.run_id,
            expected_duration=args.duration,
            metadata={
                "measurement_stage": "QLineSeries.replaceNp + custom CPU scalar LUT/RGB QImage "
                "copy + synchronous QML image-provider submission; GPU work excluded",
                "renderer": "Qt Graphs LineSeries / Qt Quick scene graph",
                "qsg_rhi_backend_override": os.environ.get("QSG_RHI_BACKEND"),
                "qt_quick_backend_override": os.environ.get("QT_QUICK_BACKEND"),
                "image_renderer": "CUSTOM QQuickImageProvider + Qt Quick Image; NOT a native "
                "Qt Graphs image series",
                "custom_work": "RGB QImage ownership, scalar LUT, image-provider invalidation "
                "and QML image axes/layout require additional implementation",
                "update_strategy": "full authoritative window replaceNp in replace AND append",
                "downsampling": False,
                "antialias": False,
                "versions": {
                    "python": platform.python_version(),
                    "numpy": np.__version__,
                    "qt": qVersion(),
                    "pyside6": version("PySide6"),
                },
            },
        )
        self.update_timer = QTimer(self)
        self.update_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.update_timer.timeout.connect(self.poll_frame)
        self.hud_timer = QTimer(self)
        self.hud_timer.timeout.connect(self.update_hud)

    @Property("QVariantMap", notify=hudChanged)
    def presentation(self):
        return self._presentation

    @Property(str, constant=True)
    def runMode(self):
        return self.args.mode.title()

    @Property("QVariantMap", notify=configChanged)
    def workload(self):
        config = self._config
        if not config:
            return {
                "target": "—",
                "waveform": "—",
                "image": "—",
                "waveformSubtitle": "Waiting for source",
                "imageSubtitle": "Waiting for source",
            }
        image_mode = "RGB" if config["image_mode"] == "rgb" else "scalar"
        return {
            "target": f"{config['hz']:g} Hz",
            "waveform": f"{config['points']:,} · {config['waveform_mode']}",
            "image": f"{config['width']} × {config['height']} · {image_mode}",
            "waveformSubtitle": f"{config['points']:,} points · {config['waveform_mode']}",
            "imageSubtitle": f"{config['width']} × {config['height']} · "
            f"{'RGB' if config['image_mode'] == 'rgb' else 'scalar colormap'}",
        }

    @Property(str, constant=True)
    def metricGuide(self):
        return METRIC_GUIDE

    @Property("QVariantMap", notify=configChanged)
    def metricTargets(self):
        hz = self._config.get("hz")
        targets = {
            "submitted": "(waiting for source)",
            "update": "(waiting for source)",
            "skipped": "(target 0)",
            "age": "(waiting for source)",
        }
        if hz is not None:
            period_ms = 1000 / hz
            targets.update(
                submitted=f"(target {hz:g}/s)",
                update=f"(budget ≤{period_ms:.2f} ms)",
                age=f"(goal <{period_ms:.2f} ms)",
            )
        if self.args.mode == "replay":
            targets["age"] = "(N/A in replay)"
        return targets

    @Property("QVariantMap", notify=plotControlsChanged)
    def plotControls(self):
        view = self._config.get("view")
        pending = self._view_request_pending or self.source.view_pending
        locked = bool(self.args.duration)
        available = bool(view) and not (pending or locked)
        if locked:
            reason = "Locked during recorded runs"
        elif view is None:
            reason = "Waiting for the shared source"
        elif pending:
            reason = "Updating shared source…"
        elif self.source.view_error:
            reason = self.source.view_error
        else:
            reason = "Update the shared source"
            if self.args.mode == "replay":
                reason += " and reload replay"
        return {
            "waveformChecked": view in ("waveform", "both"),
            "imageChecked": view in ("image", "both"),
            "waveformEnabled": available and view != "waveform",
            "imageEnabled": available and view != "image",
            "waveformTooltip": "1D waveform · "
            + (
                "At least one plot must remain enabled"
                if available and view == "waveform"
                else reason
            ),
            "imageTooltip": "2D image · "
            + (
                "At least one plot must remain enabled" if available and view == "image" else reason
            ),
        }

    @Slot(str)
    def toggle_plot(self, plot):
        view = self._config.get("view")
        if (
            not view
            or self.args.duration
            or self._view_request_pending
            or self.source.view_pending
            or plot not in ("waveform", "image")
        ):
            self.plotControlsChanged.emit()
            return
        selected = {"waveform", "image"} if view == "both" else {view}
        if plot in selected:
            selected.remove(plot)
        else:
            selected.add(plot)
        if selected:
            self._view_request_pending = self.source.request_view(
                "both" if len(selected) == 2 else next(iter(selected))
            )
        self.plotControlsChanged.emit()

    @Property(str, notify=imageChanged)
    def imageUrl(self):
        return self._image_url

    @Property(bool, notify=configChanged)
    def waveformVisible(self):
        return self._config.get("view", "both") in ("waveform", "both")

    @Property(bool, notify=configChanged)
    def imageVisible(self):
        return self._config.get("view", "both") in ("image", "both")

    @Property(float, notify=configChanged)
    def xMaximum(self):
        return float(max(1, self._config.get("points", 10000) - 1))

    @Property(int, notify=configChanged)
    def imageWidth(self):
        return self._config.get("width", 512)

    @Property(int, notify=configChanged)
    def imageHeight(self):
        return self._config.get("height", 512)

    @Slot()
    def open_controls(self):
        QDesktopServices.openUrl(QUrl(self.args.url))

    def start(self, window):
        self.window = window
        self.series = window.findChild(QLineSeries, "waveformSeries")
        if self.series is None:
            raise RuntimeError("QML did not create the required Qt Graphs LineSeries")
        self.source.start()
        self.update_timer.start(1)
        self.hud_timer.start(500)

    @Slot()
    def poll_frame(self):
        frame = self.source.take_latest()
        if frame is None:
            return
        if not self.source.view_pending:
            self._view_request_pending = False
        try:
            started = perf_counter()
            if frame.generation != self.generation:
                self._config = frame.header["config"]
                if self.x.size != self._config["points"]:
                    self.x = np.arange(self._config["points"], dtype=np.float32)
                self.generation = frame.generation
                self.configChanged.emit()
                self.plotControlsChanged.emit()
            if "waveform" in frame.arrays:
                self.series.replaceNp(self.x, frame.arrays["waveform"])
            conversion_started = perf_counter()
            if "image" in frame.arrays:
                self.provider.update_image(frame.arrays["image"])
            conversion_ms = (perf_counter() - conversion_started) * 1000
            if "image" in frame.arrays:
                self._image_url = f"image://frames/{frame.generation}/{frame.seq}"
                self.imageChanged.emit()
            self.sink.record(frame, (perf_counter() - started) * 1000, conversion_ms=conversion_ms)
            self.sink.metadata.update(self.source.metadata)
            if self.args.duration and not self.duration_started:
                self.duration_started = True
                QTimer.singleShot(round(self.args.duration * 1000), self.finish_duration)
        except Exception as exc:
            self.error = f"Plot update failed: {exc}"
            logger.exception("Plot update failed")
            self.update_timer.stop()
            self.update_hud()

    @Slot()
    def update_hud(self):
        metrics = self.sink.snapshot()
        if self.source.view_error or self.source.error:
            self._view_request_pending = False
        age = metrics.get("receive_age_ms")
        error = self.error or self.source.error or self.sink.error or self.source.view_error
        state = (
            "Source error"
            if error
            else ("Replaying" if self.args.mode == "replay" else "Streaming")
        )
        if metrics["count"] == 0 and not error:
            state = "Connecting"
        self._presentation = {
            "submitted": f"{metrics['updates_hz']:.1f}",
            "update": f"{metrics['update_ms']:.2f}",
            "skipped": f"{metrics['skipped']:,}",
            "age": "—" if age is None else f"{age:.1f}",
            "ageUnit": ("replay" if self.args.mode == "replay" else "") if age is None else "ms",
            "state": state,
            "error": bool(error),
            "details": error or self.source.status,
            "resources": f"CPU {self.process.cpu_percent():.0f}% · "
            f"{self.process.memory_info().rss / 2**20:.0f} MiB · Custom Qt Quick image",
            "renderer": self.window.rendererInterface().graphicsApi().name,
        }
        self.hudChanged.emit()
        self.plotControlsChanged.emit()
        ratio = self.window.devicePixelRatio()
        self.sink.metadata.update(
            qt_window_metadata(self.window, platform_name=QGuiApplication.platformName())
        )
        self.series.setWidth(1 / ratio)
        self.sink.metadata.update(
            pixel_ratio=ratio,
            viewport_size=[self.window.width(), self.window.height()],
            viewport_size_units="logical pixels",
            plot_viewport_units="physical pixels; data drawing area excluding axes",
            graphics_api=self.window.rendererInterface().graphicsApi().name,
        )
        graph = self.window.findChild(QObject, "waveformGraph")
        image = self.window.findChild(QObject, "streamImage")
        area = graph.property("plotArea")
        self.sink.metadata["plot_viewports"] = {
            "waveform": (
                [area.width() * ratio, area.height() * ratio] if self.waveformVisible else None
            ),
            "image": (
                [image.property("paintedWidth") * ratio, image.property("paintedHeight") * ratio]
                if self.imageVisible
                else None
            ),
        }

    @Slot()
    def finish_duration(self):
        self.sink.mark_stopped("duration")
        self.window.close()

    @Slot()
    def close(self):
        self.update_timer.stop()
        self.hud_timer.stop()
        self.sink.mark_stopped("user")
        self.source.close()
        self.sink.close()


def main():
    args = frontend_parser(__doc__).parse_args()
    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("Plotbench Qt Graphs")
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    provider = FrameImageProvider()
    engine.addImageProvider("frames", provider)
    controller = Controller(args, provider)
    engine.rootContext().setContextProperty("benchmark", controller)
    engine.setInitialProperties({"width": args.width, "height": args.height})
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("Main.qml"))))
    if not engine.rootObjects():
        controller.close()
        print("Failed to load Qt Graphs QML window", file=sys.stderr)
        return 1
    window = engine.rootObjects()[0]
    app.aboutToQuit.connect(controller.close)
    controller.start(window)
    result = app.exec()
    failure = controller.error or controller.source.error or controller.sink.error
    if failure or controller.sink.snapshot()["count"] == 0:
        print(failure or "No frames submitted", file=sys.stderr)
        return 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
