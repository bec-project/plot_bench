# Rust and Python sources

Backend selection is independent of stream/replay mode. Every frontend receives
the same binary protocol and centrally generated workload; backend identity is
recorded and kept separate in comparisons. Rust is the default for `serve`, `demo`,
`run`, `probe` and `doctor`. Install Rust/Cargo and include the source in setup:

```sh
./scripts/setup rust pyqtgraph
./scripts/plotbench doctor --frontends pyqtgraph
./scripts/plotbench demo pyqtgraph
./scripts/plotbench run --suite scenarios/isolated-smoke.json \
  --frontends pyqtgraph --backends python rust --dry-run
```

`demo` starts Rust when no source is running and requires the Rust backend when
attaching to an existing source. If a Python source is already running, select
`--backend python` explicitly; the default demo reports the mismatch. Explicit
suite `backends` choices remain honored, and CLI `--backends` overrides them.

To run Python without installing the Rust source, install the chosen frontend
and select Python explicitly. For example:

```sh
./scripts/setup pyqtgraph
```

Start the Python source in terminal A:

```sh
./scripts/plotbench serve --backend python --port 8766
```

Attach the demo from terminal B:

```sh
./scripts/plotbench demo pyqtgraph --backend python --url http://127.0.0.1:8766
```

For source-only use, install just `core`.

The source control page at the chosen URL changes streaming workload settings.
Replay clients retain preloaded input until their supported reload action or a
restart. Stop manually started sources before formal benchmark runs; the runner
creates a separate source per run.

## Receiver-only probes

The default probe measures Rust only. Select both sources explicitly to compare them:

```sh
./scripts/plotbench probe --suite scenarios/backend-probe.json --backends python rust --dry-run
./scripts/plotbench probe --suite scenarios/backend-probe.json \
  --backends python rust --duration 10 --repetitions 1 --output results/source-probe
./scripts/plotbench report results/source-probe --probe
```

Use `--backends python` for a Python-only probe or doctor check.

A common receiver decodes and acknowledges packets without plotting. Its report
shows source generation and decoded delivery capacity, missed deadlines, receive
age, decode cost and throughput. This separates source/transport limits from
renderer behavior. ACKs mean decoded delivery, not plotted or displayed frames.

Python uses NumPy and the shared Python server; Rust uses a native generator and
Tokio/Axum. Native and vectorized math can round differently within the documented
fixture tolerances. Neither backend is assumed faster. See the
[Rust implementation](../backends/rust/README.md), [protocol](protocol.md), and
[measurement guide](methodology.md).
