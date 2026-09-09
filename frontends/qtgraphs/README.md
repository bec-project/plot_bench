# Qt Graphs and custom Qt Quick image adapter

Independent Python 3.13 + PySide6 environment. Waveforms use **Qt Graphs** QML
`GraphsView`/`LineSeries`, bulk-updated with `QLineSeries.replaceNp`. This does not
use the deprecated Qt Charts module. qtpy supplies ordinary Qt types; QtGraphs is
imported from PySide6 because qtpy does not wrap this module.

From the monorepo root (start the shared producer first):

```sh
UV_CACHE_DIR="$PWD/.cache/uv" UV_PYTHON_INSTALL_DIR="$PWD/.envs/python" \
UV_PROJECT_ENVIRONMENT="$PWD/.envs/plotting-benchmark-qtgraphs" \
uv sync --project frontends/qtgraphs --python 3.13.14
.envs/plotting-benchmark-qtgraphs/bin/plotbench-qtgraphs
.envs/plotting-benchmark-qtgraphs/bin/plotbench-qtgraphs --mode replay --duration 10
```

**The image view requires additional custom work.** Qt Graphs does not provide a
native 2D scalar/RGB image series. This adapter implements a `QQuickImageProvider`,
owns a detached RGB `QImage`, maps scalar arrays through the common LUT on the CPU,
invalidates the QML image source for every frame, and supplies image axes/layout.
Qt Quick then uploads/displays the image texture. The UI, metadata, and report
label this as custom Qt Quick image rendering; do not attribute that capability
to a built-in Qt Graphs image plot. Native color-bar, pixel picking and scientific
image tools would need more custom work and are outside this benchmark.

Replace and append both bulk-replace the complete authoritative rolling window.
No Python `QPointF` objects are allocated per point and no hidden decimation is
performed. Lines are one physical pixel wide; axes use fixed limits, image display
uses nearest-neighbor interpolation, and scalar color limits remain [0,1]. The
source controls select waveform/image/both and scalar/RGB workloads.

`update_ms` includes `replaceNp`, scalar color mapping/RGB QImage ownership copy,
and synchronous image-provider submission. `conversion_ms` isolates image
conversion/ownership work. GPU uploads, scene-graph drawing and compositor
presentation are asynchronous and excluded. The HUD shows **submitted updates/s**,
not display FPS. Exact active Qt Quick graphics API, pixel ratio and view sizes
are attached to telemetry. The default macOS Qt Quick backend is selected by Qt;
do not assume it is OpenGL. `QSG_RHI_BACKEND` overrides, if used, should be recorded
with benchmark provenance.

NumPy version, screen name/model, window/screen geometry, device scaling, reported
refresh rate and renderer environment overrides (including `QSG_RENDER_LOOP`) are
recorded at the 2 Hz HUD cadence. Moving the window between displays updates this
metadata. `display.refresh_hz` is Qt's reported nominal rate, not measured display
presentation; an unset `QSG_RENDER_LOOP` does not establish the selected loop.
The image area is the aspect-fitted painted rectangle, excluding letterboxing.

The native **Qt Graphs module is available under GPLv3 or a commercial Qt license**,
not LGPL. The PySide binding files' license alternatives do not change the native
module's licensing. See the official [Qt Graphs license information](https://doc.qt.io/qt-6/qtgraphs-index.html#licenses-and-attributions).

Headless tests can validate native series replacement and image conversion but
are not representative of a visible GPU rendering path. Benchmark the visible window.

Tests: `QT_QPA_PLATFORM=offscreen .envs/plotting-benchmark-qtgraphs/bin/python -m pytest frontends/qtgraphs/tests`.
`--duration` starts after the first successful submission and excludes replay preload.

Official references: [Qt Graphs](https://doc.qt.io/qt-6/qtgraphs-index.html),
[LineSeries](https://doc.qt.io/qt-6/qml-qtgraphs-lineseries.html),
[QXYSeries NumPy API](https://doc.qt.io/qtforpython-6/PySide6/QtGraphs/QXYSeries.html),
[image providers](https://doc.qt.io/qtforpython-6/PySide6/QtQuick/QQuickImageProvider.html).

Metric cards show parenthesized targets from the **active input frames**: submitted
updates target the configured rate, update time has a one-period budget
(`1000 / Hz` ms), skipped frames target zero, and receive age has an indicative
goal below one period. These guides are not displayed-FPS measurements or latency
guarantees; the update budget excludes deferred GPU and display presentation work.
Replay shows receive age as **N/A**. Targets remain unavailable before the first
frame and follow the active rate after stream changes or replay reloads. Hover over
a metric card for the interpretation.
