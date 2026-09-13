# Plotbench

Plotbench measures how well plotting libraries keep up with streaming data. One
source generates identical waveform and image frames, and every frontend adapter —
PyQtGraph, Matplotlib, Qt Graphs (Python and C++), Iced and Plotly — receives those
same frames over the same protocol and renders them. Because none of the frontends
generate their own data, what you compare is each library's update path: its data
conversion, plot-update API and rendering, and whether it can sustain the requested
rate.

The comparison is between the adapters as implemented here, under controlled
conditions. It does not claim a library's best-case performance or full feature set.

The source is written in Rust (the default) or Python. Keep it fixed when comparing
frontends. Streaming can be limited by data generation or transport rather than
rendering, so a receiver-only probe measures the source alone, and replay mode takes
live generation and transport out of the timed window. Results from different
sources and modes are always reported separately. The headline number is submitted
updates per second, which is not the same as displayed frames per second.

## Requirements

Plotbench runs from a git clone on **macOS** or **Linux x86-64** with a native
Wayland desktop (Ubuntu 24.04 and RHEL-compatible 9+ are the qualification targets).
Windows and Linux ARM are outside the initial release.

- **Git and a POSIX shell.** Everything is driven by the helpers in `scripts/`, run
  from the repository root.
- **[uv](https://docs.astral.sh/uv/) 0.11.26 or newer** ([.uv-version](.uv-version)).
  uv installs the pinned Python 3.13 ([.python-version](.python-version)) and every
  isolated environment under `.envs/`; no system Python, pip or conda is needed.
- **[Rust/Cargo](https://rustup.rs/)** with the pinned toolchain 1.96.1
  ([rust-toolchain.toml](rust-toolchain.toml)), for the default Rust source and the
  Iced frontend. A Python-only workflow can skip it.
- **Node/npm**, only to build the Plotly frontend or to develop the Preact web UI.
  Setup installs a pinned Node 24 ([.node-version](.node-version)) under `.envs/node`;
  the shipped matrix editor and source controls need no Node at runtime.
- **A Qt 6 C++ SDK and CMake**, only for the `qtgraphs-cpp` frontend.
- **A visible desktop session** for demos and formal benchmarks. Headless and
  offscreen runs are diagnostics, not measurements.

Each platform also needs a few system packages (Qt and Wayland libraries, browser
dependencies). Install those from the [platform setup guide](docs/setup.md) before
running setup.

## Quick start

Plotbench runs from a git clone; there is no PyPI package. It builds and drives
independent Rust, Qt and npm components through repo-local tooling, so everything
happens inside the checkout. Clone the repository and run every command from its
root. With the requirements above in place:

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

You can also drive everything from an interactive terminal UI. Bootstrap the core
once with `./scripts/setup core`, then start it:

```sh
./scripts/plotbench tui
```

The TUI shows which frontends and sources are installed, installs the missing ones
(it runs `./scripts/setup` for you), starts a source, runs suites and opens the
matrix editor, with each action's output in its own tab.

The runner prints the result directory. Open its **report.html** for compact charts
or **report-extended.html** for complete evidence. Both work offline. Raw samples,
logs, the selected suite and JSON/CSV summaries remain under `results/`.
Short smoke runs verify operation; they do not establish stable performance rankings.

## Documentation

New here? Read [setup](docs/setup.md), then follow the Quick start above. This page
is the tour; the guides below go deeper.

- **Get running** — [Installation & platform setup](docs/setup.md) ·
  [Rust and Python sources](docs/backends.md)
- **Build & run benchmarks** — [Configure a benchmark matrix](docs/suites.md) ·
  [Reports & retained evidence](docs/reports.md)
- **How it works** — [Measurement & interpretation](docs/methodology.md) ·
  [Protocol v1](docs/protocol.md) · [Validation & supported environments](docs/validation.md)
- **Extend & contribute** — [Contributing](CONTRIBUTING.md) ·
  [Adding a frontend](docs/frontends.md) · [Agent guide](AGENTS.md) ·
  [Web UI: matrix editor & source controls](core/webui/README.md)
- **Reference** — [Core package](core/README.md) ·
  [Third-party licenses](THIRD-PARTY-LICENSES.md) ·
  [Presentation style](docs/presentation.md) · [Demo gallery](docs/demo-gallery.html)

## Create your own matrix

```sh
./scripts/plotbench matrix
```

The local Preact browser editor opens with a gallery of bundled scenarios (each
with its scope) and a blank option to start from. Pick a starting point, shape the
workloads — the form shows only the fields relevant to each plot — select
frontends, sources, delivery modes and timings, inspect the expanded schedule, then
**Save to scenarios_custom** (a git-ignored folder) or export the JSON. The editor
never runs benchmarks; it hands you the commands to run next. Save a suite as
`my-suite` before using this example, then stop the editor with Ctrl+C:

```sh
./scripts/plotbench run --suite scenarios_custom/my-suite.json --dry-run
./scripts/plotbench run --suite scenarios_custom/my-suite.json --output results/my-comparison
```

Use a new output directory for each attempt; directories containing an existing
campaign's `suite.json` are rejected to preserve its measurements.

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
to build the default source. npm is needed to build the Plotly frontend or develop
the Preact web UI; the C++ Qt SDK is needed for `qtgraphs-cpp`. The matrix editor
and source controls ship prebuilt and need no Node at runtime. Local Python
environments are isolated; no BEC, Redis, credentials or shared conda setup is needed.
See the [core](core/README.md) and [Rust source](backends/rust/README.md).

Rust is the default source for `serve`, `demo`, `run`, `probe` and `doctor`.
Explicit suite backend choices remain in effect unless overridden on the CLI.
A default demo requires a Rust source and refuses to attach to an existing Python source;
select `--backend python` to use that source.

Run `./scripts/plotbench serve` to start just a source, then open
[its URL](http://127.0.0.1:8765) manually for a live browser control panel that
adjusts the rate, waveform and image workload while demos stream from it.

For a Python-only source, install just the chosen frontend (for example,
`./scripts/setup pyqtgraph`) and select `--backend python` for `serve`/`demo` or
`--backends python` for `run`/`probe`/`doctor`. This needs no Rust toolchain unless
the frontend itself uses Rust. To compare both sources, select `--backends python rust`
explicitly. Use `./scripts/plotbench probe` to measure source and decoded-delivery capacity
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

See the [Documentation](#documentation) index above for contributing, adding a
frontend, and development checks. The repository retains separate frontend packages
and one shared measurement contract.

## License

Project code is [BSD-3-Clause licensed](LICENSE), Copyright (c) 2026 Jan Wyzula.
Dependencies retain their own licenses; Qt Graphs is GPLv3 or commercially licensed.
See [third-party licenses](THIRD-PARTY-LICENSES.md) and the
[licensing notes](docs/licenses.md).
