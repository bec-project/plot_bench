# Plotbench protocol v2

All frontends use this contract. A run selects one source implementation:
native Rust/Tokio (the default) or Python/NumPy. The selected source owns generation;
frontends do not synthesize data. Reports retain the source backend as a separate
comparison dimension. See [backend comparison](backends.md).

Base URL defaults to `http://127.0.0.1:8765`. WebSocket `/ws` emits binary frames.
After decoding/offering each frame, the receiver sends a JSON text acknowledgement
`{"ack": <seq>, "generation": <generation>}`. The server allows one frame in flight
and one latest pending frame per client; it sends the pending frame only after a
matching acknowledgement. The first frame requires no acknowledgement beforehand.
This bounds browser-internal message accumulation as well as application mailboxes.
`GET /api/config` returns the current configuration. `POST /api/config` accepts a
JSON object with changed fields and returns the validated complete configuration.
`GET /api/health` returns status. `POST /api/metrics` accepts a JSON measurement batch.
Health includes `backend` (`python` or `rust`). Configuration updates are sparse:
only submitted fields change; omitted fields, including `view`, remain current.
Control forms send only edited fields to avoid restoring stale values from another
frontend or control page.
`GET /api/frame?seq=0` returns one deterministic binary frame, without advancing the stream.
`GET /api/replay?count=16` returns a preloaded sequence: uint32 LE frame count,
then, for each frame, uint32 LE packet byte length and the packet. The server caps
replay memory at 256 MiB and reports the actual count in the container.

## Configuration

Fields/defaults, in wire order: `hz:30`, `points:10000`, `append_count:1000`,
`curves:1`, `waveform_plots:1`, `width:512`, `height:512`, `image_plots:1`,
`waveform_mode:"replace"` (`replace|append`), `image_mode:"scalar"` (`scalar|rgb`),
`view:"both"` (`waveform|image|both`), `seed:42`. `generation` is server-assigned and
changes after a config update.

Protocol v2 adds three integer fields so one window can hold several plot widgets:

| field | meaning | range |
|---|---|---|
| `curves` | curves per waveform plot | 1 … 64 |
| `waveform_plots` | number of waveform plot widgets | 1 … 16 |
| `image_plots` | number of image plot widgets | 1 … 16 |

Limits: all sizes are positive integers (booleans are rejected); hz is >0 and <=120;
`append_count <= points`; `points <= 10000000` per curve; `width` and `height`
<= 8192; `curves must be between 1 and 64`; `waveform_plots must be between 1 and 16`;
`image_plots must be between 1 and 16`. Per-frame payload bytes are
`waveform_plots * curves * points * 4` (when `view != "image"`) plus
`image_plots * width * height * (4 for scalar, 3 for rgb)` (when `view != "waveform"`)
and must stay within 256 MiB (`a frame must fit in 256 MiB`). `view` keeps its
meaning: `waveform` sends only waveform plots, `image` only image plots, `both` both
kinds; `waveform_plots` is ignored (but still valid and carried) when `view` is
`image`, likewise `image_plots` when `view` is `waveform`. Both sources validate
identically and reject unknown fields; `plotbench serve` exposes every field as a
`--flag` (`--curves`, `--waveform-plots`, `--image-plots`).

## Binary packet

uint32 LE JSON header length, UTF-8 JSON header, zero padding until the total header
prefix is divisible by four, then contiguous array bytes. Array offsets are relative
to the start of the array payload (after padding).

Header: `version:2`, `seq` (zero-based), `generation`, `emitted_at_ms` (Unix epoch),
`config` (complete config, including `curves`, `waveform_plots` and `image_plots`),
`arrays` (list of descriptors). Decoders require `version == 2` and reject every
other value, including v1 frames; the packet layout is otherwise unchanged from v1.
Descriptor: `name` (`waveform|image`), `dtype` (`float32|uint8`), `shape` (1 to 4
dimensions), `offset`, `nbytes`. Floats are little endian; arrays are C/row-major.

Shapes are always full-rank, even for one plot with one curve:

| array | dtype | shape |
|---|---|---|
| `waveform` | float32 | `[waveform_plots, curves, points]` |
| `image` (scalar) | float32 | `[image_plots, height, width]`, values in [0,1] |
| `image` (rgb) | uint8 | `[image_plots, height, width, 3]` |

Decoders validate the exact shape against the frame's `config`. In row-major order,
waveform plot `p` curve `c` is the contiguous slice
`[(p*curves + c)*points, (p*curves + c + 1)*points)`; image plot `p` is the contiguous
block of `height*width` (×3 for RGB) elements starting at `p*height*width(*3)`.
Frontends slice without copying where the language allows (NumPy views, Rust/Go/C++
slices, JavaScript `subarray`).

Waveform display ranges: x=[0,points-1], y=[-1.5,1.5] for every curve of every plot.
Image levels always [0,1]. Use the same 256-entry colormap from `GET /api/colormap`
(JSON list of RGB triples). Nearest-neighbor image interpolation, opaque
one-physical-pixel waveform stroke, no point markers, no data decimation, fixed
ranges are the baseline.

Scalar color mapping may use float32 arithmetic or renderer-native rounding. A
rounding difference of at most one adjacent LUT entry is acceptable; bit-identical
RGB output across adapters is not required. Keep the shared LUT, fixed levels,
clamping and full-resolution input. This tolerance does not permit a smaller
palette, downsampling or omitted pixels. Document the conversion arithmetic and
any SIMD build variant, and include explicit conversion in image-update timing.

Append mode describes a rolling window advanced by append_count samples each
source tick. The source transmits the complete authoritative window in both modes,
so dropped frames cannot corrupt history. Adapters may use native incremental APIs
for contiguous frames, using the last append_count values, and must replace after
a skipped frame. Document the actual update strategy. This is not a transport-volume
comparison of append packets versus full frames.

## Data generation

Both sources generate distinct data for every waveform plot, every curve and every
image plot from the same definitions (f64 unless stated), so transport and rendering
scale with the plot counts:

```text
phase          = seq * 0.13 + (seed % 10000) * 0.001
shift(p, c)    = p * 0.29 + c * 0.61          # waveform plot p, curve c (radians)
harmonic(c)    = 4.3 + 0.37 * c               # replace mode, second-term multiplier
rate(c)        = 0.071 + 0.0061 * c           # append mode, second-term multiplier
image_phase(p) = phase + p * 0.47             # image plot p
```

Waveform, replace mode (f32 arithmetic; `x = linspace(0, 12π, points)` as f32,
`total_shift = phase + shift(p, c)` computed in f64 and converted to f32 once):
`y = sin(x + total_shift) + 0.23 * sin(x * harmonic(c) - phase * 0.7)`.

Waveform, append mode (f64 arithmetic, cast to f32 at the end;
`x = i + seq * append_count` is the absolute sample position):
`y = sin(x * 0.017 + seed * 0.001 + shift(p, c)) + 0.23 * sin(x * rate(c))`,
evaluated as `((x * 0.017) + (seed * 0.001)) + shift` and `x * rate`. Consecutive
windows overlap exactly for every plot and curve because they depend only on `x`,
`p` and `c`.

Images (f32 arithmetic, `ph = image_phase(p)`, `x = linspace(0, 4π, width)`,
`y = linspace(0, 4π, height)`):
`scalar[r, c] = clip((sin(x[c] + ph) + cos(y[r] - ph * 0.7) + 2) * 0.25, 0, 1)`;
RGB `R = scalar * 255`, `G = (sin(x * 0.7 - ph) + 1) * 127.5`,
`B = (cos(y * 0.9 + ph) + 1) * 127.5`, truncated to uint8.

For `p = 0` and `c = 0` these reduce exactly to the protocol v1 formulas (shift 0,
harmonic 4.3, rate 0.071, image phase `phase`), so the first plot and curve are
bit-identical to the single-plot generator on each source. The payload is laid out
plot-major: for each waveform plot, for each curve, `points` values; for each image
plot, one `height × width (× 3)` block. The Rust source mirrors the f32/f64
discipline and expression order; `backends/rust/tests/fixtures/generation.json`
holds Python-generated reference values (3e-6 float / 1 RGB level tolerance).

## Plot layout and curve colours

Every frontend creates `waveform_plots` waveform widgets (each drawing `curves`
curves) and `image_plots` image widgets according to the current config, rebuilding
the widget set when the generation changes. One update submission per frame covers
all plots; `update_ms` times the whole frame and `conversion_ms` all image
conversions in it.

Layout rule (shared, language neutral): visible plots are ordered waveform plots
first (`Waveform 1..N`), then image plots (`Image 1..M`), `n = N + M` counting only
the kinds enabled by `view`. Arrange them in a grid with `columns = ceil(sqrt(n))`,
`rows = ceil(n / columns)`, filled row-major with equal cell sizes; trailing empty
cells stay empty (n=1 → 1×1, n=2 → 2×1 side by side, n=3 and 4 → 2×2, n=5 and 6 →
3×2, n=9 → 3×3).

Titles: `Waveform` / `Image` when there is exactly one of that kind, else
`Waveform 1`, `Waveform 2`, … / `Image 1`, `Image 2`, …. Subtitles keep
`points · mode` / `width × height · mode`, plus `· K curves` on waveform plots when
`curves > 1`. The workload summary strip shows `10,000 · replace · 2 plots × 3 curves`
when plots or curves exceed 1 (no suffix when both are 1) and `· 3 plots` on the
image item when `image_plots > 1`. Counts are pluralised grammatically
(`1 plot × 3 curves`, `4 plots × 1 curve`); reports use the same wording.

Curve `c` of every waveform plot uses `CURVE_COLORS[c % 8]`:

```text
CURVE_COLORS = ["#64dccc", "#f5c76e", "#7aa6ff", "#ff9d7a", "#c39bff", "#9be564", "#ff7ab8", "#6ee7ff"]
```

Curve 0 keeps the accent colour. Stroke width, antialiasing, fixed axes, no markers
and no decimation are unchanged; all curves of a plot share the same fixed ranges.
Python frontends import the tuple from `plotbench.palette`.

## Replay

Preload central frames once via `/api/replay`, cycle changing CPU-side input at the
configured rate, keep a separate increasing presentation sequence for drop counting,
and perform conversions/uploads for each adopted update. Do not preload GPU resources
for every frame. Time synchronous preparation, record asynchronous completion separately
where observable, and document deferred/unobserved work. Report payload count and memory. This bounded cyclic replay is a
cache-warm diagnostic, not an unlimited unique-data stream.
The preloaded configuration remains fixed until a supported interactive control
reloads the central dataset or the frontend restarts. External source changes do
not update an existing replay automatically. Ordinary replay scheduling makes no
frame/configuration HTTP requests after preload; telemetry still posts to the
source. Interactive reloads run outside that scheduling path, and workload controls
are disabled during recorded runs.

## Measurements

Send batches approximately once/second (not per frame) to `/api/metrics`:
`{frontend, mode, run_id, samples:[...], metadata:{...}}`.
mode=`stream|replay`; run_id comes from CLI/query (default `demo`).
Each sample: `seq`, `generation`, `client_time_ms`, `update_ms`,
`receive_age_ms` (null in replay), `skipped` (since last submitted frame),
`conversion_ms`, `draw_ms`, `update_complete_ms`, `image_upload_wait_ms` (optional).
update_ms times synchronous frontend conversion/update submission using a local
monotonic clock. It MUST NOT be labeled GPU time or displayed FPS. Add
`metadata.measurement_stage` describing exactly what is timed, and
`metadata.renderer`, versions, pixel ratio, viewport size and update strategy.
Plot geometry metadata: `plot_viewports: {"waveform": [w,h] | null, "image": [w,h] | null}`
is the physical data area of the FIRST plot of each kind (all grid cells are equal);
`plot_counts: {"waveform": N, "image": M}` records the visible widget counts (0 when
the kind is hidden by `view`) and `curves: K` the curves per waveform plot. Where a
frontend also records `plot_viewports_logical` or `plot_containers`, the same
first-plot rule applies.
`update_complete_ms` is adapter-specific elapsed time through completion: Plotly waits
for all active trace-update promises; Iced waits for image allocation and adopts a
ready frame. It includes asynchronous waiting, not just CPU work, and does not prove
screen presentation. Iced's `image_upload_wait_ms` includes allocation/event scheduling.
Optional durations must be finite and nonnegative or null. Report percentiles and
observation coverage over the same measured interval; absent draw observations are
unavailable, not zero. Stages can overlap (Plotly `draw_ms` is inside `update_ms`), so
never add these columns or their percentiles to infer total frame time/headroom.
Receive age is an approximate same-host wall-clock estimate; it is not precise
presentation latency. Record negative estimates; do not silently clamp them.
Final metadata records `termination_reason` (`duration|user|error`), `active_seconds`,
and telemetry loss. Always send the final metadata batch, even with no samples.
The report deduplicates retries by frontend/run/generation/sequence, exposes duplicate
counts, and excludes interrupted, changed-configuration or incomplete-telemetry runs.
Observed display/plot-geometry changes during measurement and native receiver reconnects
also invalidate comparisons. Display metadata is sampled with telemetry, not on every
frame; undetected changes remain possible. Record operator display context in the suite
or `run --display-context` when physical monitor/refresh cannot be queried by the adapter.

Live UI: submitted updates/s, source target Hz, update duration, skipped frames,
approximate receive age, connection/error state, selected workload. Refresh the HUD
at ~2Hz. Receiver/replay scheduling uses a latest-frame mailbox so UI work is bounded.
Report skipped updates; do not queue an unbounded backlog. A GUI can use a timer
to poll its mailbox, but timer callbacks alone do not count as rendered frames.

## Executables and frontend arguments

Python console scripts: `plotbench-pyqtgraph`, `plotbench-matplotlib`,
`plotbench-qtgraphs`. Rust binary: `plotbench-iced`. C++ binary:
`plotbench-qtgraphs-cpp`. Go binary: `plotbench-fyne`. Java: `java -jar frontends/jfreechart/build/plotbench-jfreechart.jar`.
All accept `--url`, `--mode stream|replay`, `--run-id`, `--duration` (seconds;
0 means until closed), `--width` and `--height` (logical window size; defaults
1100 and 820). PyQtGraph additionally accepts `--opengl`.
Browser query fields: `url`, `mode`, `run_id`, `duration`, `width`, `height`.
The browser frontends are `plotly` and `fyne-wasm`; the latter compiles the Go/Fyne
renderer to WebAssembly and reports its own frontend and browser runtime identity.
Run native graphical apps sequentially during measurements.

## Shared Python client API (core package)

`from plotbench.client import FrameSource, MetricsSink, frontend_parser`
`args = frontend_parser(description).parse_args()` (caller can add arguments).
`source = FrameSource(args.url, args.mode)`; `source.start()`;
`frame = source.take_latest()` returns None or Frame with `.header`, `.arrays`
(NumPy dict), `.seq`, `.generation`, `.receive_age_ms`, `.skipped`.
`source.status` is human-readable; `.error` is None or an error string; `.close()`.
`source.request_view("waveform")` dispatches a view-only configuration request on
a worker thread; `"both"` and `"image"` are also accepted. It returns False if another request is
pending or the source is closed. `.view_pending` stays True until the accepted
generation reaches the client; `.view_error` reports configuration failures.
Replay selection changes reload the central CPU dataset, without adding network
polling to ordinary replay scheduling. GUI controls reflect actual frame config,
retain at least one selected plot, and are locked during timed benchmark runs.
`sink = MetricsSink(args.url, frontend_name, args.mode, args.run_id, metadata={...})`;
`sink.record(frame, update_ms, **extra)` returns None and batches in background;
`.snapshot()` returns dict `updates_hz, update_ms, skipped, receive_age_ms, count`;
`.close()` flushes. Source handles socket/replay reception outside GUI thread.
`from plotbench.palette import COLORMAP, CURVE_COLORS, colorize` provides the uint8 RGB
LUT, the eight curve colours and `colorize(array)` -> RGB uint8. `frame.arrays["waveform"]`
is `[waveform_plots, curves, points]` and `frame.arrays["image"]` is
`[image_plots, height, width(, 3)]`; index the first axis to get a zero-copy view per plot. Measure explicit conversion inside image update timing.
Libraries can defer their own color expansion/paint: PyQtGraph's indexed QImage/LUT
lookup is deferred, while Matplotlib's synchronous Agg path includes rasterization.
Keep that distinction explicit in `measurement_stage` and the per-adapter timing tables.

### Source timing and delivery counters

Both encoders stamp `emitted_at_ms` after packing payload bytes, before serializing
and inserting the JSON header. It is not the socket-send time. Python returns an
owned read-only buffer view so header insertion does not require another payload copy.
The aligned wire representation is unchanged.

`source.jsonl` records generated frames plus cumulative `deadline_misses_total`,
`acknowledgements_total` and active `clients`. Counters span source generations.
Deadline misses calculated after one sample are visible in the next; the report's
counter increase excludes unobserved window boundaries. Delivery ACK Hz uses the
ACK counter difference divided by the actual first-to-last source-sample span of the
leading single-client samples inside the measured window; trailing samples recorded
after that client disconnected are excluded, and any other client count before or
inside the span makes the rate unavailable rather than zero. ACK means
decoded input accepted by the receiver, not plotted or displayed content. Receiver
probes retain their direct per-received-frame measurement as the primary delivery metric.

Both servers enable TCP_NODELAY and use a 20-second receive-idle heartbeat followed
by a 10-second response timeout; incoming traffic resets liveness. Generation duration
includes packing/mailbox publication. Python includes thread dispatch/return;
neither duration includes the subsequent JSONL write. Backend identity remains explicit.

Core dependencies contain no Qt or plotting packages. Each Python frontend installs
the sibling core package in its own independently resolved environment.
