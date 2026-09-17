# Adding a plotting frontend

Keep the existing design: an independently packaged executable consumes the
common source protocol and exports telemetry. No dynamic plugin framework or
frontend-specific generator is required.

## Implement the adapter

Create `frontends/NAME/` with its package/build manifest, dependency lock, README,
source and focused tests. Follow a nearby frontend in the same language. Python
packages use a sibling editable `plotbench-core` dependency and their own local
environment; use `qtpy` where it exposes the needed Qt API.

Implement the [executable arguments and wire contract](protocol.md). The executable
accepts source URL, stream/replay mode, run ID, duration and logical window size.
Start the duration clock after the first successful submission, excluding replay
preload. Support waveform-only, image-only and combined views, both waveform modes,
and scalar/RGB images. Match fixed axes, color limits, LUT, nearest-neighbor image
sampling and full-data rendering. Describe any unsupported behavior explicitly.
Scalar color mapping may differ by one adjacent LUT entry because of numeric
rounding, as described in the [protocol](protocol.md); exact RGB equality between
adapters is not required. Apply the same tolerance to scalar and SIMD implementations.

Support multi-plot workloads: create `waveform_plots` waveform widgets, each
drawing `curves` curves, and `image_plots` image widgets from the current config,
and rebuild that widget set when the generation changes the counts. Protocol v2
always ships the waveform as `[waveform_plots, curves, points]` and images as
`[image_plots, height, width(, 3)]`; validate the exact shape against the config
and slice plots and curves without copying where the language allows. Arrange the
visible plots with the shared grid rule (waveforms first, then images,
`columns = ceil(sqrt(n))`, `rows = ceil(n / columns)`, row-major, equal cells),
title them `Waveform 1..N` / `Image 1..M` (plain `Waveform` / `Image` for a single
plot of a kind) and colour curve `c` with the shared `CURVE_COLORS[c % 8]`
palette; see [presentation](presentation.md). One update submission per frame
covers all plots: `update_ms` times the whole frame and `conversion_ms` all image
conversions in it. Record `plot_counts` and `curves` in metadata, and keep
`plot_viewports` as the data area of the first plot of each kind. Follow the
versioned [data-area contract](presentation.md#data-area-contract-data-area-v2),
record `render_contract` and report independently measured `plot_viewports_all`
for every visible plot. Reports reject mismatched geometry.

Python adapters can reuse `FrameSource`, `MetricsSink` and `frontend_parser` from
`plotbench.client`. Other languages implement the documented transport directly.
Preserve bounded mailboxes, ACKs, authoritative append windows, reconnect behavior,
and bounded CPU replay. Do not generate data, silently downsample, or preload every
replay frame into GPU resources.

Palette tables, reusable output storage, static decorations and equivalent SIMD
conversion are valid optimizations for any adapter. Dynamic source data must still
be adopted and rendered for each counted update. Cache invalidation must cover
changed values, dimensions, plot counts and source generations; repeating replay
input does not permit caching fully converted frames. Keep the selected renderer
and required full-data work explicit, and report conversion kernels and renderer
overrides so different execution modes remain separate in comparisons.

## Define telemetry

Record submission count, sequence/generation, skips, receive age and synchronous
update duration. Name the work inside each timer, conversion ownership/copies,
deferred rendering and any asynchronous completion signal. Preserve sample loss
accounting and completion/termination metadata; flush final telemetry on exit.

Record library/compiler versions, graphics API, actual scaling and plot region,
display protocol, and renderer overrides where available. Unknown information
stays unknown. Follow [presentation conventions](presentation.md) and explain
custom waveform/image/axis rendering in both the UI and README.

## Register and build

1. Add the frontend ID to the shared suite catalog and its launch command to the
   runner. The CLI/editor must obtain accepted IDs from the shared catalog.
2. Extend setup and doctor with the component's environment/build prerequisites.
   Build release artifacts for measurements.
3. For compiled or bundled components, register artifact paths and source/build
   fingerprints in provenance, and include the component in runner preflight.
   Source changes must invalidate stale build artifacts.
4. Add the adapter's timing/metadata fields to report interpretation where needed.
   Preserve context separation and existing metrics; do not invent comparable
   GPU/presentation timings from unlike API boundaries.
5. Add a small scenario example, README entry and CI coverage. Keep expensive or
   optional SDK frontends out of the single-component quick start.
6. Decide whether the frontend joins the official baseline suite. Membership is
   explicit: add its ID to the `frontends` list of `scenarios/baseline.json` (the
   core suite test checks that every listed frontend exists in the shared catalog;
   a subset is allowed) and run the
   website checks, because the community results site publishes baseline
   campaigns only. A frontend outside that list can be measured locally but never
   appears on the site's section boards or overall ranking. Its adapter must
   report non-empty library versions in its metadata: records with incomplete
   context are excluded from the winner boards.

Go adapters use an independent `go.mod` / `go.sum`; keep module/build caches local,
use read-only dependency resolution for builds, and register `.go`, `.mod` and
`.sum` files in provenance. Fyne provides a reference at `frontends/fyne/`.
The `fyne-wasm` browser target shares that Go module and renderer while keeping a
separate frontend ID, build artifacts, browser runtime identity and telemetry.
It is part of the official baseline as its own frontend. Shared implementation
does not make native and browser results interchangeable.

## Acceptance

Test malformed frames, array layout, append/replay behavior, bounded delivery,
conversion correctness and clean completion, including the multi-plot slicing and
the grid layout. Exercise both backends with visible short stream/replay runs
(`scenarios/smoke.json` and `scenarios/multi-plot-smoke.json`) and verify
complete, usable telemetry. Before proposing the frontend for the baseline, run
the seven sections once in their published form on a visible desktop
(substitute your frontend's ID for `pyqtgraph`) and confirm every section
completes with recorded versions, display scale and plot areas:

```sh
./scripts/plotbench run --suite scenarios/baseline.json --frontends pyqtgraph --warmup 1 --duration 3 --repetitions 1 --output results/acceptance-quick
./scripts/plotbench run --baseline --frontends pyqtgraph --output results/acceptance
```

The first, shortened pass is a quick functional check of the same seven sections
and is not publishable; the second is a real baseline campaign.
Test view changes outside recorded runs. Use screenshots only outside
measurement windows.

Confirm repeated runs have stable runtime identity, source limitations stay
visible, and failures remain in the report. State which OS/display combinations
were actually tested; offscreen tests do not validate GPU performance.

Java adapters can use an independent JDK build with checksum-locked dependency
JARs. JFreeChart is the reference at `frontends/jfreechart/`: setup invokes its
build script, deployed JARs are fingerprinted separately from temporary classes,
and `.java` sources plus the dependency lock participate in stale-build checks.
Record compiler and runtime separately and allow explicit JVM warmup.
