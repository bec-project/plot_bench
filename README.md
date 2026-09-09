# Plotbench

Compare streaming waveform and image rendering across independently packaged
plotting frontends. Python/NumPy and Rust/Tokio sources generate the shared input;
frontends decode and render the same protocol. Backend results remain separate.

## Quick start

Install [uv](https://docs.astral.sh/uv/), then run from the repository root:

```sh
./scripts/setup pyqtgraph
./scripts/plotbench demo pyqtgraph
./scripts/plotbench run --suite scenarios/smoke.json --frontends pyqtgraph --modes stream --dry-run
./scripts/plotbench run --suite scenarios/smoke.json --frontends pyqtgraph --modes stream
```

The last command writes an offline report and raw measurements under `results/`.
Use a visible desktop for benchmarks. Short smoke runs verify operation, not
stable performance rankings. Linux support is under validation.

## Components

Sources: Python/NumPy and [Rust](backends/rust/README.md).
Frontends: [PyQtGraph](frontends/pyqtgraph/README.md) (raster/OpenGL),
[Matplotlib](frontends/matplotlib/README.md), [Qt Graphs](frontends/qtgraphs/README.md),
[Qt Graphs C++](frontends/qtgraphs-cpp/README.md), [Iced](frontends/iced/README.md),
and [Plotly/React](frontends/plotly/README.md).

See the [protocol and measurement contract](docs/protocol.md) and
[presentation conventions](docs/presentation.md). The common metric is submitted
updates per second, not displayed FPS. Per-adapter timing boundaries differ.

## License

Project code is [BSD-3-Clause licensed](LICENSE). Dependencies retain their own licenses;
Qt Graphs is available under GPLv3 or a commercial Qt license.
