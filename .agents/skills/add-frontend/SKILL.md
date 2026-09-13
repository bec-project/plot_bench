---
name: add-frontend
description: Add a new plotting frontend adapter to Plotbench — implement it against the shared protocol and timing contract, register it in the suite catalog, runner, setup, doctor, TUI and web UI, and add tests, a README, a scenario and licenses. Use when asked to add, port or integrate a new plotting library or renderer as a frontend.
license: BSD-3-Clause
---

# Add a plotting frontend

Every frontend is an independent package that receives frames from the shared
source and renders them; it must never generate its own data. The contract and
acceptance criteria are in `docs/frontends.md` and `docs/protocol.md` — read both
first. This skill lists every place a frontend is wired in, so nothing is missed.

## 1. Implement the adapter

- Create `frontends/<name>/` as its own package: a `pyproject.toml` with
  `plotbench-core` as a path dependency and its own `uv.lock` for Python, or a
  `Cargo.toml` or CMake project for a compiled frontend. Copy the layout of the
  closest existing adapter — `frontends/pyqtgraph` (Python/Qt),
  `frontends/iced` (Rust), `frontends/qtgraphs-cpp` (C++), `frontends/plotly`
  (browser bundle).
- Decode the protocol frames — waveform replace and append windows, scalar and
  RGB images — and submit them through the library's update API. Conversion a
  renderer needs is allowed, but it must keep the documented timing boundary.
- Accept the launch arguments the runner passes (`--url`, `--mode`, `--run-id`,
  `--duration`) and report telemetry the way existing adapters do ("Define
  telemetry" in `docs/frontends.md`). Honor bounded delivery and
  acknowledgements, replay, and clean completion.
- Use `qtpy` for shared Qt APIs; use PySide6 directly only for Qt Graphs APIs that
  qtpy does not expose.

## 2. Register it — every touch point

| Where | What |
|---|---|
| `core/src/plotbench/suites.py` — `FRONTENDS` | add the ID; this catalog is what the CLI, editor and TUI read |
| `core/src/plotbench/runner.py` — `frontend_command` | how the runner launches it (executable path or Python module) |
| `core/src/plotbench/runtime.py` — `PYTHON_FRONTENDS`, `QT_FRONTENDS`, `_executable` | install detection and doctor's runtime probe |
| `scripts/setup` — the component `case`, plus the `for PLOTBENCH_PACKAGE` loop for Python adapters | how it is installed or built |
| `core/src/plotbench/tui.py` — `INSTALLABLE` | offer it in the TUI installer |
| `core/webui/src/config-fields.ts` — `OPTION_TIPS` | its tooltip in the matrix editor; then rebuild the web UI |
| `core/src/plotbench/provenance.py` | compiled or bundled adapters only: artifact paths and build fingerprints, so a stale build is invalidated |
| `core/src/plotbench/report.py` and `report_layout.py` | any adapter-specific timing or metadata fields, keeping contexts separate |
| `README.md` frontends table and `frontends/<name>/README.md` | what it renders and its known limitations |
| `THIRD-PARTY-LICENSES.md` | the new dependencies and their licenses |
| `scenarios/` and CI | a small scenario that exercises it, and test coverage |

## 3. Test and accept

- Unit tests under `frontends/<name>/tests`: malformed frames, array layout,
  append and replay behavior, bounded delivery, conversion correctness, clean
  completion.
- Then, visibly, with both sources and both delivery modes (substitute your
  frontend's ID for `pyqtgraph`):
  ```sh
  ./scripts/setup rust pyqtgraph --dev
  ./scripts/plotbench doctor --frontends pyqtgraph
  ./scripts/plotbench demo pyqtgraph
  ./scripts/plotbench run --suite scenarios/smoke.json --frontends pyqtgraph --modes stream replay --dry-run
  ```
  Confirm complete, usable telemetry. Take screenshots only outside measured
  windows.
- Run the `validate-change` skill for everything you touched, including the docs
  test — it checks the new ID against the CLI.
- State exactly which OS and display combinations you tested; offscreen runs do
  not validate rendering performance.

## Never

- Generate data in the frontend, or bypass the common source.
- Invent comparable GPU or presentation timings from unlike API boundaries.
- Put an expensive or optional-SDK frontend into the single-component quick start.
- Skip re-locking (`uv lock`) or regenerating provenance after a build change.
