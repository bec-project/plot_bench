# Python and Rust sources

Backend selection is independent of stream/replay mode. Every frontend receives
the same binary protocol and centrally generated workload; backend identity is
recorded and kept separate in comparisons.

```sh
./scripts/setup rust
./scripts/plotbench serve --backend rust --hz 60
./scripts/plotbench demo pyqtgraph --backend rust
./scripts/plotbench run --suite scenarios/isolated-smoke.json \
  --frontends pyqtgraph --backends python rust --dry-run
```

Python is the default. An explicit demo backend refuses to attach to a different
source already running at the URL. Use another port to run a separate source:

```sh
./scripts/plotbench serve --backend python --port 8766
./scripts/plotbench demo pyqtgraph --backend python --url http://127.0.0.1:8766
```

The source control page at the chosen URL changes streaming workload settings.
Replay clients retain preloaded input until their supported reload action or a
restart. Stop manually started sources before formal benchmark runs; the runner
creates a separate source per run.

## Receiver-only probes

```sh
./scripts/plotbench probe --suite scenarios/backend-probe.json --dry-run
./scripts/plotbench probe --suite scenarios/backend-probe.json \
  --backends python rust --duration 10 --repetitions 1 --output results/source-probe
./scripts/plotbench report results/source-probe --probe
```

A common receiver decodes and acknowledges packets without plotting. Its report
shows source generation and decoded delivery capacity, missed deadlines, receive
age, decode cost and throughput. This separates source/transport limits from
renderer behavior. ACKs mean decoded delivery, not plotted or displayed frames.

Python uses NumPy and the shared Python server; Rust uses a native generator and
Tokio/Axum. Native and vectorized math can round differently within the documented
fixture tolerances. Neither backend is assumed faster. See the
[Rust implementation](../backends/rust/README.md), [protocol](protocol.md), and
[measurement guide](methodology.md).
