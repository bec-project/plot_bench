# Validation and supported environments

Functional tests, visible smoke checks, and performance measurements establish
different things. CI is not a GPU benchmark. Mark a platform/frontend combination
verified only after its actual checks have passed; support for a dependency alone
does not establish support for the complete harness.

## Platform matrix

| Environment | Automated coverage | Visible desktop qualification |
|---|---|---|
| macOS | Core, Python adapters, browser, Rust and C++ checks | See the release validation record below |
| Ubuntu 24.04 x86-64 | CI installation/build/tests and software/offscreen checks | Native Wayland checks required; not yet qualified |
| AlmaLinux 9/10 x86-64 | CI installation/build/tests in distribution containers | Native Wayland and installed-browser checks required; not yet qualified |

Linux ARM, Windows and X11/XWayland qualification are outside the initial release.
CI workflows are supplied with the source; their first remote execution depends
on configuring the public repository. A configured workflow is not a passed run.

## Local checks

```sh
./scripts/setup core pyqtgraph matplotlib qtgraphs plotly rust iced --dev
export CARGO_HOME="$PWD/.cache/cargo"
export PATH="$PWD/.envs/node/node_modules/node/bin:$PATH"
.envs/plotting-benchmark/bin/python -m pytest core/tests
.envs/plotting-benchmark/bin/python -m black core --check
.envs/plotting-benchmark/bin/python -m ruff check core
QT_QPA_PLATFORM=offscreen .envs/plotting-benchmark-pyqtgraph/bin/python -m pytest frontends/pyqtgraph/tests
QT_QPA_PLATFORM=offscreen .envs/plotting-benchmark-matplotlib/bin/python -m pytest frontends/matplotlib/tests
QT_QPA_PLATFORM=offscreen .envs/plotting-benchmark-qtgraphs/bin/python -m pytest frontends/qtgraphs/tests
npm --prefix frontends/plotly test
npm --prefix frontends/plotly run build
cargo test --locked --manifest-path backends/rust/Cargo.toml
cargo test --locked --manifest-path frontends/iced/Cargo.toml
```

Use the local Node binary installed by setup if system Node does not satisfy the
frontend's engine requirement. Rust checks use the repository-pinned toolchain.
For C++, run `./scripts/setup qtgraphs-cpp --dev`, then
`ctest --test-dir frontends/qtgraphs-cpp/build --output-on-failure`.
Each component README includes its additional formatting/lint commands.

Core integration tests start ephemeral loopback servers and exercise both sources
when the Rust source is built. A sandbox that blocks loopback cannot run those
checks. Do not change tests or measurement logic to accommodate such restrictions.

## Desktop qualification

On each intended native desktop, with all selected components built:

1. Run doctor for every frontend and both sources. Confirm the requested display
   protocol and graphics prerequisites. On RHEL supply the installed browser path.
2. Open each demo, check waveform/scalar/RGB rendering and independent plot toggles,
   and exercise its source-controls action. Confirm clean shutdown.
3. Run short sequential stream/replay suites with both backends. Capture visual
   evidence before/after timed windows, never inside them.
4. Check completion status, raw metrics, source delivery, resource observations,
   graphics/display identity and compact/extended report links. Retain failures.
5. Record OS version/architecture, toolchain and driver versions, desktop protocol,
   tested frontends, checks and limitations. Do not convert smoke rates into rankings.

For report changes, exercise complete, interrupted, all-failed and legacy campaigns,
multiple contexts, extensions and diagnostic attempts. Verify offline navigation,
escaped user text, small and 300+ run fixtures, and matching values in both views.

## Release validation record

Validated on 2026-09-09 using macOS 15.7.5 on arm64, repository-local Python 3.13.14
environments, Node 24.19.0, Rust 1.96.1, PySide6/Qt 6.11.2, a Qt C++ 6.11.1 SDK,
and bundled Chromium 151.0.7922.34. These checks establish functionality on that
configuration; they are not performance rankings or Linux qualification.

- Core: Python/Rust source conformance, shared matrix validation, read-only
  previews, real loopback editor requests (preview, presets, save-to-custom and the
  preserved run-free invariant) and opt-in browser import/export/save interactions.
  The original core baseline was 187 passing tests.
- Python frontends: **45 tests passed** across PyQtGraph, Matplotlib and Qt Graphs
  in their isolated environments with offscreen Qt.
- TypeScript: **32 tests passed** and the production bundle built successfully.
- Native checks: **13 Rust-source tests**, **20 Iced tests** and **2 C++ CTest
  checks passed**. One optional Iced test requiring an independently running source
  was ignored; the visible suites separately exercised its live transport.
- Black, Ruff, Rust formatting, Clippy and shell syntax checks passed. Workflow
  YAML and its shell blocks parsed successfully. The locked `block` dependency
  emits a Rust future-compatibility warning on macOS; current builds pass.
- Visible macOS smoke: all seven frontend variants were exercised with both
  sources, stream/replay, replacement/append waveforms and scalar/RGB images.
  **55 of 56 initial runs were valid.** One Iced attempt with a 250 ms warmup
  correctly failed the display-stability check because plot dimensions were first
  unknown, then populated. All **8 Iced combinations passed** with a one-second
  warmup. The failed attempt and separately linked repeat were retained.
- Browser lifecycle: **4 headless combinations** passed across both sources and
  modes; **1 explicit-executable check** passed. **2 source-only probes** passed.
  Headless checks do not establish display or GPU performance.
- Offline reports: desktop/mobile navigation, selectors, stable anchors and
  JavaScript-disabled access passed on small and **312-run synthetic fixtures**.
  Regeneration preserved all **306 existing run measurements**, **102 comparison
  values** and linked diagnostics in a legacy campaign. Both report variants use
  the same statistics and retain failures and missing observations.
- Fresh clone: a single-branch clone contained only the four public commits.
  Setup created new core/PyQtGraph environments using cached locked downloads;
  doctor, demo startup/shutdown, preview and both README smoke cases passed.
  Native demo accessibility inspection timed out and is not counted as visual QA.
  Local documentation links and all public commits were checked for removed
  private material. The preserved development history is separate from this baseline.

Ubuntu/AlmaLinux CI is configured but has not been executed remotely. Native
Linux Wayland demos and suites, Linux current-RSS behavior, and an installed
RHEL-compatible browser still require validation on the target systems. Unit
tests exercise Linux selection/diagnostics and missing metadata; those tests do
not substitute for actual platform checks. No Linux frontend is marked qualified
by this local release record.

Generated validation results are local, ignored artifacts. Historical personal
benchmark campaigns are not included in the public source repository.
