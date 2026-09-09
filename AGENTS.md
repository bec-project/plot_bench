# Working on Plotbench

Plotbench is a standalone benchmark, with no BEC, Redis, conda, credentials, or
external services required. Run commands from this repository root. Use its local
environments; never modify a user's shared Python environment.

## Setup and checks

```sh
./scripts/setup rust pyqtgraph --dev
./scripts/plotbench doctor --frontends pyqtgraph
.envs/plotting-benchmark/bin/python -m pytest core/tests
QT_QPA_PLATFORM=offscreen .envs/plotting-benchmark-pyqtgraph/bin/python -m pytest frontends/pyqtgraph/tests
```

Install the selected components, not every frontend by default. See
[setup](docs/setup.md), [validation](docs/validation.md), and each component's
README for platform requirements and additional tests. Preserve dependency locks.
Use `qtpy` for shared Qt APIs; direct PySide6 access is appropriate for Qt Graphs
APIs that qtpy does not expose.

Rust is the default source; install Rust/Cargo and explicitly include `rust` in
setup for that workflow. Preserve any backend selected by the user or suite.
For a Python-only source, setup can install just `core` or the selected frontend;
use `--backend python` for `serve`/`demo` and `--backends python` for
`run`/`probe`/`doctor`. A default demo requires Rust even if a Python source is
already running; it must not silently attach to that source. Comparing both
backends requires an explicit `--backends python rust` selection.

## Running a requested benchmark

1. Translate the user's question into an explicit suite JSON. Reuse the examples
   and [suite reference](docs/suites.md); keep hardware-specific settings out of
   shared examples. Use a new result directory for each attempt.
2. Run doctor for the selected components, then `run --suite FILE --dry-run`.
   Report the number of runs and nominal time, including the additional startup,
   preload and cooldown costs. Ask for missing workload or time-budget information
   only when it materially changes the requested experiment. Existing user
   authorization to run the chosen campaign remains valid.
3. Verify operation with a short visible smoke run. Screenshots are visual QA and
   must occur outside measured windows. Close unrelated benchmark/demo windows.
4. Run sequentially on a controlled visible desktop. Record display identity,
   refresh, scaling and placement with `--display-context`. Do not silently switch
   to headless, software rendering or a different display protocol after a failure.
5. Preserve all raw data, failed attempts and diagnostics. Report errors and
   source limitations; never selectively discard inconvenient measurements.
6. Deliver links to the compact and extended reports, the suite and the raw result
   directory. Explain which combinations were tested and any limits to comparison.

Use `run --dry-run --json` for machine-readable plans. The matrix editor creates
the same JSON — it saves to the git-ignored `scenarios_custom/` or exports a
download — but it does not execute campaigns and exposes no run endpoint. Stop the
editor before formal runs. Never run a large example sweep merely to validate a
documentation change.

## Measurement invariants

- Data generation belongs to the Python or Rust source. Frontends decode and
  render its authoritative frames, including append windows. Conversion required
  by a renderer is allowed and must retain its documented timing boundary.
- Preserve the binary protocol, seeded inputs, bounded delivery, acknowledgement
  semantics, replay limits, completion validation, and build provenance.
- Submitted updates per second are not displayed FPS. CPU/API return times are
  not GPU completion or presentation times. Adapter timing stages may overlap.
- Never pool source backends, workloads, modes, builds, display/runtime contexts,
  or diagnostic campaigns. Missing observations remain missing, not zero.
- Do not edit source, dependencies, builds or rendering settings during a run.
  Rebuild selected compiled components before benchmarking changed source.
- Headless, offscreen and virtual-display checks establish function only. Claim
  platform support only to the extent recorded in the validation guide.

## Making changes

Keep components independently packaged and document actual rendering work. Follow
[CONTRIBUTING.md](CONTRIBUTING.md) and the
[frontend integration guide](docs/frontends.md). Run focused checks for each changed
component and protocol/conformance checks when shared behavior changes. Do not
regenerate numerical fixtures to make a failing implementation pass.

Do not commit generated results, local paths, machine identifiers, personal
campaign instructions or tool-generated conversation logs. Commit and branch
operations follow the user's requested scope. Never publish private backup
branches or use `git push --all` / `git push --mirror` for a public release.
