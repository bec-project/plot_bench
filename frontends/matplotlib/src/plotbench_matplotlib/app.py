"""Stream central waveform and image frames through Matplotlib's QtAgg backend."""

import logging
import platform
import sys
from importlib.metadata import version
from time import perf_counter

import matplotlib
import numpy as np
import psutil
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.colors import ListedColormap, NoNorm
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch
from plotbench.client import FrameSource, MetricsSink, frontend_parser
from plotbench.palette import COLORMAP
from plotbench.qt_metadata import qt_window_metadata
from qtpy.QtCore import Qt, QTimer, Slot, qVersion
from qtpy.QtWidgets import QApplication, QMainWindow

from .dashboard import ACCENT, BACKGROUND, BORDER, MUTED, PANEL, TEXT, Dashboard

logger = logging.getLogger(__name__)


class PlotCanvas(FigureCanvasQTAgg):
    """Keep axes/limits static between configuration changes and blit changing artists."""

    def __init__(self):
        figure = Figure(facecolor=BACKGROUND, dpi=100)
        super().__init__(figure)
        self.setMinimumSize(100, 100)
        self.waveform_axis = figure.add_axes((0.09, 0.58, 0.86, 0.35))
        self.image_axis = figure.add_axes((0.09, 0.08, 0.86, 0.35))
        self.cards = []
        for title in ("Waveform", "Image"):
            panel = FancyBboxPatch(
                (0, 0),
                1,
                1,
                boxstyle="round,pad=0,rounding_size=0.012",
                transform=figure.transFigure,
                facecolor=PANEL,
                edgecolor=BORDER,
                linewidth=0.7,
                zorder=-1,
            )
            figure.patches.append(panel)
            heading = figure.text(0, 0, title, color=TEXT, fontsize=11.5, weight="bold", va="top")
            subtitle = figure.text(0, 0, "Waiting for source", color=MUTED, fontsize=8, va="top")
            self.cards.append((panel, heading, subtitle))
        for axis in (self.waveform_axis, self.image_axis):
            axis.set_facecolor(PANEL)
            axis.tick_params(colors=MUTED, labelsize=8, length=3, width=0.6)
            for spine in axis.spines.values():
                spine.set_color(BORDER)
                spine.set_linewidth(0.6)
            axis.xaxis.label.set_color(MUTED)
            axis.yaxis.label.set_color(MUTED)
            axis.xaxis.label.set_size(8)
            axis.yaxis.label.set_size(8)
        self.waveform_axis.set_xlabel("Sample")
        self.waveform_axis.set_ylabel("Amplitude")
        self.image_axis.set_xlabel("Column")
        self.image_axis.set_ylabel("Row")
        (self.line,) = self.waveform_axis.plot(
            [], [], color=ACCENT, linewidth=0.72, antialiased=False, animated=True
        )
        self.image_artist = self.image_axis.imshow(
            np.zeros((2, 2), dtype=np.float32),
            cmap=ListedColormap(COLORMAP / 255.0, name="plotbench"),
            norm=NoNorm(),
            origin="upper",
            interpolation="nearest",
            interpolation_stage="rgba",
            animated=True,
        )
        self.background = None
        self.config = None
        self.x = np.empty(0, dtype=np.float32)
        self.layout_plots()
        self.mpl_connect("resize_event", self.invalidate_background)

    def invalidate_background(self, event=None):
        self.layout_plots()
        self.background = None

    def layout_plots(self):
        width, height = max(1, self.width()), max(1, self.height())
        view = self.config["view"] if self.config else "both"
        gap = 16 / width
        for index, (axis, card) in enumerate(
            zip((self.waveform_axis, self.image_axis), self.cards, strict=True)
        ):
            panel, heading, subtitle = card
            visible = view == "both" or view == ("waveform", "image")[index]
            for item in (axis, panel, heading, subtitle):
                item.set_visible(visible)
            card_width = (1 - gap) / 2 if view == "both" else 1
            left = index * (card_width + gap) if view == "both" else 0
            panel.set_bounds(left + 0.001, 0.003, card_width - 0.002, 0.994)
            heading.set_position((left + 16 / width, 1 - 16 / height))
            subtitle.set_position((left + 16 / width, 1 - 42 / height))
            axis.set_position(
                (
                    left + 62 / width,
                    46 / height,
                    max(30 / width, card_width - 82 / width),
                    max(40 / height, 1 - 114 / height),
                )
            )

    def apply_config(self, config):
        self.config = config
        self.cards[0][2].set_text(f"{config['points']:,} points · {config['waveform_mode']}")
        self.cards[1][2].set_text(
            f"{config['width']} × {config['height']} · "
            f"{'RGB' if config['image_mode'] == 'rgb' else 'scalar colormap'}"
        )
        self.layout_plots()
        if self.x.size != config["points"]:
            self.x = np.arange(config["points"], dtype=np.float32)
        self.waveform_axis.set_xlim(0, max(1, config["points"] - 1))
        self.waveform_axis.set_ylim(-1.5, 1.5)
        self.image_artist.set_extent((-0.5, config["width"] - 0.5, config["height"] - 0.5, -0.5))
        self.image_axis.set_xlim(-0.5, config["width"] - 0.5)
        self.image_axis.set_ylim(config["height"] - 0.5, -0.5)
        self.background = None

    def update_frame(self, frame):
        if "waveform" in frame.arrays:
            self.line.set_data(self.x, frame.arrays["waveform"])
        conversion_ms = 0.0
        if "image" in frame.arrays:
            image = frame.arrays["image"]
            if image.ndim == 2:
                conversion_started = perf_counter()
                image = (np.clip(image, 0, 1) * 255).astype(np.uint8)
                conversion_ms = (perf_counter() - conversion_started) * 1000
            self.image_artist.set_data(image)
        # Matplotlib uses points for stroke width, while figure.dpi includes Retina scaling.
        self.line.set_linewidth(72 / self.figure.dpi)
        if self.background is None:
            self.line.set_visible(False)
            self.image_artist.set_visible(False)
            self.draw()
            self.background = self.copy_from_bbox(self.figure.bbox)
            self.line.set_visible(True)
            self.image_artist.set_visible(True)
        self.restore_region(self.background)
        if "waveform" in frame.arrays:
            self.waveform_axis.draw_artist(self.line)
        if "image" in frame.arrays:
            self.image_axis.draw_artist(self.image_artist)
        self.blit(self.figure.bbox)
        return conversion_ms


class PlotWindow(QMainWindow):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.error = None
        self.duration_started = False
        self.generation = None
        self.process = psutil.Process()
        self.process.cpu_percent()
        self.setWindowTitle(f"Plotbench · Matplotlib QtAgg · {args.mode}")
        self.resize(args.width, args.height)
        self.setMinimumSize(860, 640)
        self.dashboard = Dashboard("Matplotlib", "QtAgg", args.mode, args.url)
        self.dashboard.viewRequested.connect(self.request_view)
        self.dashboard.sync_plot_controls(locked=bool(args.duration))
        self.canvas = PlotCanvas()
        self.dashboard.plots.addWidget(self.canvas, 1)
        self.setCentralWidget(self.dashboard)
        self.source = FrameSource(args.url, args.mode)
        self.sink = MetricsSink(
            args.url,
            "matplotlib",
            args.mode,
            args.run_id,
            expected_duration=args.duration,
            metadata={
                "measurement_stage": "scalar-to-uint8 index conversion + set_data + synchronous "
                "Agg artist rasterization + QtAgg canvas.blit; compositor/presentation excluded",
                "renderer": "Matplotlib QtAgg with reusable artists and blitting",
                "scalar_index_mapping": "uint8 floor(clamp(value,0,1)*255); native NoNorm "
                "+ ListedColormap lookup",
                "update_strategy": "complete authoritative window set_data in replace AND append",
                "downsampling": False,
                "path_simplify": False,
                "agg_path_chunksize": 0,
                "antialias": False,
                "versions": {
                    "python": platform.python_version(),
                    "numpy": np.__version__,
                    "matplotlib": matplotlib.__version__,
                    "qt": qVersion(),
                    "pyside6": version("PySide6"),
                },
            },
        )
        self.update_timer = QTimer(self)
        self.update_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.update_timer.timeout.connect(self.poll_frame)
        self.update_timer.start(1)
        self.hud_timer = QTimer(self)
        self.hud_timer.timeout.connect(self.update_hud)
        self.hud_timer.start(500)
        self.source.start()

    @Slot()
    def poll_frame(self):
        frame = self.source.take_latest()
        if frame is None:
            return
        try:
            started = perf_counter()
            if frame.generation != self.generation:
                self.canvas.apply_config(frame.header["config"])
                self.dashboard.update_summary(frame.header["config"])
                self.generation = frame.generation
            conversion_ms = self.canvas.update_frame(frame)
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
            "QtAgg blitting",
        )
        self.sink.metadata.update(
            qt_window_metadata(self, platform_name=QApplication.platformName())
        )
        self.sink.metadata.update(
            pixel_ratio=self.devicePixelRatioF(),
            viewport_size=[self.width(), self.height()],
            viewport_size_units="logical pixels",
            canvas_size=[self.canvas.width(), self.canvas.height()],
            plot_viewport_units="physical pixels; data drawing area excluding axes",
            plot_viewports={
                "waveform": (
                    [self.canvas.waveform_axis.bbox.width, self.canvas.waveform_axis.bbox.height]
                    if self.canvas.waveform_axis.get_visible()
                    else None
                ),
                "image": (
                    [self.canvas.image_axis.bbox.width, self.canvas.image_axis.bbox.height]
                    if self.canvas.image_axis.get_visible()
                    else None
                ),
            },
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
    args = frontend_parser(__doc__).parse_args()
    matplotlib.rcParams.update({"path.simplify": False, "agg.path.chunksize": 0})
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
