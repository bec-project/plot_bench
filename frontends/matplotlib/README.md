# Matplotlib adapter

Independent Python 3.13 environment using QtAgg, with reusable `Line2D` and
`AxesImage` artists and explicit background blitting.

From the repository root:

```sh
./scripts/setup matplotlib
./scripts/plotbench demo matplotlib
./scripts/plotbench demo matplotlib --mode replay
```

See [platform setup](../../docs/setup.md) for system requirements and
[validation](../../docs/validation.md) for test coverage.


Use the shared producer controls for source frequency/dimensions, waveform
replace/append, scalar/RGB images and waveform/image/both. Every waveform update
uses `set_data` on the full authoritative source window. Append mode is a rolling
source window, not a second client-side append buffer, so skipped frames are safe.

The baseline disables Matplotlib path simplification and Agg path chunking, uses
one physical pixel strokes without antialiasing, fixed axes, nearest-neighbor
image interpolation, and the shared 256-entry colormap with fixed [0,1] scalar
levels. RGB arrays are passed directly to `AxesImage.set_data`. No data decimation
is performed. Resizing or changing source configuration invalidates the static
background; normal updates restore it and draw only changing artists.

Scalar inputs are converted to uint8 indices with exactly
`floor(clamp(value,0,1)*255)` inside the timed update. `NoNorm` passes those indices
to the native `ListedColormap`/`AxesImage` scalar path. Matplotlib's default float
normalization uses 256 bins and would otherwise differ from the shared source
mapping. The adapter does not construct a full RGB image; native Matplotlib color
lookup remains in the draw path. `conversion_ms` records index conversion alone.
`interpolation_stage="rgba"` fixes the color-mapping stage at source resolution.
The installed Matplotlib 3.11 default `auto` also selects this stage when either
display scale is below 3, including downsampled large images. Native image
conversion and resampling overhead remains part of the measured Matplotlib path.

The HUD counts successful **submitted updates**, not display refreshes.
`update_ms` includes artist setters, scalar color mapping, synchronous Agg
rasterization and QtAgg `canvas.blit`. It excludes operating-system compositor
presentation. This timing covers more work than an asynchronous library's setter
submission time; the report must preserve the measurement-stage label instead of
ranking their setter durations as equivalent rendering costs. Receive age is only
an approximate same-host wall-clock estimate and is absent in replay.

Metadata includes NumPy and Qt versions, current window/screen geometry, screen
name/model, reported refresh rate, device scaling, and renderer environment
overrides. These values refresh at the 2 Hz HUD cadence, including screen changes.
`display.refresh_hz` is Qt's reported nominal rate, not measured presentation
frequency. Physical image dimensions use the aspect-adjusted axes bounding box.

Offscreen smoke tests verify source integration and the software draw path; real
Visible windows are required for comparable desktop benchmark runs.

Tests: `QT_QPA_PLATFORM=offscreen .envs/plotting-benchmark-matplotlib/bin/python -m pytest frontends/matplotlib/tests`.
`--duration` starts after the first successful submission and excludes replay preload.

Official reference: [Matplotlib blitting](https://matplotlib.org/stable/users/explain/animations/blitting.html).

Metric cards show parenthesized targets from the **active input frames**: submitted
updates target the configured rate, update time has a one-period budget
(`1000 / Hz` ms), skipped frames target zero, and receive age has an indicative
goal below one period. These guides are not displayed-FPS measurements or latency
guarantees; the update budget excludes deferred GPU and display presentation work.
Replay shows receive age as **N/A**. Targets remain unavailable before the first
frame and follow the active rate after stream changes or replay reloads. Hover over
a metric card for the interpretation.
