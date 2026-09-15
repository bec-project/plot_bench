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

Run commands from the repository root. Install and test only the components you
changed; the block below is the full component check list, not a prerequisite for
editing documentation or the web UI. For core/docs work, start with
`./scripts/setup core --dev`, then run the core tests and Python quality checks.

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
npm --prefix website test
npm --prefix website run build
cargo test --locked --manifest-path backends/rust/Cargo.toml
cargo test --locked --manifest-path frontends/iced/Cargo.toml
```

Use the local Node binary installed by setup if system Node does not satisfy the
frontend's engine requirement. Rust checks use the repository-pinned toolchain.
For C++, run `./scripts/setup qtgraphs-cpp --dev`, then
`ctest --test-dir frontends/qtgraphs-cpp/build --output-on-failure`.
The Rust component READMEs include formatting/Clippy commands. After manually
rebuilding a compiled or bundled component, record its provenance before using it
through the harness, or run its setup command to rebuild and record it together.

Core integration tests start ephemeral loopback servers and exercise both sources
when the Rust source is built. A sandbox that blocks loopback cannot run those
checks. Do not change tests or measurement logic to accommodate such restrictions.

### Matrix editor and source controls

Both pages are Preact apps with committed production assets. After installing
Node/npm compatible with `core/webui/package.json`:

```sh
./scripts/setup core --dev
npm ci --prefix core/webui --cache "$PWD/.cache/npm" --no-audit --no-fund
npm --prefix core/webui test
npm --prefix core/webui run typecheck
npm --prefix core/webui run build
```

Install Chromium into the repository cache and select its executable for the
opt-in browser tests:

```sh
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/playwright"
.envs/plotting-benchmark/bin/python -m playwright install chromium
PLOTBENCH_TEST_BROWSER="$(.envs/plotting-benchmark/bin/python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as playwright:
    print(playwright.chromium.executable_path)
PY
)"
export PLOTBENCH_TEST_BROWSER
.envs/plotting-benchmark/bin/python -m pytest core/tests/test_matrix_browser.py core/tests/test_source_controls.py
```

On Ubuntu, install the [browser system dependencies](setup.md#ubuntu-2404-x86-64-wayland)
as well. On RHEL-compatible systems, select an installed Chromium executable as
described in [setup](setup.md#rhel-compatible-linux-9-x86-64-wayland).
Without `PLOTBENCH_TEST_BROWSER`, the interaction tests skip. They are headless
functional checks and do not qualify rendering performance. CI also rebuilds the
UI and checks that it matches the committed assets. The HTML entry points, packaged
pages and offline reports have different roles; see the
[web UI guide](../core/webui/README.md).

### Results website

The community results site under `website/` is a React + Vite app with the same
Node requirement as the other web UIs; CI builds its bundle, which is never
committed. Install its locked tools into the repository cache, then run the unit
tests, formatting, catalogue validation, type checking and production build:

```sh
npm ci --prefix website --cache "$PWD/.cache/npm" --no-audit --no-fund
npm --prefix website test
npm --prefix website run format:check
npm --prefix website run validate
npm --prefix website run build
```

With `PLOTBENCH_TEST_BROWSER` selected as above, the opt-in browser check drives
the built site through its filters, grouping, winners, run details, contribution
preview and mobile layout:

```sh
.envs/plotting-benchmark/bin/python -m pytest website/tests/browser_smoke.py
```

It skips without a selected browser. Like the matrix editor checks, it is a
headless functional test and measures no rendering performance. Its stylesheet
shares the design tokens and control primitives of `core/webui/src/style.css`;
see the [website guide](../website/README.md).

### Documentation examples

```sh
.envs/plotting-benchmark/bin/python -m pytest core/tests/test_documentation.py
./scripts/plotbench --help
./scripts/plotbench run --help
./scripts/plotbench serve --help
```

The documentation tests parse complete `./scripts/plotbench` examples against the
current CLI, verify npm script names, check shell-block syntax and expand suite
examples. They
never install packages or execute campaigns. Local links and bundled scenario
previews should also be checked after documentation changes. Replace explicitly
marked clone URLs, browser/SDK paths and result-directory examples with values
for your checkout. Successful parsing does not establish that every system package,
graphics driver or toolchain is installed; use doctor and target-platform checks
for that evidence.

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

## Multi-plot workloads

Protocol v2 adds multi-plot, multi-curve workloads (`curves`, `waveform_plots`,
`image_plots`). Their automated coverage is the core contract tests, the shipped
scenario checks in `core/tests/test_suites.py`, each frontend's layout and slicing
tests and the documentation test. A passing offscreen test is not visible
evidence; the visible check below is recorded separately from the release record.

Validated on 2026-09-14 using macOS 15.7.5 on arm64 with the same repository-local
toolchains as the release record (Python 3.13.15 environments, Rust 1.96.1, Go 1.25.4,
PySide6/Qt 6.11.2, a Qt C++ 6.11.1 SDK, bundled Chromium 151). These checks
establish that every adapter lays out and renders several plots and curves; they
are functional smoke results, not rankings.

- Automated: **634 core tests** (protocol v2 codec and shapes, plot-0/curve-0
  bit-identity with the v1 formulas, Python/Rust source conformance for 8 workloads
  including 2 × 3-curve + 2-image, 4 × 5-curve and 3-image cases, suite expansion
  over the new axes, report labels, documentation examples), **41 PyQtGraph**,
  **52 Matplotlib** and **30 Qt Graphs** offscreen tests, **17 + 1 Rust source tests**
  (fixture error 1.2 × 10⁻⁷ against 22 Python-generated cases), **26 Iced tests**,
  the Go race/vet suite, **2 C++ CTest checks**, **41 Plotly tests**, the web UI
  typecheck, tests and bundle rebuild. Ruff, Black, rustfmt, Clippy and gofmt passed.
- Visible macOS smoke: `scenarios/multi-plot-smoke.json` with all eight frontend
  variants and both delivery modes on the Rust source (48 runs, one-second warmup,
  three measured seconds). **46 runs were valid.** Two replay runs (Qt Graphs
  4 × 4-curve waveforms, PyQtGraph 4 RGB images) were invalidated by the
  display-stability check because their windows were moved between the built-in and
  an external display during the measured seconds; a four-run repeat reproduced the
  same operator interaction and both attempts are retained as diagnostics. Their
  stream counterparts and the other replay combinations completed. Every adapter
  reported `plot_counts` and `curves` in its telemetry.
- Untimed visual QA (adapter-side captures outside measured windows) confirmed the
  2 × 3-curve + 3-image layout, per-plot titles, the shared curve colours and the
  summary-strip wording for PyQtGraph (raster), Matplotlib, Qt Graphs, Iced, Fyne
  and Plotly; the captures are kept as `frontends/*/screenshots/*-multi-plot.png`.
  The OpenGL PyQtGraph variant cannot be captured by a widget grab and was checked
  through its telemetry only; the Qt Graphs C++ adapter has no capture facility.
- Rates observed in this short smoke (not rankings): the 4 × 4-curve 60 Hz case was
  sustained by PyQtGraph (raster), Fyne and Iced, and limited to roughly 12 Hz by
  both Qt Graphs adapters and to roughly 40 Hz by Matplotlib; four 256² RGB images
  at 30 Hz were sustained by every adapter except Iced and Plotly. These are the
  documented per-plot update costs of each library, visible in the reports.

## Fyne integration validation

The Go/Fyne frontend was checked on macOS arm64 with the native Fyne GLFW/OpenGL
driver, Go 1.27 and Fyne 2.8.1. Visible acceptance used a Retina desktop with a
2× physical pixel ratio. All **16 combinations** in `scenarios/fyne-smoke.json`
completed with valid reports: Python/Rust sources × stream/replay × combined
replacement/scalar, combined append/RGB, waveform-only and image-only cases.
Each run used a one-second warmup and three measured seconds. No telemetry loss
was reported. These short checks establish function, not a sustained ranking.

Untimed canvas screenshots verified combined rendering and an external live
view change to image-only. The adapter README retains a combined screenshot.
The physical-pixel regression test covers macOS's separate texture scale:
`Canvas.Scale()` alone is insufficient; `PixelCoordinateForPosition` includes it.
An initial local acceptance attempt using logical canvas scale is retained as a
diagnostic and excluded from the above acceptance claim.

The 12 Go tests pass with the race detector using Fyne's `ci` test driver.
Core integration/provenance/setup tests, Python formatting, web UI type checking,
proxy tests and bundle rebuild were also checked. Go vet and module checksum
verification pass. To repeat the Go checks from the repository root:

```sh
export GOPATH="$PWD/.cache/go"
export GOCACHE="$PWD/.cache/go-build"
go -C frontends/fyne test -race -tags ci ./...
go -C frontends/fyne vet -tags ci ./...
go -C frontends/fyne mod verify
```

A dedicated workflow adds macOS and Ubuntu native build/test coverage; it is not
a claim that remote CI has run. Linux/Wayland visible rendering remains
**unqualified**, and Fyne on AlmaLinux has not been built or tested locally.
Windows and X11 are outside this integration's supported host contract.

## JFreeChart integration validation

### Protocol v2 launch regression

The Java branch initially retained a protocol-v1 decoder and self-generated v1
test packets. Against the current v2 sources, a TUI demo exited with
`java.lang.IllegalArgumentException: invalid version` even though setup and doctor
passed. The historical checks below did not catch this incompatibility.

The corrected adapter validates v2 shapes and renders all configured plots and
curves. Ten JUnit tests now include 24 workloads encoded by the shared Python
source, checking every waveform value and converted image pixel, plot counts,
curve colours, configuration changes and rejection of mismatched dimensions.
Core checks passed 681 tests with five optional checks skipped.

On macOS arm64 / OpenJDK 25.0.1, component setup and doctor passed, and the TUI
picker launched and stopped the Rust-backed Java demo. Visible application checks
passed with both Python and Rust in stream and replay, exercising both → waveform
→ image → both with two waveform plots, three curves per plot and three RGB image
plots. Application snapshots confirmed the grid. These checks establish function,
not steady-state performance or additional platform qualification.

### Historical integration checks

JFreeChart 1.5.6 was checked on macOS arm64 with Homebrew OpenJDK 25.0.1,
Java 17 bytecode and a visible 60 Hz desktop at 1× scaling. All **16 combinations**
in `scenarios/jfreechart-smoke.json` completed with usable telemetry: Python and
Rust sources, stream and replay, combined replacement/scalar and append/RGB
workloads, and waveform-only/image-only views. These short runs establish
function, not steady-state JVM performance or a frontend ranking.

A separate visible application test exercised both → waveform → image → both in
stream and replay against Rust, confirmed the source generations and panel count,
and exported an application render snapshot outside measured windows. The native
UI automation service could not attach to the Java window; the snapshot is a
Swing component rendering, not a capture of compositor presentation.

Nine JUnit tests cover protocol/layout rejection, bounded delivery, replay,
conversion and Java2D raster contents, and final telemetry. Core validation passed
537 tests, with four optional browser tests skipped; web-UI type checking, proxy
test and committed-bundle rebuild also passed. CI is configured for Java 17 and 25
on macOS and Linux. Local checks used Java 25 only.

Visible Linux remains **unsupported** for this adapter: stock Swing does not
establish the repository's native Wayland contract. Headless Java2D tests on Linux
are functional diagnostics, not visible platform qualification. Retina/HiDPI
JFreeChart rendering has not been validated locally.

A separate Rust-backed repeated campaign completed **12/12** runs: the two
combined workloads, stream/replay and three repetitions, with 10 seconds of JVM
warmup plus 10 seconds measured per run. Median submitted rates met the 30 and
60 updates/s targets in all four groups; one 60 Hz replay repetition averaged
59.4 updates/s. No source-limit flag, telemetry loss, reconnect or detected display
change was recorded. This target-rate check is not a maximum-throughput ranking;
the longer JVM warmup is a separate context from earlier campaigns.
