# Qt Graphs C++ adapter with a custom Qt Quick image

The same QML scene as the Python Qt Graphs adapter (`frontends/qtgraphs`), driven by a
C++ controller instead of PySide6. It helps measure how much of the
Python adapter's cost is the binding and NumPy path, and how much is Qt Graphs itself.

Requirements: a Qt 6 C++ SDK (6.8 or newer) with the Graphs, Quick, QuickControls2,
Network and WebSockets modules, CMake 3.21+ and a C++20 compiler. The SDK is a bootstrap
tool like uv or Cargo; `./scripts/setup qtgraphs-cpp` looks in `~/Qt/6.*/macos` and
`/opt/homebrew/opt/qt`, or use `PLOTBENCH_QT_PREFIX`. The build lands in `build/` and
setup records the executable's identity for benchmark provenance.

```sh
./scripts/setup qtgraphs-cpp
./scripts/plotbench demo qtgraphs-cpp --backend rust
build/plotbench-qtgraphs-cpp --url http://127.0.0.1:8765 --mode replay --duration 10
cd frontends/qtgraphs-cpp/build && ctest --output-on-failure
```

Waveforms use the native **Qt Graphs** `GraphsView`/`LineSeries`; each frame rewrites one
preallocated `QList<QPointF>` and calls `QXYSeries::replace`, the C++ API behind the Python
adapter's `replaceNp`. Replace and append both submit the complete authoritative window.
No decimation, fixed axes, opaque one-physical-pixel lines, antialiasing off.

**The image view is custom work.** Qt Graphs has no 2D image series. This adapter owns a
`QQuickImageProvider`; scalar frames become an `Indexed8` `QImage` (index =
`truncate(clamp(v, 0, 1) × 255)` in float32, as in the Python adapters) with the shared
256-entry colour table fetched from `GET /api/colormap`; RGB frames wrap the packet bytes
as `RGB888` without copying. The QML `Image` reloads the provider URL for every frame.
Qt Quick expands the colour table and uploads the texture on the scene-graph render thread.

`update_ms` therefore includes `replace`, the scalar index conversion, `QImage` creation and
the synchronous image-provider submission; `conversion_ms` isolates the image part. Colour
expansion, texture upload, scene-graph drawing and presentation are excluded. This
boundary is documented in `measurement_stage` and differs from the Python adapter, which
performs the RGB colour gather and a deep copy inside its timed region. The HUD shows
**submitted updates/s**, not display FPS.

Telemetry matches the shared contract: batches once per second to `/api/metrics`, bounded
pending memory with loss accounting, a final flush with `termination_reason`,
`active_seconds` and `expected_duration`, and per-HUD-tick metadata (QScreen identity and
nominal refresh, window geometry, pixel ratio, renderer environment overrides, active
graphics API, physical plot areas). `receiver_connection_epoch` counts (re)connections.
`--duration` starts after the first successful submission and excludes replay preload.

The native Qt Graphs module is available under **GPLv3 or a commercial Qt license**.
Decoder tests run with `ctest`; they cover the binary frame layout, rejection of malformed
packets and the replay container. Rendering is validated only with the visible window.
