"""Stream central waveform and image frames through Matplotlib's QtAgg backend."""

import logging
import math
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
from plotbench.palette import COLORMAP, CURVE_COLORS
from plotbench.qt_metadata import qt_window_metadata
from plotbench.render_contract import VERSION, slot_size
from qtpy.QtCore import Qt, QTimer, Slot, qVersion
from qtpy.QtWidgets import QApplication, QMainWindow

from .dashboard import BACKGROUND, BORDER, MUTED, PANEL, TEXT, Dashboard

logger = logging.getLogger(__name__)


def plot_grid(count):
    """Shared layout rule: columns = ceil(sqrt(n)), rows = ceil(n / columns), row-major."""
    if count <= 0:
        return 0, 0
    columns = math.ceil(math.sqrt(count))
    return columns, math.ceil(count / columns)


class PlotCanvas(FigureCanvasQTAgg):
    """Keep axes/limits static between configuration changes and blit changing artists.

    One axes per waveform plot (holding `curves` Line2D artists) and one per image plot
    (holding one AxesImage) sit on the shared grid; the set is rebuilt only when the
    plot or curve counts change, so artists survive ordinary configuration updates.
    """

    def __init__(self):
        figure = Figure(facecolor=BACKGROUND, dpi=100)
        super().__init__(figure)
        self.setMinimumSize(100, 100)
        self.colormap = ListedColormap(COLORMAP / 255.0, name="plotbench")
        self.waveform_axes = []
        self.image_axes = []
        self.lines = []
        self.image_artists = []
        self.cards = []
        self.curves = 0
        self.plot_counts = None
        self.background = None
        self.config = None
        self.linewidth = None
        self.x = np.empty(0, dtype=np.float32)
        self.build_plots(1, 1, 1)
        self.layout_plots()
        self.mpl_connect("resize_event", self.invalidate_background)

    @property
    def waveform_axis(self):
        """First waveform axes (metadata and tests), or None when the kind is hidden."""
        return self.waveform_axes[0] if self.waveform_axes else None

    @property
    def image_axis(self):
        return self.image_axes[0] if self.image_axes else None

    @property
    def line(self):
        """Curve 0 of the first waveform plot."""
        return self.lines[0][0] if self.lines else None

    @property
    def image_artist(self):
        return self.image_artists[0] if self.image_artists else None

    @property
    def animated_artists(self):
        return [line for plot_lines in self.lines for line in plot_lines] + self.image_artists

    def invalidate_background(self, event=None):
        self.layout_plots()
        self.background = None

    def _make_card(self, title):
        figure = self.figure
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
        figure.add_artist(panel)
        heading = figure.text(0, 0, title, color=TEXT, fontsize=11.5, weight="bold", va="top")
        subtitle = figure.text(0, 0, "Waiting for source", color=MUTED, fontsize=8, va="top")
        card = (panel, heading, subtitle)
        self.cards.append(card)
        return card

    def _make_axis(self, xlabel, ylabel):
        axis = self.figure.add_axes((0.1, 0.1, 0.8, 0.8))
        axis.set_facecolor(PANEL)
        axis.tick_params(colors=MUTED, labelsize=8, length=3, width=0.6)
        for spine in axis.spines.values():
            spine.set_color(BORDER)
            spine.set_linewidth(0.6)
        axis.xaxis.label.set_color(MUTED)
        axis.yaxis.label.set_color(MUTED)
        axis.xaxis.label.set_size(8)
        axis.yaxis.label.set_size(8)
        axis.set_xlabel(xlabel)
        axis.set_ylabel(ylabel)
        return axis

    def build_plots(self, waveform_count, curves, image_count):
        """Create the plot set for the given counts; a no-op while the counts are unchanged."""
        if self.plot_counts == (waveform_count, curves, image_count):
            return
        for axis in self.waveform_axes + self.image_axes:
            self.figure.delaxes(axis)
        for card in self.cards:
            for item in card:
                item.remove()
        self.waveform_axes, self.image_axes, self.lines, self.image_artists = ([], [], [], [])
        self.cards = []
        for index in range(waveform_count):
            self._make_card("Waveform" if waveform_count == 1 else f"Waveform {index + 1}")
            axis = self._make_axis("Sample", "Amplitude")
            self.waveform_axes.append(axis)
            self.lines.append(
                [
                    axis.plot(
                        [],
                        [],
                        color=CURVE_COLORS[curve % len(CURVE_COLORS)],
                        linewidth=0.72,
                        antialiased=False,
                        animated=True,
                    )[0]
                    for curve in range(curves)
                ]
            )
        for index in range(image_count):
            self._make_card("Image" if image_count == 1 else f"Image {index + 1}")
            axis = self._make_axis("Column", "Row")
            self.image_axes.append(axis)
            self.image_artists.append(
                axis.imshow(
                    np.zeros((2, 2), dtype=np.float32),
                    cmap=self.colormap,
                    norm=NoNorm(),
                    origin="upper",
                    interpolation="nearest",
                    interpolation_stage="rgba",
                    animated=True,
                )
            )
        self.curves = curves
        self.plot_counts = (waveform_count, curves, image_count)
        self.linewidth = None
        self.background = None

    def layout_plots(self):
        """Place every card and axes on the shared grid with pixel margins per cell."""
        width, height = max(1, self.width()), max(1, self.height())
        plots = list(zip(self.waveform_axes + self.image_axes, self.cards, strict=True))
        columns, rows = plot_grid(len(plots))
        if not plots:
            return
        slot = slot_size(self.window().width(), self.window().height(), len(plots))
        gap_x, gap_y = 16 / width, 16 / height
        cell_width = (1 - gap_x * (columns - 1)) / columns
        cell_height = (1 - gap_y * (rows - 1)) / rows
        for index, (axis, (panel, heading, subtitle)) in enumerate(plots):
            column, row = index % columns, index // columns
            left = column * (cell_width + gap_x)
            bottom = 1 - (row + 1) * cell_height - row * gap_y
            panel.set_bounds(left + 0.001, bottom + 0.003, cell_width - 0.002, cell_height - 0.006)
            heading.set_position((left + 16 / width, bottom + cell_height - 16 / height))
            subtitle.set_position((left + 16 / width, bottom + cell_height - 42 / height))
            axis.set_position(
                (left + 62 / width, bottom + 46 / height, slot[0] / width, slot[1] / height)
            )

    def apply_config(self, config):
        self.config = config
        waveform_count = config["waveform_plots"] if config["view"] != "image" else 0
        image_count = config["image_plots"] if config["view"] != "waveform" else 0
        self.build_plots(waveform_count, config["curves"], image_count)
        waveform_subtitle = f"{config['points']:,} points · {config['waveform_mode']}"
        if config["curves"] > 1:
            waveform_subtitle += f" · {config['curves']} curves"
        image_subtitle = (
            f"{config['width']} × {config['height']} · "
            f"{'RGB' if config['image_mode'] == 'rgb' else 'scalar colormap'}"
        )
        for index, card in enumerate(self.cards):
            card[2].set_text(waveform_subtitle if index < waveform_count else image_subtitle)
        self.layout_plots()
        if self.x.size != config["points"]:
            self.x = np.arange(config["points"], dtype=np.float32)
        for axis in self.waveform_axes:
            axis.set_xlim(0, max(1, config["points"] - 1))
            axis.set_ylim(-1.5, 1.5)
        for axis, artist in zip(self.image_axes, self.image_artists, strict=True):
            artist.set_extent((-0.5, config["width"] - 0.5, config["height"] - 0.5, -0.5))
            axis.set_xlim(-0.5, config["width"] - 0.5)
            axis.set_ylim(config["height"] - 0.5, -0.5)
        self.background = None

    def update_frame(self, frame):
        waveform = frame.arrays.get("waveform")
        if waveform is not None:
            expected = (len(self.lines), self.curves, self.x.size)
            if waveform.shape != expected:
                raise ValueError(f"waveform shape {waveform.shape} does not match {expected}")
            for plot_lines, plot in zip(self.lines, waveform, strict=True):
                for line, curve in zip(plot_lines, plot, strict=True):
                    line.set_data(self.x, curve)
        conversion_ms = 0.0
        image = frame.arrays.get("image")
        if image is not None:
            expected_size = (self.config["height"], self.config["width"])
            if image.ndim not in (3, 4) or image.shape[0] != len(self.image_artists):
                raise ValueError(
                    f"image shape {image.shape} does not match {len(self.image_artists)} plots"
                )
            if tuple(image.shape[1:3]) != expected_size:
                raise ValueError(
                    f"image shape {image.shape} does not match {expected_size[0]} × "
                    f"{expected_size[1]} (height × width)"
                )
            if image.ndim == 3:
                # One vectorized conversion covers every image plot of the frame.
                conversion_started = perf_counter()
                image = (np.clip(image, 0, 1) * 255).astype(np.uint8)
                conversion_ms = (perf_counter() - conversion_started) * 1000
            for artist, plot in zip(self.image_artists, image, strict=True):
                artist.set_data(plot)
        # Matplotlib uses points for stroke width, while figure.dpi includes Retina scaling.
        linewidth = 72 / self.figure.dpi
        if linewidth != self.linewidth:
            self.linewidth = linewidth
            for plot_lines in self.lines:
                for line in plot_lines:
                    line.set_linewidth(linewidth)
        artists = self.animated_artists
        if self.background is None:
            for artist in artists:
                artist.set_visible(False)
            self.draw()
            self.background = self.copy_from_bbox(self.figure.bbox)
            for artist in artists:
                artist.set_visible(True)
        self.restore_region(self.background)
        for axis, plot_lines in zip(self.waveform_axes, self.lines, strict=True):
            for line in plot_lines:
                axis.draw_artist(line)
        for axis, artist in zip(self.image_axes, self.image_artists, strict=True):
            axis.draw_artist(artist)
        self.blit(self.figure.bbox)
        return conversion_ms


def axis_viewport(axis):
    """Physical data area of the first plot of a kind, or None when that kind is hidden."""
    return None if axis is None else [float(axis.bbox.width), float(axis.bbox.height)]


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
                # Publish the plot set at once so metadata never shows the placeholder 1+1.
                self.sink.metadata.update(self.plot_metadata())
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
            **self.plot_metadata(),
        )

    def plot_metadata(self):
        """Plot counts, curves and first-plot viewports of the current plot set."""
        return {
            "render_contract": VERSION,
            "plot_viewports_all": {
                "waveform": [axis_viewport(a) for a in self.canvas.waveform_axes],
                "image": [axis_viewport(a) for a in self.canvas.image_axes],
            },
            "plot_viewport_units": "physical pixels; data drawing area excluding axes",
            "plot_viewports": {
                "waveform": axis_viewport(self.canvas.waveform_axis),
                "image": axis_viewport(self.canvas.image_axis),
            },
            "plot_counts": {
                "waveform": len(self.canvas.waveform_axes),
                "image": len(self.canvas.image_axes),
            },
            "curves": self.canvas.curves,
        }

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
