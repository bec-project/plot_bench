# Plotbench

Compare streaming waveform and image rendering across independently packaged
plotting frontends. Rust/Tokio and Python/NumPy sources generate the shared input;
frontends decode and render the same protocol. Backend results remain separate.

## Quick start

Install [uv](https://docs.astral.sh/uv/) (minimum version in [.uv-version](.uv-version))
and [Rust/Cargo](https://rustup.rs/) and follow
the [platform setup guide](docs/setup.md) for your desktop. Run from the repository root:

```sh
./scripts/setup rust pyqtgraph
./scripts/plotbench doctor --frontends pyqtgraph
./scripts/plotbench demo pyqtgraph
```

Close the demo before recording a short functional benchmark:

```sh
./scripts/plotbench run --suite scenarios/smoke.json --frontends pyqtgraph --modes stream --dry-run
./scripts/plotbench run --suite scenarios/smoke.json --frontends pyqtgraph --modes stream
```

The runner prints the result directory. Open its **report.html** for compact charts
or **report-extended.html** for complete evidence. Both work offline. Raw samples,
logs, the selected suite and JSON/CSV summaries remain under `results/`.
Short smoke runs verify operation; they do not establish stable performance rankings.

## Create your own matrix

```sh
./scripts/plotbench matrix
```

The local browser editor opens with a gallery of the bundled scenarios (each with
its scope) and a blank option to start from. Pick a starting point, shape the
workloads — the form shows only the fields relevant to each plot — select
frontends, sources, delivery modes and timings, inspect the expanded schedule, then
**Save to scenarios_custom** (a git-ignored folder) or export the JSON. The editor
never runs benchmarks; it hands you the exact commands to run next:

```sh
./scripts/plotbench run --suite scenarios_custom/my-suite.json --dry-run
./scripts/plotbench run --suite scenarios_custom/my-suite.json --output results/my-comparison
```

`run` prints live progress: `[i/N]`, elapsed time, an ETA and a pass/fail tally.
CLI filters and timing overrides remain available. See the
[suite reference](docs/suites.md) before using a large sweep.

## Frontends and sources

| Component | Rendering implementation |
|---|---|
| [PyQtGraph](frontends/pyqtgraph/README.md) | Raster and OpenGL curve variants; ImageItem |
| [Matplotlib](frontends/matplotlib/README.md) | QtAgg with reusable artists and fixed-axes blitting |
| [Qt Graphs](frontends/qtgraphs/README.md) | PySide6 native waveform series; custom Qt Quick image provider |
| [Qt Graphs C++](frontends/qtgraphs-cpp/README.md) | Native C++ waveform submission and custom Qt Quick image provider |
| [Iced](frontends/iced/README.md) | Rust/wgpu with a custom waveform Canvas and image widget |
| [Plotly/React](frontends/plotly/README.md) | Production TypeScript bundle; scattergl, heatmap and image |

Install only selected components with `./scripts/setup COMPONENT`. Include `rust`
to build the default source. npm and the C++ Qt SDK are required only for their
respective frontends. Local Python environments are isolated; no BEC, Redis,
credentials or shared conda setup is needed.
See the [core](core/README.md) and [Rust source](backends/rust/README.md).

Rust is the default source for `serve`, `demo`, `run`, `probe` and `doctor`.
Explicit suite backend choices remain in effect unless overridden on the CLI.
A default demo requires a Rust source and refuses to attach to an existing Python source;
select `--backend python` to use that source.

For a Python-only source, install just the chosen frontend (for example,
`./scripts/setup pyqtgraph`) and select `--backend python` for `serve`/`demo` or
`--backends python` for `run`/`probe`/`doctor`. This needs no Rust toolchain unless
the frontend itself uses Rust. To compare both sources, select `--backends python rust`
explicitly. Use `plotbench probe` to measure source and decoded-delivery capacity
without plotting. See [backends](docs/backends.md).

## Understand the measurements

All frontends receive centrally generated waveform replacement/append and
scalar/RGB image workloads. Streaming uses bounded delivery and decoded-frame
acknowledgements; replay uses a bounded centrally generated dataset in CPU memory.
Formal runs launch one frontend at a time.

The common metric is **submitted updates/s**, not displayed FPS. Adapter API timing
boundaries differ and can exclude deferred GPU work. Reports keep workload, source,
delivery mode, build and runtime/display contexts separate and retain failures.
Use a controlled visible desktop and record refresh/scaling/placement with
`--display-context`. See [methodology](docs/methodology.md),
[protocol](docs/protocol.md), and [reports](docs/reports.md).

macOS and Linux x86-64 are the release targets. Linux qualification targets native
Wayland on Ubuntu 24.04 and RHEL-compatible 9+. See the
[validation record](docs/validation.md) for verified checks and remaining limits;
headless/container tests are not GPU benchmarks. Windows and Linux ARM qualification
are outside the initial release.

## Use an agent or contribute

Agents should start with [AGENTS.md](AGENTS.md). Example requests:

> Preview a matrix comparing PyQtGraph and Matplotlib with the Rust source,
> 10k and 100k waveform points at 60 Hz, streaming, three 30-second repetitions.
> Tell me the run count and estimated duration before measuring.

> Run the smoke suite for my installed PyQtGraph frontend and give me links to the
> compact and extended reports. Preserve failed attempts and identify source limits.

> Regenerate the reports in results/my-comparison and explain which runs are
> comparable without treating submitted update rates as displayed FPS.

See [contributing](CONTRIBUTING.md), [adding a frontend](docs/frontends.md),
[development checks](docs/validation.md), and the [demo gallery](docs/demo-gallery.html).
The repository retains separate frontend packages and one shared measurement contract.

## License

Project code is [BSD-3-Clause licensed](LICENSE), Copyright (c) 2026 Jan Wyzula.
Dependencies retain their own licenses; Qt Graphs is GPLv3 or commercially licensed.
See [third-party notices](docs/licenses.md).
