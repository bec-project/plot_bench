---
name: environment-doctor
description: Diagnose and fix a Plotbench environment — work out which frontends and sources a task needs, check what is installed, install or rebuild missing components with ./scripts/setup, and turn doctor or setup failures into the right fix. Use when setup or doctor fails, a component shows as not installed, or before running any benchmark.
license: BSD-3-Clause
---

# Environment doctor

Plotbench installs each component into its own isolated environment: uv-managed
Python environments under `.envs/`, and compiled artifacts under
`backends/rust/target`, `frontends/iced/target` and `frontends/qtgraphs-cpp/build`.
Nothing touches the system Python. Run everything from the repository root.

## Steps

1. **Work out what is needed.** From the suite or the request, list the frontends
   and source backends involved; only those need installing. A publishable
   baseline campaign (`./scripts/plotbench run --baseline`) always needs `rust`
   plus every frontend you intend to publish — the site accepts any subset of
   frontends, but each included frontend must complete all seven sections, so
   install and verify each one before starting. Per-component requirements are
   in the README "Requirements" section and `docs/setup.md` (platform packages
   differ between macOS, Ubuntu and RHEL).

2. **Check the current state.** For a quick overview, `./scripts/plotbench tui`
   shows an installed/missing table. The authoritative check imports the adapters
   and probes the toolchains — run it for the selected components:
   ```sh
   ./scripts/plotbench doctor --frontends pyqtgraph matplotlib --backends rust
   ```
   A cold import can take a minute; that is normal.

3. **Install what is missing.** One command per component set:
   ```sh
   ./scripts/setup rust pyqtgraph
   ```
   Components: `core`, `rust`, `pyqtgraph` (also covers `pyqtgraph-gl`),
   `matplotlib`, `qtgraphs`, `qtgraphs-cpp`, `iced`, `fyne`, `jfreechart`,
   `plotly`, or `all`. Add
   `--dev` for tests and quality tools. Setup is idempotent and preserves the other
   installed components; rerun it after pulling changes to a compiled component.

4. **Run doctor again** and confirm `OK` for every selected component before
   benchmarking.

## Map failures to fixes

| Symptom | Cause | Fix |
|---|---|---|
| `The lockfile at uv.lock needs to be updated, but --locked was provided` | a `pyproject.toml` changed without re-locking | `uv lock --project core` (or the affected `frontends/<name>`), then commit the lock |
| `Missing <component>; run ./scripts/setup <component>` | the build artifact is absent | run exactly that setup command |
| `Python ... is not in the 3.13 series` | wrong interpreter in the environment | `./scripts/setup core` — uv installs the pinned Python |
| Qt Wayland platform plugin missing, or `ldd` reports missing libraries (Linux) | platform packages absent | install the packages listed in `docs/setup.md` for your distribution, then rerun setup |
| `Plotly build missing`, Playwright or browser missing | the Plotly component is not set up | `./scripts/setup plotly`; on RHEL pass `--browser-executable` to doctor, run and demo |
| `Could not find a package configuration file provided by "Qt6"` from `setup qtgraphs-cpp` | CMake sees no Qt 6.8+ SDK; setup only finds Qt online-installer SDKs under `~/Qt` by itself | install Qt 6.8+ with Qt Graphs, or name the SDK prefix: `PLOTBENCH_QT_PREFIX=/path/to/Qt/6.11.1/macos ./scripts/setup qtgraphs-cpp` ("C++ Qt SDK" in `docs/setup.md`) |
| `Build tool unavailable` warning (rustc, cmake, node) | a toolchain is not on `PATH` | install it per the README Requirements; already-built verified artifacts still run |
| `scripts/setup not found` in the TUI | not a repository checkout | clone the repository — there is no PyPI package |

## Never

- Install into, or modify, the user's system Python, conda, or a shared venv.
- Edit `uv.lock`, `Cargo.lock` or `package-lock.json` by hand; regenerate them
  with their tools.
- Assume a component works because its dependency is installed — doctor decides.
- Claim a platform is supported beyond what `docs/validation.md` records.
