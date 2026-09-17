# Installation and platform setup

Run commands from the repository root. The default Rust source requires
[uv](https://docs.astral.sh/uv/) and [Rust/Cargo](https://rustup.rs/).
Select the source and frontend you need:

```sh
./scripts/setup rust pyqtgraph
./scripts/plotbench doctor --frontends pyqtgraph
./scripts/plotbench demo pyqtgraph
```

Setup creates independent environments under `.envs/`, caches under `.cache/`,
and release build outputs inside the relevant components. It does not change a
shared Python environment or install privileged system packages. Without component
arguments, setup installs the core. Setup never adds the Rust source unless `rust`
or `all` is selected. `all` explicitly selects every component; the C++ frontend
needs its separate Qt SDK.

The matrix editor and source controls are included as prebuilt Preact pages in
the core package. They need no npm/Node installation to run. Developing those
pages uses the separate [web UI workflow](../core/webui/README.md); `setup plotly`
builds the plotting adapter, not the matrix editor or source controls.

## Components and toolchains

| Component | Additional requirements |
|---|---|
| `core` | uv; Python is installed locally |
| `pyqtgraph`, `pyqtgraph-gl`, `matplotlib`, `qtgraphs` | Graphical desktop and Qt runtime system libraries |
| `rust` | Rust/Cargo and a native linker/compiler |
| `jfreechart` | JDK 17+ (`java`, `javac`, `jar`); macOS or Linux Wayland desktop with XWayland and `xdpyinfo` |
| `fyne` | Go 1.27+, native C compiler, OpenGL; native Wayland development libraries on Linux |
| `fyne-wasm` | Go 1.27+; Chromium with WebGL and WebAssembly SIMD or an explicitly selected installed browser |
| `iced` | Rust/Cargo, native linker/compiler, graphics drivers and Wayland libraries on Linux |
| `plotly` | npm to bootstrap local Node; Chromium or an explicitly selected installed browser |
| `qtgraphs-cpp` | CMake 3.21+, C++20 compiler, Qt SDK with Graphs, Quick, QuickControls2, Network, WebSockets and Test; WaylandClient on Linux |

The minimum supported uv version is declared in `.uv-version`. Setup checks the
selected executable before installing anything and prints its version and path.
Python, Node and Rust versions are declared in `.python-version`, `.node-version`
and `rust-toolchain.toml`. Python packages support the Python 3.13 series; setup
selects an available patch release rather than fixing one exact patch. Locks
describe tested dependency resolutions; update manifests and locks together when
changing a supported version. Record actual tool versions in benchmark provenance.

Rust is the default for `serve`, `demo`, `run`, `probe` and `doctor`; an explicit
suite backend selection takes precedence over the default. A default demo refuses
an existing Python source. To use Python without installing the Rust source:

```sh
./scripts/setup pyqtgraph
./scripts/plotbench doctor --frontends pyqtgraph --backends python
./scripts/plotbench demo pyqtgraph --backend python
./scripts/plotbench run --suite scenarios/smoke.json --frontends pyqtgraph --backends python --dry-run
```

For source-only use, `./scripts/setup core` and
`./scripts/plotbench serve --backend python` need no Rust toolchain. Choose
`--backends python` for Python-only receiver probes. Iced still needs Rust/Cargo
to build its frontend, independently of the selected source.

For development tools and tests:

```sh
./scripts/setup rust pyqtgraph --dev
```

Setup is repeatable. Re-run it for changed compiled/bundled components before
benchmarking; preflight rejects stale artifacts.

## macOS

Use an active graphical login session. Install Xcode command-line tools for Rust
and C++ builds. The Qt SDK can come from a compatible system installation or the
Qt installer. Python frontends obtain PySide6 through their locked environments.
Do not set Linux-specific Qt/Wayland variables on macOS. See the
[validation matrix](validation.md) for what has actually been exercised.

## Ubuntu 24.04 x86-64, Wayland

Use a native Wayland desktop with working GPU drivers. Typical build and runtime
prerequisites are:

```sh
sudo apt-get update
sudo apt-get install build-essential pkg-config cmake ninja-build \
  libwayland-dev libxkbcommon-dev libegl1 libgl1 libgl1-mesa-dev libvulkan1 mesa-vulkan-drivers \
  libfontconfig1 libfreetype6 libdbus-1-3 xdg-utils
```

For the bundled browser, install its distribution dependencies after setup:

```sh
./scripts/setup rust plotly
.envs/plotting-benchmark/bin/python -m playwright install-deps chromium
```

The Playwright dependency command may require administrator access. It is explicit
and is not run by Plotbench setup. Driver packages depend on your GPU vendor.

## RHEL-compatible Linux 9+ x86-64, Wayland

AlmaLinux 9/10 provide the CI compatibility targets. Start with a native Wayland
desktop and distribution-supported graphics drivers. Typical prerequisites are:

```sh
sudo dnf --enablerepo=crb install gcc gcc-c++ make pkgconf-pkg-config cmake ninja-build \
  wayland-devel libxkbcommon-devel mesa-libEGL mesa-libGL mesa-libGL-devel vulkan-loader \
  mesa-vulkan-drivers fontconfig freetype dbus-libs xdg-utils
```

The `crb` repository name applies to AlmaLinux/Rocky Linux. On RHEL use your
subscription's corresponding CodeReady Builder repository instead. Do not
replace the system glibc. The locked x86-64 PySide6 wheels require glibc 2.34;
the ARM wheels have a higher baseline and RHEL 9 ARM is outside this release.
See [Qt's platform requirements](https://doc.qt.io/qt-6/supported-platforms.html).

Playwright's supported Linux hosts are Ubuntu/Debian. On RHEL-compatible systems,
install an appropriate native Chromium/Chrome through your administrator's normal
package source and explicitly select its executable:

```sh
./scripts/setup rust plotly --browser system
./scripts/plotbench doctor --frontends plotly --browser-executable /usr/bin/chromium
./scripts/plotbench demo plotly --browser-executable /usr/bin/chromium
```

Use the actual installed executable path. This is a configurable compatibility
path, not an upstream support guarantee. Driver/browser lifecycle, WebGL and native
Wayland must pass the desktop validation before recording performance conclusions.
See [Playwright requirements](https://playwright.dev/python/docs/intro#system-requirements).

## C++ Qt SDK

Distribution Qt packages may be too old or omit Qt Graphs. The `qtgraphs-cpp`
frontend needs a Qt 6 SDK, 6.8 or later, with the Graphs, Quick, QuickControls2,
Network, WebSockets and Test modules, plus WaylandClient on Linux; the Python
adapters use Qt 6.11. The [Qt online installer](https://www.qt.io/download-open-source)
places such an SDK under `~/Qt/<version>/macos` on macOS or `~/Qt/<version>/gcc_64`
on Linux x86-64. When nothing else selects a Qt, setup uses the newest of those and
prints `Using the Qt SDK at …`, so `./scripts/setup qtgraphs-cpp` and the TUI
installer work as soon as the SDK is installed.

To select a particular SDK, name its prefix, the directory containing `bin/` and
`lib/cmake/`:

```sh
PLOTBENCH_QT_PREFIX="$HOME/Qt/6.11.1/macos" ./scripts/setup qtgraphs-cpp
```

Normal CMake discovery, `CMAKE_PREFIX_PATH`, `Qt6_DIR` and a `qt-cmake` on `PATH`
are respected and switch the automatic search off. If CMake reports
`Could not find a package configuration file provided by "Qt6"`, no SDK was
visible: install one or set `PLOTBENCH_QT_PREFIX`. An SDK that CMake rejects is
usually older than 6.8 or missing a module; the CMake output names it. Build
provenance records the actual Qt version. Qt Graphs has separate
[license terms](licenses.md).

## Troubleshooting

### uv cannot find the pinned Python download

uv's Python download catalog is bundled with each uv release. An older executable
can report `No download found for request` even when the pinned Python is available.
Setup requires a tested uv version from `.uv-version` or newer. Check which copy
your shell uses:

```sh
uv --version
type -a uv
```

For a standalone installation, run `uv self update`; for a Homebrew installation,
run `brew update` then `brew upgrade uv`. Other package-manager installations should
be updated through that package manager. See [uv's upgrade instructions](https://docs.astral.sh/uv/getting-started/installation/#upgrading-uv).
If an older copy still comes first on `PATH`, fix the order or select the current
executable explicitly (replace the example path):

```sh
PLOTBENCH_UV=/path/to/uv ./scripts/setup rust pyqtgraph matplotlib
```

The override applies to all uv operations in setup. Updating uv does not change
the repository's Python pin or dependency locks. See [uv's Python version documentation](https://docs.astral.sh/uv/concepts/python-versions/#installing-a-python-version).

### Runtime and display checks

Python frontend checks import the actual adapter before measurements. A fresh
Matplotlib installation may spend time discovering system fonts and building its
local font cache (on macOS this invokes `system_profiler`). These imports have a
120-second timeout; short tool/version checks retain a 15-second timeout. If an
import still times out, doctor reports captured diagnostic output. Check that the
frontend's `.cache/` directory is writable, or the directory selected by an
explicit `MPLCONFIGDIR`, then retry doctor before starting the campaign.

Run doctor with the exact component selection before a campaign. Missing
components should be installed explicitly; unavailable SDKs, stale binaries or
missing display access should be fixed before retrying into a new result directory.

Supported visible Linux runs request native Wayland. A missing session/socket or
incompatible `QT_QPA_PLATFORM` must not silently fall back to XWayland. Headless
browser and Qt offscreen checks are available for functional testing only.
Container and remote-desktop graphics can change the measured environment.

The source defaults to loopback port 8765. Stop an existing source or choose another
port if it is occupied. Recorded suites start their own sources on ephemeral ports.
Use `--display-context` for refresh/scaling/placement details unavailable from the
desktop API. Never infer physical refresh or absolute placement from missing data.

## Go / Fyne frontend

Install Go 1.27 or newer, then run `./scripts/setup rust fyne`. Fyne uses the
platform C compiler and OpenGL. On macOS install Xcode command-line tools. On
Ubuntu the additional build packages are `libgl1-mesa-dev`, `libegl1-mesa-dev`,
`libwayland-dev`, `libxkbcommon-dev` and `wayland-protocols`; on RHEL-compatible
systems use `mesa-libGL-devel`, `mesa-libEGL-devel`, `wayland-devel`,
`libxkbcommon-devel` and `wayland-protocols-devel` with the toolchain above.
Setup selects `-tags release,no_animations,wayland` on Linux; it does not fall
back to X11. Doctor rejects a Fyne build without the Wayland identity on Linux.
Go modules/build caches live in `.cache/go` and `.cache/go-build`; the executable
and provenance live in `frontends/fyne/build`. Dependencies are built with
`-mod=readonly` to preserve `go.mod`/`go.sum`. See the
[Fyne adapter](../frontends/fyne/README.md) for rendering and validation limits.

Fyne setup enables `GOEXPERIMENT=simd` by default for scalar-image conversion on
ARM64, WebAssembly and AVX-capable x86-64. On x86-64, runtime CPU and OS checks
select 512-bit AVX-512 when available, then 128-bit AVX. Native CPUs without a supported SIMD
path use the scalar fallback. Explicit `GOEXPERIMENT` settings are preserved;
use `GOEXPERIMENT=nosimd ./scripts/setup fyne` for a scalar reference build.
The selected kernel and Go build settings are recorded in results. Go's SIMD API
is still experimental; the reference path remains available for comparisons.

### Fyne WebAssembly

`fyne-wasm` is a separate browser benchmark using the shared Fyne Go module and
CPU renderer. Install Go 1.27 or newer, then run:

```sh
./scripts/setup rust fyne-wasm
./scripts/plotbench doctor --frontends fyne-wasm --backends rust
./scripts/plotbench demo fyne-wasm
```

Setup cross-compiles with `GOOS=js GOARCH=wasm`, keeps the module/build caches
local and installs the controlled browser runtime. This target does not need the
native Fyne C compiler or OpenGL development libraries. It does need working WebGL
in the selected browser. Browser installation and explicit
`--browser-executable` selection follow the Plotly browser workflow above;
`--browser system` skips the managed Chromium download. Keep browser and native
Fyne results separate. See the [adapter README](../frontends/fyne-wasm/README.md)
for the rendering boundary and current validation scope.
The browser build also defaults to SIMD; use
`GOEXPERIMENT=nosimd ./scripts/setup fyne-wasm` to build the scalar reference.

## Java / JFreeChart frontend

Install a JDK 17 or newer and run `./scripts/setup rust jfreechart`.
`PLOTBENCH_JAVA_HOME` can select a JDK explicitly; otherwise its tools come from
PATH. Maven is not required. Setup downloads SHA-256-locked JARs into `.cache/java`
and builds the independently packaged adapter in `frontends/jfreechart/build`.
The dependency JARs remain separate and unmodified, including their notices.
Doctor verifies deployed JARs, adapter sources and the selected Java runtime.

Visible Linux runs use XWayland and require `xdpyinfo` (Ubuntu: `x11-utils`).
Doctor requires an active Wayland session and confirms that `DISPLAY` exposes
the XWAYLAND extension. Record XWayland separately from native Wayland results.
Headless Java tests are functional checks only. See the
[JFreeChart adapter](../frontends/jfreechart/README.md) for timing and warmup.
