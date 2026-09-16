"""Compare PyQtGraph's raster viewport and OpenGL curve path."""

import logging
import math
import os
import platform
import sys
from importlib.metadata import version
from time import perf_counter

import numpy as np
import psutil
import pyqtgraph as pg
from plotbench.client import FrameSource, MetricsSink, frontend_parser
from plotbench.palette import COLORMAP, CURVE_COLORS
from plotbench.qt_metadata import qt_window_metadata
from plotbench.render_contract import VERSION, image_size, slot_size
from qtpy.QtCore import QSizeF, Qt, QTimer, Slot, qVersion
from qtpy.QtGui import QFont, QSurfaceFormat
from qtpy.QtWidgets import QApplication, QMainWindow

from .dashboard import BORDER, MUTED, PANEL, Dashboard, PlotCard, plot_title

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
        self.tick_font = QFont("Helvetica Neue")
        self.tick_font.setPixelSize(11)
        # One PlotCard + PlotWidget per waveform plot (holding `curves` PlotDataItems) and per
        # image plot (holding one ImageItem); rebuilt whenever a generation changes the counts.
        self.waveform_cards = []
        self.waveform_plots = []
        self.curves = []
        self.curve_count = 1
        self.image_cards = []
        self.image_plots = []
        self.image_items = []
        self.sync_plots(1, 1, 1)
        self.setCentralWidget(self.dashboard)

        self.metadata = {
            "render_contract": VERSION,
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
            "update_strategy": "full authoritative window setData per curve of every waveform "
            "plot and setImage per image plot in replace AND append mode",
            "curve_colors": "plotbench.palette.CURVE_COLORS[c % 8] per curve index c",
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

    # First plot of each kind; None while that kind is hidden by the source view.
    @property
    def waveform(self):
        return self.waveform_plots[0] if self.waveform_plots else None

    @property
    def curve(self):
        return self.curves[0][0] if self.curves else None

    @property
    def image_plot(self):
        return self.image_plots[0] if self.image_plots else None

    @property
    def image_item(self):
        return self.image_items[0] if self.image_items else None

    def style_plot(self, plot):
        plot.setMouseEnabled(x=False, y=False)
        plot.setMenuEnabled(False)
        plot.disableAutoRange()
        plot.setMinimumSize(1, 1)
        plot.getPlotItem().layout.setContentsMargins(0, 8, 0, 0)
        plot.getPlotItem().layout.setSpacing(0)
        plot.getAxis("left").setWidth(56)
        plot.getAxis("bottom").setHeight(36)
        plot.hideButtons()
        for axis_name in ("left", "bottom"):
            axis = plot.getAxis(axis_name)
            axis.setPen(pg.mkPen(BORDER))
            axis.setTextPen(pg.mkPen(MUTED))
            axis.setStyle(tickFont=self.tick_font)
            axis.label.setDefaultTextColor(pg.mkColor(MUTED))
        return plot

    def add_curve(self, plot, index):
        curve = plot.plot(
            pen=pg.mkPen(CURVE_COLORS[index % len(CURVE_COLORS)], width=1, cosmetic=True),
            antialias=False,
            connect="all",
            skipFiniteCheck=True,
        )
        curve.setDownsampling(ds=1, auto=False)
        curve.setClipToView(False)
        curve.setDynamicRangeLimit(None)
        return curve

    def add_waveform_plot(self):
        # PlotWidget reads the global useOpenGL option, so every plot shares the viewport kind.
        plot = self.style_plot(pg.PlotWidget(background=PANEL))
        plot.setLabel("bottom", "Sample")
        plot.setLabel("left", "Amplitude")
        card = PlotCard("Waveform")
        card.content.addWidget(plot, 0, Qt.AlignmentFlag.AlignHCenter)
        card.content.addStretch(1)
        self.waveform_cards.append(card)
        self.waveform_plots.append(plot)
        self.curves.append([])

    def add_image_plot(self):
        plot = self.style_plot(pg.PlotWidget(background=PANEL))
        plot.setLabel("bottom", "Column")
        plot.setLabel("left", "Row")
        plot.getViewBox().invertY(True)
        plot.setAspectLocked(True)
        item = pg.ImageItem(axisOrder="row-major", autoDownsample=False)
        plot.addItem(item)
        card = PlotCard("Image")
        card.content.addWidget(plot, 0, Qt.AlignmentFlag.AlignHCenter)
        card.content.addStretch(1)
        self.image_cards.append(card)
        self.image_plots.append(plot)
        self.image_items.append(item)

    def sync_plots(self, waveform_count, curve_count, image_count):
        """Reuse existing widgets, add missing ones and delete surplus ones, then lay out."""
        surplus = []
        while len(self.waveform_plots) > waveform_count:
            surplus.append(self.waveform_cards.pop())
            self.waveform_plots.pop()
            self.curves.pop()
        while len(self.waveform_plots) < waveform_count:
            self.add_waveform_plot()
        for plot, curves in zip(self.waveform_plots, self.curves, strict=True):
            while len(curves) > curve_count:
                plot.removeItem(curves.pop())
            while len(curves) < curve_count:
                curves.append(self.add_curve(plot, len(curves)))
        self.curve_count = curve_count
        while len(self.image_plots) > image_count:
            surplus.append(self.image_cards.pop())
            self.image_plots.pop()
            self.image_items.pop()
        while len(self.image_plots) < image_count:
            self.add_image_plot()
        self.dashboard.arrange_plots(self.waveform_cards + self.image_cards)
        for card in surplus:
            card.setParent(None)
            card.deleteLater()

    def apply_config(self, config):
        self.config = config
        self.dashboard.update_summary(config)
        waveform_count = config["waveform_plots"] if config["view"] in ("waveform", "both") else 0
        image_count = config["image_plots"] if config["view"] in ("image", "both") else 0
        self.sync_plots(waveform_count, config["curves"], image_count)
        if self.x.size != config["points"]:
            self.x = np.arange(config["points"], dtype=np.float32)
        subtitle = f"{config['points']:,} points · {config['waveform_mode']}"
        if config["curves"] > 1:
            subtitle += f" · {config['curves']} curves"
        for index, (card, plot) in enumerate(
            zip(self.waveform_cards, self.waveform_plots, strict=True)
        ):
            card.title.setText(plot_title("Waveform", index, waveform_count))
            card.subtitle.setText(subtitle)
            plot.setXRange(0, max(1, config["points"] - 1), padding=0)
            plot.setYRange(-1.5, 1.5, padding=0)
        subtitle = (
            f"{config['width']} × {config['height']} · "
            f"{'RGB' if config['image_mode'] == 'rgb' else 'scalar colormap'}"
        )
        for index, (card, plot, item) in enumerate(
            zip(self.image_cards, self.image_plots, self.image_items, strict=True)
        ):
            card.title.setText(plot_title("Image", index, image_count))
            card.subtitle.setText(subtitle)
            plot.setRange(xRange=(0, config["width"]), yRange=(0, config["height"]), padding=0)
            item.setLookupTable(COLORMAP if config["image_mode"] == "scalar" else None)
        self.layout_data_areas()

    def layout_data_areas(self):
        if not self.config:
            return
        count = len(self.waveform_plots) + len(self.image_plots)
        slot = slot_size(self.width(), self.height(), count)
        fitted = image_size(slot, self.config["width"], self.config["height"])
        for plots, size in ((self.waveform_plots, slot), (self.image_plots, fitted)):
            for plot in plots:
                view = plot.getViewBox()
                view.setMinimumSize(QSizeF(*size))
                view.setMaximumSize(QSizeF(*size))
                # Fix the plot widget too: otherwise its axes stretch to the old
                # container while the constrained ViewBox occupies only part of it.
                plot.setFixedSize(math.ceil(size[0] + 56), math.ceil(size[1] + 44))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "waveform_plots"):
            self.layout_data_areas()

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
                # [waveform_plots, curves, points]; iterating yields contiguous views, no copies.
                for curves, plot_data in zip(self.curves, frame.arrays["waveform"], strict=True):
                    for curve, values in zip(curves, plot_data, strict=True):
                        curve.setData(self.x, values)
            conversion_ms = 0.0
            if "image" in frame.arrays:
                # [image_plots, height, width] scalar or [image_plots, height, width, 3] RGB.
                for item, image in zip(self.image_items, frame.arrays["image"], strict=True):
                    if image.ndim == 2:
                        conversion_started = perf_counter()
                        image = (np.clip(image, 0, 1) * 255).astype(np.uint8)
                        conversion_ms += (perf_counter() - conversion_started) * 1000
                    item.setImage(image, autoLevels=False, levels=None, autoDownsample=False)
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
        # All grid cells are equal, so the first plot of each kind describes every plot.
        waveform_area = image_area = None
        if self.waveform is not None and self.waveform.isVisible():
            waveform_area = self.waveform.getViewBox().rect()
        if self.image_plot is not None and self.image_plot.isVisible():
            image_area = self.image_item.mapRectToDevice(self.image_item.boundingRect())
        self.metadata.update(
            pixel_ratio=ratio,
            viewport_size=[self.width(), self.height()],
            viewport_size_units="logical pixels",
            plot_viewport_units="physical pixels; data drawing area of the first plot of each "
            "kind, excluding axes",
            plot_viewports={
                "waveform": (
                    [waveform_area.width() * ratio, waveform_area.height() * ratio]
                    if waveform_area is not None
                    else None
                ),
                "image": (
                    [image_area.width() * ratio, image_area.height() * ratio]
                    if image_area is not None
                    else None
                ),
            },
            plot_viewports_all={
                "waveform": [
                    [p.getViewBox().width() * ratio, p.getViewBox().height() * ratio]
                    for p in self.waveform_plots
                ],
                "image": [
                    [r.width() * ratio, r.height() * ratio] if r is not None else None
                    for item in self.image_items
                    for r in [item.mapRectToDevice(item.boundingRect())]
                ],
            },
            plot_counts={"waveform": len(self.waveform_plots), "image": len(self.image_plots)},
            curves=self.curve_count,
        )
        gl_plot = self.waveform if self.waveform is not None else self.image_plot
        gl_viewport = gl_plot.viewport() if gl_plot is not None else None
        if self.args.opengl and gl_viewport is not None and gl_viewport.context():
            context = gl_viewport.context()
            self.metadata["opengl_context_valid"] = context.isValid()
            self.metadata["opengl_version"] = list(context.format().version())
            self.metadata["opengl_curve_shader_ready"] = (
                self.waveform is not None
                and self.waveform.viewport().retrieveProgram("PlotCurveItem") is not None
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
