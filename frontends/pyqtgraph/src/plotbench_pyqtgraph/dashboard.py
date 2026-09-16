"""Presentation shell; plotting and measurement remain in the frontend adapter."""

import math

from qtpy.QtCore import QSignalBlocker, Qt, QUrl, Signal
from qtpy.QtGui import QDesktopServices
from qtpy.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

BACKGROUND = "#0b141c"
PANEL = "#111e28"
BORDER = "#253745"
TEXT = "#d8e6ed"
MUTED = "#8fa7b6"
ACCENT = "#64dccc"
ERROR = "#ffa7a7"
METRIC_GUIDE = "Targets follow the current input frame rate. The update budget is one source period and excludes deferred GPU and display presentation work. The receive-age goal is indicative; it is not a latency guarantee. These are not displayed-FPS measurements. Replay has no receive age."


def label(text, role):
    widget = QLabel(text)
    widget.setObjectName(role)
    return widget


def grid_shape(count):
    """Shared layout rule: (columns, rows) for `count` visible plots, filled row-major.

    columns = ceil(sqrt(n)) and rows = ceil(n / columns), so 1 → 1×1, 2 → 2×1,
    3 and 4 → 2×2, 5 and 6 → 3×2, 9 → 3×3. An empty set of plots has no cells.
    """
    if count <= 0:
        return 0, 0
    columns = math.ceil(math.sqrt(count))
    return columns, math.ceil(count / columns)


def plot_title(kind, index, count):
    """`Waveform` / `Image` for a single plot of a kind, else `Waveform 1`, `Waveform 2`, …"""
    return kind if count == 1 else f"{kind} {index + 1}"


def plural(count, noun):
    return f"{count} {noun}{'' if count == 1 else 's'}"


def waveform_layout_suffix(config):
    """` · 2 plots × 3 curves` when either count exceeds one, else empty."""
    plots, curves = config["waveform_plots"], config["curves"]
    if plots == 1 and curves == 1:
        return ""
    return f" · {plural(plots, 'plot')} × {plural(curves, 'curve')}"


def image_layout_suffix(config):
    """` · 3 plots` when more than one image plot is shown, else empty."""
    return f" · {plural(config['image_plots'], 'plot')}" if config["image_plots"] > 1 else ""


class PlotCard(QFrame):
    def __init__(self, title):
        super().__init__()
        self.setObjectName("panel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 8)
        layout.setSpacing(5)
        self.title = label(title, "plotTitle")
        layout.addWidget(self.title)
        self.subtitle = label("Waiting for source", "muted")
        layout.addWidget(self.subtitle)
        self.content = QVBoxLayout()
        self.content.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.content, 1)


class Dashboard(QWidget):
    viewRequested = Signal(str)

    def __init__(self, title, renderer, mode, url):
        super().__init__()
        self.setObjectName("dashboard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.renderer = renderer
        self.mode = mode
        self._view = None
        self._view_pending = False
        self._view_error = None
        self._view_locked = False
        self.setStyleSheet(f"""
            QWidget#dashboard {{ background: {BACKGROUND}; }}
            QLabel {{ color: {TEXT}; background: transparent; border: none;
                      font-family: "Helvetica Neue"; font-size: 12px; }}
            QLabel#eyebrow {{ color: {MUTED}; font-size: 10px; font-weight: 600; }}
            QLabel#title {{ font-size: 20px; font-weight: 600; }}
            QLabel#badge {{ color: {ACCENT}; background: #173239; border: 1px solid #285052;
                           border-radius: 5px; padding: 5px 8px; font-size: 10px; }}
            QLabel#muted, QLabel#metricLabel {{ color: {MUTED}; font-size: 11px; }}
            QLabel#summaryValue {{ font-size: 12px; font-weight: 500; }}
            QLabel#metricValue {{ font-size: 18px; font-weight: 600; }}
            QLabel#metricTarget {{ color: {MUTED}; font-size: 10px; }}
            QLabel#plotTitle {{ font-size: 16px; font-weight: 600; }}
            QLabel#footer {{ color: {MUTED}; font-size: 10px; }}
            QFrame#panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 9px; }}
            QPushButton {{ color: {BACKGROUND}; background: {ACCENT}; border: none;
                           border-radius: 6px; padding: 5px 12px;
                           font-family: "Helvetica Neue"; font-size: 12px; font-weight: 600; }}
            QPushButton:hover {{ background: #85e7da; }}
            QPushButton:pressed {{ background: #42bbaa; }}
            QPushButton#plotToggle {{ color: {MUTED}; background: {BACKGROUND};
                border: 1px solid {BORDER}; border-radius: 4px; padding: 2px 9px;
                font-size: 11px; min-width: 22px; }}
            QPushButton#plotToggle:checked {{ color: {ACCENT}; background: #173239;
                border-color: #285052; }}
            QPushButton#plotToggle:hover {{ border-color: {ACCENT}; }}
            QPushButton#plotToggle:disabled {{ border-color: {BORDER}; }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(8)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(7)
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title_row.addWidget(label(title, "title"))
        title_row.addWidget(label(f"{renderer} · {mode.title()}", "badge"))
        title_row.addStretch()
        heading.addLayout(title_row)
        header.addLayout(heading, 1)
        actions = QHBoxLayout()
        actions.setSpacing(7)
        self.connection = label("● Connecting", "muted")
        self.connection.setAlignment(Qt.AlignmentFlag.AlignRight)
        actions.addWidget(self.connection)
        controls = QPushButton("Source controls  ↗")
        controls.setCursor(Qt.CursorShape.PointingHandCursor)
        controls.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        actions.addWidget(controls)
        header.addLayout(actions)
        layout.addLayout(header)

        summary = QFrame()
        summary.setObjectName("panel")
        summary.setFixedHeight(40)
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(12, 4, 12, 4)
        summary_layout.setSpacing(18)
        self.summary_values = []
        for text in ("TARGET RATE", "WAVEFORM", "IMAGE"):
            column = QVBoxLayout()
            column.setSpacing(0)
            column.addWidget(label(text, "eyebrow"))
            value = label("—", "summaryValue")
            column.addWidget(value)
            summary_layout.addLayout(column, 1)
            self.summary_values.append(value)
        plot_column = QVBoxLayout()
        plot_column.setSpacing(0)
        plot_column.addWidget(label("PLOTS", "eyebrow"))
        toggles = QHBoxLayout()
        toggles.setSpacing(6)
        self.plot_buttons = {}
        for plot, button_text, description in (
            ("waveform", "1D", "1D waveform"),
            ("image", "2D", "2D image"),
        ):
            button = QPushButton(button_text)
            button.setObjectName("plotToggle")
            button.setAccessibleName(description)
            button.setCheckable(True)
            button.setFixedHeight(23)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked, name=plot: self.request_plot(name, checked))
            toggles.addWidget(button)
            self.plot_buttons[plot] = button
        toggles.addStretch()
        plot_column.addLayout(toggles)
        summary_layout.addLayout(plot_column, 1)
        self.sync_plot_controls()
        layout.addWidget(summary)

        metrics = QHBoxLayout()
        metrics.setSpacing(14)
        self.metric_values = []
        self.metric_targets = []
        for text in ("Submitted", "Update time", "Skipped", "Receive age"):
            card = QFrame()
            card.setObjectName("panel")
            card.setFixedHeight(48)
            column = QVBoxLayout(card)
            column.setContentsMargins(12, 4, 12, 4)
            column.setSpacing(0)
            column.addWidget(label(text, "metricLabel"))
            value = label("—", "metricValue")
            column.addWidget(value)
            target = label("", "metricTarget")
            column.addWidget(target)
            target.hide()
            card.setToolTip(METRIC_GUIDE)
            self.metric_targets.append(target)
            metrics.addWidget(card, 1)
            self.metric_values.append(value)
        self.update_metric_targets(None)
        layout.addLayout(metrics)

        self.plots = QGridLayout()
        self.plots.setSpacing(16)
        layout.addLayout(self.plots, 1)
        footer = QHBoxLayout()
        footer.addWidget(label("Submitted updates · not displayed FPS", "footer"))
        footer.addStretch()
        self.resources = label(renderer, "footer")
        footer.addWidget(self.resources)
        layout.addLayout(footer)

    def arrange_plots(self, cards):
        """Place `cards` (waveform plots first, then image plots) on the shared grid.

        Every cell gets the same stretch; cards no longer listed are detached from
        the grid and hidden so the caller can delete them. Trailing cells stay empty.
        """
        while self.plots.count():
            widget = self.plots.takeAt(0).widget()
            if widget is not None and widget not in cards:
                widget.hide()
        for column in range(self.plots.columnCount()):
            self.plots.setColumnStretch(column, 0)
        for row in range(self.plots.rowCount()):
            self.plots.setRowStretch(row, 0)
        columns, rows = grid_shape(len(cards))
        for index, card in enumerate(cards):
            self.plots.addWidget(card, index // columns, index % columns)
            card.show()
        for column in range(columns):
            self.plots.setColumnStretch(column, 1)
        for row in range(rows):
            self.plots.setRowStretch(row, 1)

    def update_summary(self, config):
        if config is None:
            return
        values = (
            f"{config['hz']:g} Hz",
            f"{config['points']:,} · {config['waveform_mode']}{waveform_layout_suffix(config)}",
            f"{config['width']} × {config['height']} · {config['image_mode'].upper() if config['image_mode'] == 'rgb' else 'scalar'}{image_layout_suffix(config)}",
        )
        for widget, value in zip(self.summary_values, values, strict=True):
            widget.setText(value)
        self.update_metric_targets(config["hz"])
        self._view = config["view"]
        self.sync_plot_controls(self._view_pending, self._view_error, self._view_locked)

    def update_metric_targets(self, hz):
        if hz is None:
            targets = [
                "(waiting for source)",
                "(waiting for source)",
                "(target 0)",
                "(waiting for source)",
            ]
        else:
            period_ms = 1000 / hz
            targets = [
                f"(target {hz:g}/s)",
                f"(budget ≤{period_ms:.2f} ms)",
                "(target 0)",
                f"(goal <{period_ms:.2f} ms)",
            ]
        if self.mode == "replay":
            targets[3] = "(N/A in replay)"
        for widget, target in zip(self.metric_targets, targets, strict=True):
            widget.setText(target)

    def sync_plot_controls(self, pending=False, error=None, locked=False):
        self._view_pending = pending
        self._view_error = error
        self._view_locked = locked
        for plot, button in self.plot_buttons.items():
            selected = self._view in ("both", plot)
            last_enabled = self._view == plot
            with QSignalBlocker(button):
                button.setChecked(selected)
            button.setEnabled(bool(self._view) and not (pending or locked or last_enabled))
            if locked:
                reason = "Locked during recorded runs"
            elif self._view is None:
                reason = "Waiting for the shared source"
            elif pending:
                reason = "Updating shared source…"
            elif error:
                reason = error
            elif last_enabled:
                reason = "At least one plot must remain enabled"
            else:
                reason = "Update the shared source"
                if self.mode == "replay":
                    reason += " and reload replay"
            button.setToolTip(f"{button.accessibleName()} · {reason}")

    def request_plot(self, plot, checked):
        if (
            plot not in self.plot_buttons
            or self._view is None
            or self._view_pending
            or self._view_locked
        ):
            self.sync_plot_controls(self._view_pending, self._view_error, self._view_locked)
            return
        selected = {"waveform", "image"} if self._view == "both" else {self._view}
        if checked:
            selected.add(plot)
        else:
            selected.discard(plot)
        if selected:
            view = "both" if len(selected) == 2 else next(iter(selected))
            if view != self._view:
                self.viewRequested.emit(view)
        # Requests never optimistically change the check state: incoming frames are authoritative.
        self.sync_plot_controls(self._view_pending, self._view_error, self._view_locked)

    def update_metrics(self, metrics, status, error, cpu, rss, renderer_note):
        age = metrics.get("receive_age_ms")
        values = (
            (f"{metrics['updates_hz']:.1f}", "/s"),
            (f"{metrics['update_ms']:.2f}", "ms"),
            (f"{metrics['skipped']:,}", ""),
            (
                ("—", "replay" if self.mode == "replay" else "")
                if age is None
                else (f"{age:.1f}", "ms")
            ),
        )
        for widget, (value, unit) in zip(self.metric_values, values, strict=True):
            widget.setText(f'{value} <span style="font-size:12px;color:{MUTED}">{unit}</span>')
        connection = (
            "Source error" if error else ("Replaying" if self.mode == "replay" else "Streaming")
        )
        if metrics["count"] == 0 and not error:
            connection = "Connecting"
        self.connection.setText(f"● {connection}")
        self.connection.setStyleSheet(f"color: {ERROR if error else ACCENT}; font-size: 11px;")
        self.connection.setToolTip(error or status)
        self.resources.setText(f"CPU {cpu:.0f}% · {rss:.0f} MiB · {renderer_note}")
