# Qt Graphs C++ adapter with a custom Qt Quick image

The same QML scene as the Python Qt Graphs adapter (`frontends/qtgraphs`), driven by a
C++ controller instead of PySide6. It helps measure how much of the
Python adapter's cost is the binding and NumPy path, and how much is Qt Graphs itself.

Requirements: a Qt 6 C++ SDK (6.8 or newer) with the Graphs, Quick, QuickControls2,
Network, WebSockets and Test modules (plus WaylandClient on Linux), CMake 3.21+
and a C++20 compiler. The SDK is a bootstrap
tool like uv or Cargo. Setup accepts normal CMake discovery, `CMAKE_PREFIX_PATH`
or an explicit `PLOTBENCH_QT_PREFIX`, and otherwise uses the newest Qt
online-installer SDK under `~/Qt`. See [platform setup](../../docs/setup.md).
Run commands from the repository root. The build lands in `frontends/qtgraphs-cpp/build/` and setup records its identity for provenance.

```sh
./scripts/setup rust qtgraphs-cpp
./scripts/plotbench demo qtgraphs-cpp
```

The default Rust source requires Rust/Cargo in addition to the C++ toolchain.
For Python input, install just `qtgraphs-cpp` and use
`./scripts/plotbench demo qtgraphs-cpp --backend python`.

For a direct adapter launch, start `./scripts/plotbench serve` in another terminal:

```sh
frontends/qtgraphs-cpp/build/plotbench-qtgraphs-cpp --url http://127.0.0.1:8765 --mode replay --duration 10
ctest --test-dir frontends/qtgraphs-cpp/build --output-on-failure
```

Waveforms use the native **Qt Graphs** `GraphsView`/`LineSeries`. The scene follows the
shared multi-plot contract of [protocol v2](../../docs/protocol.md): the controller reads
`waveform_plots`, `curves` and `image_plots` from every frame's configuration and the QML
scene creates one `GraphsView` per waveform plot (`waveformGraph-<p>`) with one `LineSeries`
per curve (`waveformSeries-<p>-<c>`) and one custom `Image` per image plot
(`streamImage-<i>`). `LineSeries` is not a Qt Quick `Item`, so a `Repeater` cannot place it
inside a `GraphsView`; each waveform panel instead builds its curves from a `Component`
(`createObject` + `GraphsView.addSeries`) once, when the panel is created, and hands the
list to the controller (`register_series`). The waveform `Repeater` is keyed on
`benchmark.waveformPanels`, a list with one entry per visible plot holding its curve count:
whenever the plot or curve count changes the `Repeater` re-instantiates every waveform panel
(`GraphsView` and `LineSeries` included); series are never removed from a live `GraphsView`,
because Qt Graphs' `PointRenderer` still polishes a removed series and crashes once it has
been destroyed. Curve `c` uses the shared palette
`CURVE_COLORS[c % 8]` (`#64dccc`, `#f5c76e`, `#7aa6ff`, `#ff9d7a`, `#c39bff`, `#9be564`,
`#ff7ab8`, `#6ee7ff`); curve 0 keeps the accent colour.

Panels sit in a `GridLayout` following the shared layout rule: waveform plots first, then
image plots, `n` visible plots in `columns = ceil(sqrt(n))` equal cells filled row-major
(1 → 1×1, 2 → side by side, 3–4 → 2×2, 5–6 → 3×2, 9 → 3×3). Titles are `Waveform` /
`Image` for a single plot of a kind and `Waveform 1`, `Image 2`, … otherwise; subtitles add
`· K curves`, and the workload strip shows `2 plots × 3 curves` / `3 plots` suffixes when the
counts exceed one. A generation change that alters `view`, `waveform_plots`, `curves` or
`image_plots` rebuilds the affected panels synchronously while the controller emits
`configChanged`, before the frame is drawn; a change of `points`, `hz` or the image size keeps
the panels and only updates their bindings.

Per frame, the controller rewrites one preallocated `QList<QPointF>` per (plot, curve) from
the contiguous `[waveform_plots, curves, points]` slice (no copy of the packet) and calls
`QXYSeries::replace` on every series, the C++ API behind the Python adapter's `replaceNp`.
Replace and append both submit the complete authoritative window. No decimation, fixed
axes, opaque one-physical-pixel lines, antialiasing off. One submission covers all plots;
`update_ms` times the whole frame.

**The image view is custom work.** Qt Graphs has no 2D image series. This adapter owns a
`QQuickImageProvider` holding one `QImage` per image plot; scalar plots become `Indexed8`
`QImage`s (index = `truncate(clamp(v, 0, 1) × 255)` in float32, as in the Python adapters)
with the shared 256-entry colour table fetched from `GET /api/colormap`; RGB plots wrap the
packet bytes at the plot's offset as `RGB888` without copying (rows are copied into an
aligned buffer only when `width × 3` is not a multiple of four). The QML `Image` of plot `i`
reloads `image://frames/<i>/<generation>/<seq>` for every frame. Qt Quick expands the
colour table and uploads the textures on the scene-graph render thread.

`update_ms` therefore includes every `replace`, the scalar index conversions, `QImage`
creation and the synchronous image-provider submission for all plots; `conversion_ms`
isolates the image part (all image plots summed). Colour
expansion, texture upload, scene-graph drawing and presentation are excluded. This
boundary is documented in `measurement_stage` and differs from the Python adapter, which
performs the RGB colour gather and a deep copy inside its timed region. The HUD shows
**submitted updates/s**, not display FPS.

Telemetry matches the shared contract: batches once per second to `/api/metrics`, bounded
pending memory with loss accounting, a final flush with `termination_reason`,
`active_seconds` and `expected_duration`, and per-HUD-tick metadata (QScreen identity and
nominal refresh, window geometry, pixel ratio, renderer environment overrides, active
graphics API, physical plot areas). `plot_viewports` is the data area of the first plot of
each kind (all cells are equal), `plot_counts` the visible counts (0 for a kind hidden by
`view`), `curves` the curves per waveform plot, and `grid_columns` (an addition specific to
this adapter) the column count of the shared layout rule in effect. `receiver_connection_epoch`
counts (re)connections.
`--duration` starts after the first successful submission and excludes replay preload.

The native Qt Graphs module is available under **GPLv3 or a commercial Qt license**.
Decoder tests run with `ctest`; they cover the v2 binary frame layout (3-D waveform and
3-D/4-D image shapes validated against the header configuration, scalar and RGB), per-plot
slice offsets, the image provider's per-plot conversion (Indexed8 indices, RGB slices, and
rejection of shapes it cannot index), rejection of malformed and version-1 packets and the
replay container. Frames whose arrays do not have the v2 layout (possible only from a packet
without a header configuration) stop the adapter with a protocol error (`termination_reason`
`error`, exit status 1). Rendering is validated only with the visible window; the manual
checks are the offscreen stream and replay runs plus live `POST /api/config` changes during a
run covering a curves-only change (with several plots and with a single plot), a plot-count
change, a `view` change and a points-only change, each expecting exit status 0 and continuous
samples across generations.
