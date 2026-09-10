# Plotbench protocol v1

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

Fields/defaults: `hz:30`, `points:10000`, `append_count:1000`,
`width:512`, `height:512`, `waveform_mode:"replace"` (`replace|append`),
`image_mode:"scalar"` (`scalar|rgb`), `view:"both"` (`waveform|image|both`),
`seed:42`. `generation` is server-assigned and changes after a config update.
All sizes are positive; hz is >0 and <=120; append_count <= points.

## Binary packet

uint32 LE JSON header length, UTF-8 JSON header, zero padding until the total header
prefix is divisible by four, then contiguous array bytes. Array offsets are relative
to the start of the array payload (after padding).

Header: `version:1`, `seq` (zero-based), `generation`, `emitted_at_ms` (Unix epoch),
`config` (complete config), `arrays` (list of descriptors).
Descriptor: `name` (`waveform|image`), `dtype` (`float32|uint8`), `shape`, `offset`, `nbytes`.
Floats are little endian; arrays are C/row-major. Waveform shape `[points]`,
scalar image `[height,width]` with values in [0,1], RGB image `[height,width,3]`.
Waveform display ranges: x=[0,points-1], y=[-1.5,1.5]. Image levels always [0,1].
Use the same 256-entry colormap from `GET /api/colormap` (JSON list of RGB triples).
Nearest-neighbor image interpolation, opaque one-physical-pixel waveform stroke,
no point markers, no data decimation, fixed ranges are the baseline.

Append mode describes a rolling window advanced by append_count samples each
source tick. The source transmits the complete authoritative window in both modes,
so dropped frames cannot corrupt history. Adapters may use native incremental APIs
for contiguous frames, using the last append_count values, and must replace after
a skipped frame. Document the actual update strategy. This is not a transport-volume
comparison of append packets versus full frames.

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
`plotbench-qtgraphs-cpp`.
All accept `--url`, `--mode stream|replay`, `--run-id`, `--duration` (seconds;
0 means until closed), `--width` and `--height` (logical window size; defaults
1100 and 820). PyQtGraph additionally accepts `--opengl`.
Browser query fields: `url`, `mode`, `run_id`, `duration`, `width`, `height`.
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
`from plotbench.palette import COLORMAP, colorize` provides uint8 RGB LUT and
`colorize(array)` -> RGB uint8. Measure explicit conversion inside image update timing.
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
