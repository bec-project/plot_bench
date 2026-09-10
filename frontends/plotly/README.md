# React + Plotly frontend

An independent TypeScript/React application for the shared Plotbench source. It contains no data
generator and has its own exact npm dependency lock. No Python, Qt, or Rust packages are installed
in this frontend.

## Run

From the repository root, install Rust/Cargo and npm, then build the default
source and browser frontend:

```sh
./scripts/setup rust plotly
./scripts/plotbench demo plotly
```

For Python input, install just `plotly` and select
`./scripts/plotbench demo plotly --backend python`;
this does not require Rust/Cargo. See [platform setup](../../docs/setup.md) for
browser prerequisites and explicit browser selection.

For a direct browser launch, use Node/npm compatible with
[`package.json`](package.json); [`.node-version`](../../.node-version) records the
repository's tested Node version. Start the shared source in another terminal
(`serve` defaults to Rust; use `serve --backend python` for Python), then run from
the repository root. The provenance command needs the core installed by setup:

```sh
npm ci --prefix frontends/plotly --cache "$PWD/.cache/npm" --no-audit --no-fund
npm --prefix frontends/plotly test
npm --prefix frontends/plotly run build
.envs/plotting-benchmark/bin/python -m plotbench.provenance plotly
npm --prefix frontends/plotly run preview
```

Open [the preview](http://127.0.0.1:4173/). Use
`npm --prefix frontends/plotly run dev` at port 5173 for development; benchmark
the production build to exclude development-server instrumentation. Vite binds only to localhost.
The default source address is `http://127.0.0.1:8765`; the core must allow this origin through CORS.

The application supports these query parameters:

| Parameter | Default | Meaning |
| --- | --- | --- |
| `url` | `http://127.0.0.1:8765` | Shared source base URL |
| `mode` | `stream` | `stream` or centrally preloaded `replay` |
| `run_id` | `demo` | Identifier attached to uploaded measurements |
| `duration` | `0` | Seconds after the first successful update; zero runs until stopped |
| `width` | `1100` | Requested logical application width |
| `height` | `820` | Requested logical application height |

For example:

```text
http://127.0.0.1:4173/?mode=replay&run_id=plotly-replay&duration=35&width=1100&height=820
```

Set the browser viewport to the requested dimensions in automation. Query parameters cannot resize
the browser itself. The actual viewport, device pixel ratio and individual plot sizes are recorded
in metadata. `plot_viewports` contains physical data-area dimensions excluding axes and margins;
`plot_viewports_logical` records those lengths in CSS pixels and `plot_containers` separately records
the outer chart boxes. Hidden plots are null. Data areas use Plotly 4's resolved axis lengths,
including aspect-ratio domain constraints; unavailable diagnostics remain null rather than guessed.
Keep the window visible and foreground during comparative performance measurements;
headless runs are useful for functional smoke tests.

The header's **Source controls** drawer is collapsed initially to leave the plots visible. It
contains the workload form, input-mode selector, a link to the common source page and `Stop & save`.
The compact workload strip and four metric cards remain visible. Combined view uses equal-width
plot cards; one selected view fills the width. The layout follows the browser viewport and supports
860 × 640 through the default 1100 × 820 without hiding controls or metric values.

The controls change the **shared source** through `POST /api/config`, including frequency, point
count, append size, image dimensions and scalar/RGB mode. The workload strip's **1D** and **2D**
buttons select waveform, image or both by changing the source's `view` alone. Turning a plot off
removes its array from source packets and gives the remaining plot the full card width. At least
one plot stays enabled; enable the other first to switch between single plots. Buttons are disabled
until configuration arrives, while a request is pending, after stopping and during duration-limited
recorded runs. A failed request preserves the confirmed selection, shows an error and permits retry.
The drawer submits only fields edited by the user, so stale forms cannot restore an old view or
other settings changed elsewhere. Confirmed updates refresh pristine fields while preserving unsaved
edits, including edits made while a request is pending. Failed requests retain those edits for retry.

These controls update the shared source for other connected stream demos. Stream demos also follow
configuration changes made by another frontend or the source page. Replay holds its bounded CPU
sequence until this frontend's own controls fetch a replacement; external changes do not alter an
already-preloaded replay. Its 1D/2D buttons reload that sequence too. The old sequence keeps playing
until a replacement is downloaded and validated. If that preload fails, the old replay and selected
buttons remain intact and permit retry; the shared source may already have accepted the new view.
Choosing a different input mode reloads the page.

## What is measured

React owns the controls and a HUD refreshed twice per second. Plotly owns the actual plot DOM.
Frame arrays stay outside React state. A scheduler keeps one active asynchronous Plotly update and
one replaceable pending frame. It never deliberately queues a growing history of plot operations.
After decoding and offering each WebSocket packet, the client immediately sends
`{"ack": sequence, "generation": generation}` before deferred plotting begins. The source permits
one packet in flight per client and sends the newest available frame after that acknowledgment,
bounding browser transport/event buffering as well as the application mailbox. Every received
packet is acknowledged, including a superseded configuration generation. An acknowledgment returns
transport credit; it does not claim that a frame was drawn. Streaming still includes transport costs.

HUD state updates, React reconciliation and their browser layout/paint work run outside the explicit
`update_ms` boundary. They still compete for the same main thread and affect achieved throughput and
process CPU. Plot geometry reads and any consequent synchronous layout during an adapter call are
included in `conversion_ms`. This demo measures the adapter in a live GUI, with that bounded HUD
overhead retained and disclosed; it is not a detached plotting microbenchmark.

| Workload | Implementation |
| --- | --- |
| Waveform replace | `scattergl`, full authoritative float32 window supplied to `Plotly.react` |
| Waveform append | Same full-window submission, displaying the source's rolling window |
| Scalar image | `heatmap`, row views over the float32 buffer, shared color table, fixed `[0, 1]` |
| RGB image | Native Plotly `image` trace, materialized nested RGB triples |

Append is a data-semantics comparison here: **this adapter does not use `extendTraces`**. Full
replacement preserves fixed sample indices and recovers immediately after dropped frames. It does
not represent the best possible performance of a separately optimized incremental Plotly adapter.
Waveforms use no point markers or decimation, fixed axes and a one-physical-pixel line. Images use
nearest-neighbor interpolation (`zsmooth: false`) and an equal spatial aspect ratio. The scalar
colorscale uses repeated boundaries to match the core's discrete `floor(value * 255)` lookup.

The RGB trace's `z` input requires nested pixel arrays, so this adapter converts the shared
interleaved RGB buffer on every update. That allocation/conversion can be substantial at 2048²
and is included in the measurements. Plotly also supports `image.source` data URIs; that would be
a different adapter, with URI preparation/loading included in its measurements. The scalar image
path uses typed-array row views, leaving color mapping and rasterization to Plotly. These results
describe the selected trace APIs and do not establish a ceiling for optimized browser image paths.

* `update_ms`: monotonic elapsed time for conversion and synchronous `Plotly.react` calls.
* `conversion_ms`: preparing traces, row views/RGB triples, layout and visibility.
* `draw_ms`: synchronous Plotly update calls; already included in `update_ms` and excludes waiting
  for their returned Promises. Adding it to `update_ms` would count that work twice.
* `update_complete_ms`: elapsed time from adapter-call start through successful completion of all
  active Plotly Promises. Includes conversion, synchronous calls, deferred library work and wait.
  RGB rasterization/PNG creation can run after synchronous submission and is included here.
  This is not GPU time, screen presentation time, or a measurement of CPU execution alone.
* Submitted updates: increments after both active Plotly Promises resolve successfully. Calls are
  serialized until that point. Promise resolution is not a GPU fence or proof of screen presentation.
* Skipped updates: source sequence gaps between submitted frames, reset when configuration changes.
* Approximate receive age: local wall-clock time at update start minus source emission time. Negative
  estimates are retained. This is null for replay and is not presentation latency.

Each metric card has a live hint: the source rate for Submitted, one source period (`1000 / Hz` ms)
as the Update time budget and Receive age freshness goal, and zero for Skipped. Replay receive age
is marked N/A. These are practical throughput and freshness heuristics; staying below the source
period does not prove GPU completion or screen presentation.

The HUD therefore says **submitted updates/s**, not displayed FPS. Replay preloads at most the
server's 256 MiB cap and cycles changing CPU arrays at the source target rate; it does not preload
GPU frames. Timer delays advance directly to the newest replay tick. Metadata records the actual
`replay_frames` and `replay_bytes`, and the finite cache-warm nature of this mode.

Metrics are batched approximately once per second. An upload failure is visible, retried, and uses
a bounded 512-sample buffer; evicted samples are counted explicitly. `Stop & save` waits for the
active plot update and final metrics upload. A duration-limited run sets
`window.__plotbenchStatus.complete = true` and `running = false` **after** that final flush. Automation
must also verify `error === null`, `submitted > 0`, and `stop_reason === 'duration'` for scheduled
runs. The other stop reasons are `user`, `error` and `dispose`. Closing a tab abruptly cannot guarantee a final
network upload; use the stop button or duration for recorded runs.

The browser worker exposes `window.__plotbenchLifecycle` before loading the page. The engine calls
it after its first successfully recorded submission and after stopping and flushing metrics. There
is no repeated CDP status evaluation during measurement. Early window closure, page errors,
missing startup/completion signals, telemetry errors and premature stops fail a recorded run.
An untimed demo remains open across Stop/Restart and exits when its window closes. A requested
`--screenshot` requires a positive `--duration` and is captured only after timed completion and
the final frontend telemetry flush; preview work is outside the measurement window. Final worker
metadata records whether capture was requested and succeeded. Metadata is exported at shutdown
even if the periodic upload already drained all samples.

Before streaming or replay preload, `browser_context` records the browser-reported screen,
available screen area, window position/dimensions, DPR, focus/visibility, cross-origin isolation,
secure-context state and a bounded sample of `performance.now()` increments. The minimum positive
observed increment may be null and is not a guaranteed timer resolution. Screen/window values may
reflect browser emulation. Actual refresh rate remains unavailable: record the controlled display
configuration separately. Existing per-update viewport and plot-area metadata track actual layout.
WebSocket parsing/acknowledgment occurs on the page main thread, before deferred plotting starts.
Resource measurements cover the worker and its descendants, including Playwright and Chromium's
GPU process. GPU-process CPU is not GPU utilization; WindowServer and the source are outside this
process tree.

## Validation

`npm --prefix frontends/plotly test` covers packet alignment, byte bounds,
descriptors, replay containers, bounded scheduling,
asynchronous-update serialization and completion timing, skipped-frame accounting, bounded clock
observation and metrics retry/drop/final-metadata behavior. Tests also cover the complete
plot-selection transition matrix, the final-enabled-plot guard,
configuration/pending/recorded-run locks, confirmed selection after a failed request, sparse
configuration patches, active-edit preservation, edits during requests and dynamic metric hints.
`npm --prefix frontends/plotly run build` runs strict TypeScript checking and creates
the production bundle.
Core `tests/test_browser_worker.py` checks lifecycle completion, failure/timeout handling and
post-completion capture order using a Playwright substitute without opening a browser.

Functional Chrome smoke tests exercised scalar and RGB images, replace and append windows, both
transport modes, all three views, configuration updates and automatic final metrics flushing.
Headless smoke measurements are not performance rankings.

Visible Chrome presentation checks used a private source and native device pixel ratio 2. They
verified the collapsed drawer, open/apply/stop actions, both equal-width cards, each single view,
live resize from 1100 × 820 to 860 × 640, RGB/replay switching, the replay receive-age dash and
updated physical viewport metadata. The plot-selection checks also inspect actual WebSocket and HTTP packet descriptors after each
view change, verify that disabled arrays are omitted, exercise replay reloads, and check pending
requests, an injected config failure with retry, a stale drawer submission and a recorded-run lock.
A focused headless check also verifies continued playback after a failed replay download and during
a delayed retry, followed by the correct new selection and a successful final metrics flush.
Further visible checks combine the shared source form with Plotly: an external 1D selection remains
active after rate and resolution edits, unedited values refresh, active and in-flight edits survive,
and captured requests contain only changed keys. Dynamic hints follow 120 Hz and replay shows N/A.
Layout checks verify the 64-pixel workload strip and four 88-pixel metric cards at 860 × 640, without
clipped hints, page overflow or JavaScript errors.

![Plotbench React and Plotly demo](screenshots/plotly-demo.png)

[Source controls drawer](screenshots/plotly-controls.png) ·
[860 × 640 layout](screenshots/plotly-compact.png)

## API references

* [Plotly update functions](https://plotly.com/javascript/plotlyjs-function-reference/)
* [Scattergl trace, including linear x coordinates](https://plotly.com/javascript/reference/scattergl/)
* [Heatmap trace](https://plotly.com/javascript/reference/heatmap/)
* [RGB image trace](https://plotly.com/javascript/reference/image/)

The distributed Plotly bundle currently uses separate DefinitelyTyped declarations. The adapter
contains narrow assertions for documented runtime properties (`version`, linear coordinate
parameters and typed-array heatmap rows) missing from those declarations; strict application types
and the browser smoke tests cover their usage.
