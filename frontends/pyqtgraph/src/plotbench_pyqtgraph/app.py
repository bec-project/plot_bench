"""Compare PyQtGraph's raster viewport and OpenGL curve path."""

import logging
import os
import platform
import sys
from importlib.metadata import version
from time import perf_counter

import numpy as np
import psutil
import pyqtgraph as pg
from plotbench.client import FrameSource, MetricsSink, frontend_parser
from plotbench.palette import COLORMAP
from plotbench.qt_metadata import qt_window_metadata
from qtpy.QtCore import Qt, QTimer, Slot, qVersion
from qtpy.QtGui import QFont, QSurfaceFormat
from qtpy.QtWidgets import QApplication, QMainWindow

from .dashboard import ACCENT, BORDER, MUTED, PANEL, Dashboard, PlotCard

logger = logging.getLogger(__name__)


class PlotWindow(QMainWindow):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.error = None
        self.duration_started = False
        self.config = None
        self.generation = None
        self.x = np.empty(0, dtype=np.float32)
        self.process = psutil.Process()
        self.process.cpu_percent()
        self.source = FrameSource(args.url, args.mode)
        name = "pyqtgraph-gl" if args.opengl else "pyqtgraph"
        self.setWindowTitle(f"Plotbench · {name} · {args.mode}")
        self.resize(args.width, args.height)
        self.setMinimumSize(860, 640)
        self.dashboard = Dashboard(
            "PyQtGraph", "OpenGL" if args.opengl else "Raster", args.mode, args.url
        )
        self.dashboard.viewRequested.connect(self.request_view)
        self.dashboard.sync_plot_controls(locked=bool(args.duration))
        self.waveform_card = PlotCard("Waveform")
        self.image_card = PlotCard("Image")
        self.dashboard.plots.addWidget(self.waveform_card, 1)
        self.dashboard.plots.addWidget(self.image_card, 1)
        self.waveform = pg.PlotWidget(background=PANEL)
        self.waveform.setLabel("bottom", "Sample")
        self.waveform.setLabel("left", "Amplitude")
        self.waveform.setMouseEnabled(x=False, y=False)
        self.waveform.setMenuEnabled(False)
        self.waveform.disableAutoRange()
        self.curve = self.waveform.plot(
            pen=pg.mkPen(ACCENT, width=1, cosmetic=True),
            antialias=False,
            connect="all",
            skipFiniteCheck=True,
        )
        self.curve.setDownsampling(ds=1, auto=False)
        self.curve.setClipToView(False)
        self.curve.setDynamicRangeLimit(None)
        self.waveform_card.content.addWidget(self.waveform, 1)
        self.image_plot = pg.PlotWidget(background=PANEL)
        self.image_plot.setLabel("bottom", "Column")
        self.image_plot.setLabel("left", "Row")
        self.image_plot.setMouseEnabled(x=False, y=False)
        self.image_plot.setMenuEnabled(False)
        self.image_plot.disableAutoRange()
        self.image_plot.getViewBox().invertY(True)
        self.image_plot.setAspectLocked(True)
        self.image_item = pg.ImageItem(axisOrder="row-major", autoDownsample=False)
        self.image_plot.addItem(self.image_item)
        self.image_card.content.addWidget(self.image_plot, 1)
        tick_font = QFont("Helvetica Neue")
        tick_font.setPixelSize(11)
        for plot in (self.waveform, self.image_plot):
            plot.setMinimumSize(100, 100)
            plot.getPlotItem().layout.setContentsMargins(0, 8, 0, 0)
            plot.hideButtons()
            for axis_name in ("left", "bottom"):
                axis = plot.getAxis(axis_name)
                axis.setPen(pg.mkPen(BORDER))
                axis.setTextPen(pg.mkPen(MUTED))
                axis.setStyle(tickFont=tick_font)
                axis.label.setDefaultTextColor(pg.mkColor(MUTED))
        self.setCentralWidget(self.dashboard)

        self.metadata = {
            "measurement_stage": "scalar-to-uint8 index conversion + setData + ImageItem.setImage "
            "submission; deferred Indexed8 QImage/color-table preparation, QPainter LUT "
            "expansion/paint and GPU work excluded",
            "renderer": (
                "OpenGL shader PlotCurveItem via Qt OpenGL + QOpenGLWidget viewport"
                if args.opengl
                else "QPainter raster viewport"
            ),
            "image_renderer": "ImageItem CPU LUT/QImage painted onto the selected viewport",
            "scalar_index_mapping": "uint8 floor(clamp(value,0,1)*255); native LUT without rescaling",
            "useOpenGL": args.opengl,
            "enableExperimental": False,
            "antialias": False,
            "downsampling": False,
            "dynamic_range_limit": None,
            "skip_finite_check": True,
            "update_strategy": "full authoritative window setData in replace AND append mode",
            "versions": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "pyqtgraph": pg.__version__,
                "qt": qVersion(),
                "pyside6": version("PySide6"),
            },
        }
        self.sink = MetricsSink(
            args.url,
            name,
            args.mode,
            args.run_id,
            metadata=self.metadata,
            expected_duration=args.duration,
        )
        self.metadata = self.sink.metadata
        self.update_timer = QTimer(self)
        self.update_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.update_timer.timeout.connect(self.poll_frame)
        self.update_timer.start(1)
        self.hud_timer = QTimer(self)
        self.hud_timer.timeout.connect(self.update_hud)
        self.hud_timer.start(500)
        self.source.start()

    def apply_config(self, config):
        self.config = config
        self.dashboard.update_summary(config)
        self.waveform_card.subtitle.setText(
            f"{config['points']:,} points · {config['waveform_mode']}"
        )
        self.image_card.subtitle.setText(
            f"{config['width']} × {config['height']} · "
            f"{'RGB' if config['image_mode'] == 'rgb' else 'scalar colormap'}"
        )
        self.waveform_card.setVisible(config["view"] in ("waveform", "both"))
        self.image_card.setVisible(config["view"] in ("image", "both"))
        self.waveform.setVisible(config["view"] in ("waveform", "both"))
        self.image_plot.setVisible(config["view"] in ("image", "both"))
        if self.x.size != config["points"]:
            self.x = np.arange(config["points"], dtype=np.float32)
        self.waveform.setXRange(0, max(1, config["points"] - 1), padding=0)
        self.waveform.setYRange(-1.5, 1.5, padding=0)
        self.image_plot.setRange(
            xRange=(0, config["width"]), yRange=(0, config["height"]), padding=0
        )
        self.image_item.setLookupTable(COLORMAP if config["image_mode"] == "scalar" else None)

    @Slot()
    def poll_frame(self):
        frame = self.source.take_latest()
        if frame is None:
            return
        try:
            started = perf_counter()
            if frame.generation != self.generation:
                self.apply_config(frame.header["config"])
                self.generation = frame.generation
            if "waveform" in frame.arrays:
                self.curve.setData(self.x, frame.arrays["waveform"])
            conversion_ms = 0.0
            if "image" in frame.arrays:
                image = frame.arrays["image"]
                if image.ndim == 2:
                    conversion_started = perf_counter()
                    image = (np.clip(image, 0, 1) * 255).astype(np.uint8)
                    conversion_ms = (perf_counter() - conversion_started) * 1000
                self.image_item.setImage(image, autoLevels=False, levels=None, autoDownsample=False)
            self.sink.record(frame, (perf_counter() - started) * 1000, conversion_ms=conversion_ms)
            self.metadata.update(self.source.metadata)
            if self.args.duration and not self.duration_started:
                self.duration_started = True
                QTimer.singleShot(round(self.args.duration * 1000), self.finish_duration)
        except Exception as exc:
            self.error = f"Plot update failed: {exc}"
            logger.exception("Plot update failed")
            self.update_timer.stop()
            self.update_hud()

    @Slot(str)
    def request_view(self, view):
        accepted = False
        if not self.args.duration and not self.source.view_pending:
            accepted = self.source.request_view(view)
        self.dashboard.sync_plot_controls(
            accepted or self.source.view_pending, self.source.view_error, bool(self.args.duration)
        )

    @Slot()
    def update_hud(self):
        metrics = self.sink.snapshot()
        self.dashboard.sync_plot_controls(
            self.source.view_pending, self.source.view_error, bool(self.args.duration)
        )
        self.dashboard.update_metrics(
            metrics,
            self.source.status,
            self.error or self.source.error or self.sink.error or self.source.view_error,
            self.process.cpu_percent(),
            self.process.memory_info().rss / 2**20,
            "OpenGL / CPU image LUT" if self.args.opengl else "QPainter raster",
        )
        ratio = self.devicePixelRatioF()
        self.metadata.update(qt_window_metadata(self, platform_name=QApplication.platformName()))
        waveform_area = self.waveform.getViewBox().sceneBoundingRect()
        image_area = self.image_item.mapRectToDevice(self.image_item.boundingRect())
        self.metadata.update(
            pixel_ratio=ratio,
            viewport_size=[self.width(), self.height()],
            viewport_size_units="logical pixels",
            plot_viewport_units="physical pixels; data drawing area excluding axes",
            plot_viewports={
                "waveform": (
                    [waveform_area.width() * ratio, waveform_area.height() * ratio]
                    if self.waveform.isVisible()
                    else None
                ),
                "image": (
                    [image_area.width() * ratio, image_area.height() * ratio]
                    if self.image_plot.isVisible() and image_area is not None
                    else None
                ),
            },
        )
        gl_viewport = (self.waveform if self.waveform.isVisible() else self.image_plot).viewport()
        if self.args.opengl and gl_viewport.context():
            context = gl_viewport.context()
            self.metadata["opengl_context_valid"] = context.isValid()
            self.metadata["opengl_version"] = list(context.format().version())
            self.metadata["opengl_curve_shader_ready"] = (
                self.waveform.viewport().retrieveProgram("PlotCurveItem") is not None
            )

    @Slot()
    def finish_duration(self):
        self.sink.mark_stopped("duration")
        self.close()

    def closeEvent(self, event):
        self.update_timer.stop()
        self.hud_timer.stop()
        self.sink.mark_stopped("user")
        self.source.close()
        self.sink.close()
        event.accept()


def main():
    parser = frontend_parser(__doc__)
    parser.add_argument(
        "--opengl", action="store_true", help="Enable OpenGL curve and viewport drawing"
    )
    args = parser.parse_args()
    if args.opengl and os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        parser.error("OpenGL requires a real macOS display; offscreen cannot verify this renderer")
    if args.opengl:
        surface = QSurfaceFormat()
        surface.setVersion(3, 3)
        surface.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        surface.setSamples(0)
        QSurfaceFormat.setDefaultFormat(surface)
    pg.setConfigOptions(
        useOpenGL=args.opengl,
        enableExperimental=False,
        antialias=False,
        background=PANEL,
        foreground=MUTED,
        imageAxisOrder="row-major",
    )
    app = QApplication(sys.argv[:1])
    window = PlotWindow(args)
    window.show()
    result = app.exec()
    failure = window.error or window.source.error or window.sink.error
    if failure or window.sink.snapshot()["count"] == 0:
        print(failure or "No frames submitted", file=sys.stderr)
        return 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
