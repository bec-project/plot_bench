# Rust source backend

Independent native source for the plotting benchmark: Axum **0.8.9**, Tokio
**1.53.1**, and Rust 2024. `Cargo.lock` pins every dependency. Python, NumPy,
Qt, Node, and plotting packages are not runtime dependencies.

Build from this directory:

```sh
CARGO_HOME="$PWD/.cargo-cache" cargo build --locked --release
```

The root launcher supplies the shared configuration and controls page:

```sh
./target/release/plotbench-source-rust \
  --host 127.0.0.1 --port 8765 \
  --config /path/to/source-config.json \
  --output /path/to/results \
  --controls ../../core/src/plotbench/controls.html
```

`--config` is a JSON **file path**. Omitted fields use the same defaults as the
Python source. `--controls` is a UTF-8 HTML file served at `/`. The native
256-entry colormap exactly matches the shared blue/cyan/yellow table; no palette
file is needed. Cache and build output stay under this package when using the
command above. SIGINT and SIGTERM stop generation, close active streaming
connections, cancel queued/stalled replay delivery, and finish source-file writes.
HTTP connections get up to three seconds to drain before stalled connections
are forcibly closed. Work already executing in a bounded generation job finishes
before the Tokio runtime exits.

## Protocol and generation

The backend implements `/api/config`, `/api/health`, `/api/frame`, `/api/replay`,
`/api/colormap`, `/api/metrics`, `/ws`, and CORS for browser clients. Configuration
POSTs are patches: unspecified settings are preserved, read-only/unknown fields
are rejected, and every successful update increments `generation`. Validation
matches the Python limits: up to 120 Hz, 10 million waveform points, 8192 pixels
per image axis, and 256 MiB of selected payload per frame. Seeds, generation
numbers, frame sequences, and integer sample counters use `u64`; Python permits
larger arbitrary-precision integers. Keep these fields within `0..2^64-1` when
comparing backends.

Each stream frame is newly generated from its actual sequence number. The stream
does **not** cycle through cached frames. A dedicated generation thread evaluates
the same deterministic formulas as Python. Append frames contain complete rolling
windows derived from absolute sample positions. Replace frames contain the
complete current waveform. Images evaluate horizontal/vertical trigonometric
terms once per axis, then write row-major scalar or RGB pixels in a fused loop.
The waveform also writes directly into the output payload. A reserved prefix
lets the encoder write the timestamped, aligned JSON header after generation
without copying the complete payload again.

Generation and source logging run outside Tokio's event loop. Scheduling uses an
absolute monotonic deadline. If generation or delivery cannot meet the requested
rate, expired deadlines advance the sequence and increment `deadline_misses`;
the source never disguises missed updates with repeated or stale frames. There
is no additional rate cap. No frames are generated when no stream clients exist.

Each WebSocket client has one latest pending packet and at most one outstanding
packet. The next packet is sent only after receiving matching text JSON
`{"ack": sequence, "generation": generation}`. Incorrect credit is ignored;
malformed JSON closes the socket. Replacing a client's pending packet increments
`mailbox_drops`. Shared immutable packet bytes avoid one payload copy per client.

Replay is generated on demand with the same framing and 256 MiB/count limits as
Python. It contains changing sequences starting at zero. Only one replay request
generates at a time; a one-chunk channel applies HTTP backpressure. Frame/replay
generation and metrics writes use at most two concurrent blocking jobs. These
limits bound CPU work, not streaming frequency. Workload changes do not alter a
replay response already being generated from its configuration snapshot.

## Numerical equivalence

Wire dtypes, shapes, array ordering, ranges, append overlap, and colormap entries
match the shared source. Native scalar math and NumPy's vector math can round
slightly differently; **bit identity is not claimed**. Replace waveforms and
images use float32 intermediate arithmetic, while append waveforms evaluate
absolute positions in float64 before converting to float32, matching Python's
precision choices. No fast-math or trigonometric approximation is enabled.

The checked-in fixtures exercise append/replace, scalar/RGB, single-pixel
dimensions, different seeds, and late sequences. Tests allow **3 × 10⁻⁶** absolute
float32 difference and at most **1** RGB level to accommodate platform math and
quantization boundaries. These fixture tolerances do not prove equivalence for
every possible sequence or seed. Consecutive native append windows overlap exactly.

## Raw results

- `source.jsonl`: `time_ms`, `seq`, `generation`, `generation_ms`, `packet_bytes`,
  per-frame `mailbox_drops`, and `target_hz`, compatible with the Python report.
- `measurements.jsonl`: complete validated frontend batches with
  `received_at_ms`. Invalid batches are rejected before writing any sample.
- `host.json`: actual platform, architecture, available CPU/memory information,
  Rust compiler version, backend/runtime/framework versions, initial config,
  and generation/numeric policies. Unavailable metadata is null; no Python
  version or GPU measurements are invented.

Health reports include `backend: "rust"`, `version`, `runtime`, `runtime_version`,
HTTP framework/version, active clients, generation counts, misses, drops, errors,
configuration, and the absolute output directory. Compare source capacity using
the root transport probe before attributing limited delivery to a plotting
library. Native Rust is not assumed to be faster for every workload.

## Validation

```sh
CARGO_HOME="$PWD/.cargo-cache" cargo fmt --all --check
CARGO_HOME="$PWD/.cargo-cache" cargo test --locked --release -- --nocapture
CARGO_HOME="$PWD/.cargo-cache" cargo clippy --locked --all-targets -- -D warnings
```

Tests cover patch atomicity and validation, frame/replay layouts, exact append
overlap, changing replay data, fixture tolerances, colormap identity, metrics
validation-before-write, and actual loopback WebSocket ACK withholding/mismatch/
release/client cleanup. Regenerate numerical fixtures only after deliberately
reviewing source-formula changes:

```sh
../../.envs/plotting-benchmark/bin/python tests/create_fixtures.py
```

Implementation references: [Axum WebSockets](https://docs.rs/axum/0.8.9/axum/extract/ws/index.html)
and [Tokio blocking-work guidance](https://docs.rs/tokio/1.53.1/tokio/task/fn.spawn_blocking.html).
