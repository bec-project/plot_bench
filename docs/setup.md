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

## Components and toolchains

| Component | Additional requirements |
|---|---|
| `core` | uv; Python is installed locally |
| `pyqtgraph`, `pyqtgraph-gl`, `matplotlib`, `qtgraphs` | Graphical desktop and Qt runtime system libraries |
| `rust` | Rust/Cargo and a native linker/compiler |
| `iced` | Rust/Cargo, native linker/compiler, graphics drivers and Wayland libraries on Linux |
| `plotly` | npm to bootstrap local Node; Chromium or an explicitly selected installed browser |
| `qtgraphs-cpp` | CMake 3.21+, C++20 compiler, Qt SDK with Graphs, Quick, QuickControls2, Network, WebSockets and Test; WaylandClient on Linux |

Python, Node and Rust versions are declared in `.python-version`, `.node-version`
and `rust-toolchain.toml`. Python packages currently support Python 3.13. Locks
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

Distribution Qt packages may be too old or omit Qt Graphs. Provide a compatible
Qt 6 SDK (6.8 or later; the Python adapters use Qt 6.11) and record the actual version:

```sh
PLOTBENCH_QT_PREFIX="$HOME/Qt/6.11.2/gcc_64" ./scripts/setup qtgraphs-cpp
```

The SDK prefix is the directory containing `bin/` and `lib/cmake/`. Normal CMake
discovery and `CMAKE_PREFIX_PATH` are also supported; use the SDK path appropriate
for your machine. Qt Graphs has separate [license terms](licenses.md).

## Troubleshooting

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
