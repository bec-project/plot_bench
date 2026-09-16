"""Runtime discovery and native desktop requirements, outside measured windows."""

import importlib.util
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tomllib
from pathlib import Path

from .backends import DEFAULT_BACKEND
from .provenance import file_hash, require_current_artifact
from .suites import FRONTENDS

ROOT = Path(__file__).resolve().parents[3]
PYTHON_FRONTENDS = ("pyqtgraph", "matplotlib", "qtgraphs")
QT_FRONTENDS = (*PYTHON_FRONTENDS, "pyqtgraph-gl", "qtgraphs-cpp")
# Cold imports can discover system fonts and initialize native libraries.
# This work happens before measurements and needs more time than version queries.
FRONTEND_IMPORT_TIMEOUT_SECONDS = 120


def _python_series(version):
    """Major.minor of a version string, so a 3.13 pin accepts any 3.13.x patch."""
    return ".".join(version.split(".")[:2])


def display_session():
    """Record session type without recording user names or local socket paths."""
    session = os.environ.get("XDG_SESSION_TYPE")
    protocol = "native" if platform.system() == "Darwin" else None
    if platform.system() == "Linux" and session in ("wayland", "x11"):
        protocol = session
    return {
        "session_type": os.environ.get("XDG_SESSION_TYPE"),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
        "wayland_available": bool(os.environ.get("WAYLAND_DISPLAY")),
        "display_protocol": protocol,
    }


def require_wayland():
    """Require a live native Wayland socket."""
    if platform.system() != "Linux":
        return
    display = os.environ.get("WAYLAND_DISPLAY")
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not display or (not Path(display).is_absolute() and not runtime):
        raise ValueError(
            "Visible Linux runs require a native Wayland desktop: WAYLAND_DISPLAY and "
            "XDG_RUNTIME_DIR must identify the current user session. Headless runs are diagnostics."
        )
    path = Path(display) if Path(display).is_absolute() else Path(runtime) / display
    try:
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(1)
            connection.connect(str(path))
    except OSError as exc:
        raise ValueError(f"Cannot connect to the current Wayland compositor: {exc}") from exc


def require_xwayland():
    """Require Swing's X display to belong to the active Wayland session."""
    if platform.system() != "Linux":
        return
    if os.environ.get("XDG_SESSION_TYPE") != "wayland" or not os.environ.get("DISPLAY"):
        raise ValueError("JFreeChart on Linux requires XWayland in a Wayland desktop session")
    if not shutil.which("xdpyinfo"):
        raise ValueError("JFreeChart on Linux requires xdpyinfo (Ubuntu: x11-utils)")
    extensions = _run_check(["xdpyinfo", "-queryExtensions"])
    if not any(line.strip().startswith("XWAYLAND  (") for line in extensions.splitlines()):
        raise ValueError("DISPLAY is not an XWayland server")


def frontend_environment(*, frontends=(), headless=False):
    """Environment for a new frontend process, preserving explicit renderer choices."""
    environment = os.environ.copy()
    if platform.system() == "Linux" and frontends and not headless:
        require_wayland()
        if "jfreechart" in frontends:
            require_xwayland()
        if set(frontends).intersection(QT_FRONTENDS):
            requested = environment.get("QT_QPA_PLATFORM")
            if requested and requested != "wayland":
                raise ValueError(
                    f"QT_QPA_PLATFORM={requested!r} conflicts with native Wayland benchmarking; "
                    "unset it or use QT_QPA_PLATFORM=wayland."
                )
            environment["QT_QPA_PLATFORM"] = "wayland"
    return environment


def browser_executable_path(value):
    if not value:
        return None
    requested = str(value)
    executable = shutil.which(requested) if "/" not in requested else requested
    path = Path(executable or requested).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"Browser executable is not executable: {value}")
    return str(path)


def browser_launch_options(*, browser_executable=None, headless=False):
    options = {"headless": headless}
    executable = browser_executable_path(browser_executable)
    if executable:
        options["executable_path"] = executable
    if platform.system() == "Linux" and not headless:
        require_wayland()
        options["args"] = ["--ozone-platform=wayland"]
    return options


def java_executable():
    home = os.environ.get("PLOTBENCH_JAVA_HOME")
    executable = str(Path(home) / "bin/java") if home else shutil.which("java")
    if not executable or not Path(executable).is_file() or not os.access(executable, os.X_OK):
        raise ValueError("JFreeChart requires Java 17+; select a JDK with PLOTBENCH_JAVA_HOME")
    return executable


def _executable(component):
    if component == "pyqtgraph-gl":
        component = "pyqtgraph"
    if component in PYTHON_FRONTENDS:
        return ROOT / f".envs/plotting-benchmark-{component}/bin/plotbench-{component}"
    return {
        "rust": ROOT / "backends/rust/target/release/plotbench-source-rust",
        "iced": ROOT / "frontends/iced/target/release/plotbench-iced",
        "jfreechart": ROOT / "frontends/jfreechart/build/plotbench-jfreechart.jar",
        "fyne": ROOT / "frontends/fyne/build/plotbench-fyne",
        "qtgraphs-cpp": ROOT / "frontends/qtgraphs-cpp/build/plotbench-qtgraphs-cpp",
    }[component]


# pyqtgraph-gl shares the pyqtgraph environment, so `setup pyqtgraph` installs both.
SETUP_ALIAS = {"pyqtgraph-gl": "pyqtgraph"}


def setup_component(component):
    """The `./scripts/setup` argument that installs the given component."""
    return SETUP_ALIAS.get(component, component)


def component_installed(component):
    """Fast filesystem check that a component's build artifact exists.

    No imports, subprocesses or Qt initialization — suitable for the editor's live
    environment probe. `doctor` remains the authority for full verification.
    """
    if component == "python":
        return True
    if component == "plotly":
        return (ROOT / "frontends/plotly/dist/index.html").is_file()
    try:
        executable = _executable(component)
    except KeyError:
        return False
    return executable.is_file() and (component == "jfreechart" or os.access(executable, os.X_OK))


def _run_check(command, *, environment=None, timeout=15):
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, env=environment, check=False
        )
    except subprocess.TimeoutExpired as exc:
        detail = exc.stderr or exc.stdout or ""
        if isinstance(detail, bytes):
            detail = detail.decode(errors="replace")
        message = f"Runtime check timed out after {timeout:g} seconds: {command[0]}"
        if detail.strip():
            message += f"\n{detail.strip()}"
        raise ValueError(message) from exc
    if result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "command failed")
    return result.stdout.strip()


def preflight(*, frontends=(), backends=(), browser_executable=None, headless=False):
    """Check selected runtimes without opening plot windows or starting measurements."""
    checks = []

    def check(name, callback):
        try:
            detail = callback()
        except (OSError, ImportError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            checks.append({"name": name, "status": "error", "detail": str(exc)})
        else:
            checks.append({"name": name, "status": "ok", "detail": detail or "Available"})

    system = platform.system()
    frontends = list(frontends or ())
    backends = list(backends or ())
    runtime = {"os": system, "architecture": platform.machine(), "display": display_session()}

    def core_available():
        expected = (ROOT / ".python-version").read_text().strip()
        if _python_series(platform.python_version()) != _python_series(expected):
            raise ValueError(
                f"Python {platform.python_version()} is not in the {expected} series "
                "(.python-version); run ./scripts/setup core"
            )
        for module in ("aiohttp", "numpy", "websockets", "psutil", "plotbench.server"):
            __import__(module)
        runtime["python"] = platform.python_version()
        return f"Python {platform.python_version()}; shared source dependencies available"

    def supported_platform():
        if system not in ("Darwin", "Linux"):
            raise ValueError("Supported hosts are macOS and Linux with a native Wayland desktop.")
        if system == "Linux":
            if platform.machine() not in ("x86_64", "amd64"):
                raise ValueError(
                    "The supported Linux release target is x86-64; ARM is unvalidated."
                )
            libc, version = platform.libc_ver()
            if libc != "glibc" or tuple(map(int, version.split(".")[:2])) < (2, 34):
                raise ValueError("Linux requires glibc 2.34 or newer (Ubuntu 22.04+/RHEL 9+).")
        return f"{system} {platform.machine()}"

    check("platform", supported_platform)
    check("core", core_available)
    if frontends and not headless:
        check(
            "desktop",
            lambda: frontend_environment(frontends=frontends)
            and "Native desktop session available",
        )
    if headless and set(frontends) - {"plotly"}:
        checks.append(
            {
                "name": "headless",
                "status": "error",
                "detail": "--headless is a Plotly diagnostic only; select --frontends plotly.",
            }
        )
    for backend in backends:
        if backend not in ("python", "rust"):
            checks.append({"name": backend, "status": "error", "detail": "Unknown backend"})
    for name in frontends:
        if name not in FRONTENDS:
            checks.append({"name": name, "status": "error", "detail": "Unknown frontend"})
    components = set(frontends) & set(FRONTENDS)
    if "rust" in backends:
        components.add("rust")
    for component in sorted(components - {"plotly"}):
        executable = _executable(component)

        def installed(executable=executable, component=component):
            if not executable.is_file() or (
                component != "jfreechart" and not os.access(executable, os.X_OK)
            ):
                raise ValueError(f"Missing {component}; run ./scripts/setup {component}")
            package = "pyqtgraph" if component == "pyqtgraph-gl" else component
            if package in PYTHON_FRONTENDS:
                module = f"plotbench_{package}.app"
                script = (
                    f"import {module}\nimport json, platform\nfrom pathlib import Path\n"
                    "from qtpy.QtCore import QLibraryInfo, qVersion\n"
                    "print(json.dumps({'python':platform.python_version(),'qt':qVersion(),"
                    "'wayland_plugins':[str(p) for p in (Path(QLibraryInfo.path(QLibraryInfo.PluginsPath)) / 'platforms').glob('*qwayland*.so')]}))"
                )
                details = json.loads(
                    _run_check(
                        [str(executable.with_name("python")), "-c", script],
                        timeout=FRONTEND_IMPORT_TIMEOUT_SECONDS,
                    )
                )
                runtime.setdefault("components", {})[component] = details
                expected = (ROOT / ".python-version").read_text().strip()
                if _python_series(details["python"]) != _python_series(expected):
                    raise ValueError(
                        f"{component} Python {details['python']} is not in the {expected} series; "
                        "rerun setup"
                    )
                if system == "Linux" and not details["wayland_plugins"]:
                    raise ValueError(f"Qt Wayland platform plugin missing for {component}")
                libraries_to_check = details["wayland_plugins"] if system == "Linux" else []
            else:
                require_current_artifact(component, ROOT)
                libraries_to_check = [str(executable)]
                if component == "jfreechart":
                    java = java_executable()
                    details = json.loads(
                        _run_check([java, "-jar", str(executable), "--runtime-info"])
                    )
                    details["executable_sha256"] = file_hash(java)
                    runtime.setdefault("components", {})[component] = details
                    libraries_to_check = []
                    if details.get("java_feature", 0) < 17:
                        raise ValueError("JFreeChart requires Java 17+")
                    if details.get("headless"):
                        raise ValueError("JFreeChart requires a visible desktop")
                    if system == "Linux":
                        require_xwayland()
                        if details.get("display_protocol") != "xwayland":
                            raise ValueError("JFreeChart must report XWayland on Linux")
                if component == "fyne":
                    details = json.loads(_run_check([str(executable), "--runtime-info"]))
                    runtime.setdefault("components", {})[component] = details
                    if details.get("headless"):
                        raise ValueError("Fyne test-driver builds cannot run visible benchmarks")
                    if system == "Linux" and details.get("display_protocol") != "wayland":
                        raise ValueError("Fyne requires a native Wayland build; rerun setup fyne")
                if component == "qtgraphs-cpp":
                    details = json.loads(_run_check([str(executable), "--runtime-info"]))
                    runtime.setdefault("components", {})[component] = details
                    if system == "Linux":
                        if not details["wayland_plugins"]:
                            raise ValueError("Qt C++ Wayland platform plugin missing from SDK")
                        libraries_to_check.extend(details["wayland_plugins"])
            if system == "Linux" and shutil.which("ldd"):
                for library in libraries_to_check:
                    libraries = _run_check(["ldd", library])
                    if "not found" in libraries:
                        raise ValueError(f"Missing native libraries for {component}:\n{libraries}")
            return str(executable.relative_to(ROOT))

        check(component, installed)
    if "plotly" in components:

        def browser_available():
            if not (ROOT / "frontends/plotly/dist/index.html").is_file():
                raise ValueError("Plotly build missing; run ./scripts/setup plotly")
            require_current_artifact("plotly", ROOT)
            if importlib.util.find_spec("playwright") is None:
                raise ValueError("Playwright missing; run ./scripts/setup plotly")
            executable = browser_executable_path(browser_executable)
            if not executable:
                environment = os.environ.copy()
                environment.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache/playwright"))
                executable = _run_check(
                    [
                        sys.executable,
                        "-c",
                        "from playwright.sync_api import sync_playwright\n"
                        "with sync_playwright() as p: print(p.chromium.executable_path)",
                    ],
                    environment=environment,
                )
                browser_executable_path(executable)
            version = _run_check([executable, "--version"])
            if not version:
                raise ValueError("Browser did not report its version with --version")
            runtime["browser"] = {
                "executable": executable,
                "version": version,
                "executable_sha256": file_hash(executable),
                "selection": "custom" if browser_executable else "bundled",
            }
            return executable

        check("plotly", browser_available)
    toolchains = {}
    if "plotly" in components:
        toolchains["node"] = {
            "expected": (ROOT / ".node-version").read_text().strip(),
            "command": [str(ROOT / ".envs/node/node_modules/node/bin/node"), "--version"],
        }
    if components & {"rust", "iced"}:
        with (ROOT / "rust-toolchain.toml").open("rb") as stream:
            rust_version = tomllib.load(stream)["toolchain"]["channel"]
        # `rustup run` reports a missing toolchain without installing anything.
        toolchains["rustc"] = {
            "expected": rust_version,
            "command": ["rustup", "run", rust_version, "rustc", "--version"],
        }
    if "fyne" in components:
        toolchains["go"] = {"command": ["go", "version"]}
    if "qtgraphs-cpp" in components:
        toolchains["cmake"] = {"command": ["cmake", "--version"]}
    for name, toolchain in toolchains.items():
        command = toolchain.pop("command")
        try:
            toolchain["version"] = _run_check(command).splitlines()[0]
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            toolchain["unavailable"] = str(exc)
            checks.append(
                {
                    "name": name,
                    "status": "warning",
                    "detail": "Build tool unavailable; existing verified artifacts can run. "
                    + str(exc),
                }
            )
    runtime["toolchains"] = toolchains
    return {
        "ok": all(item["status"] != "error" for item in checks),
        "checks": checks,
        "runtime": runtime,
    }


def require_preflight(**options):
    result = preflight(**options)
    if not result["ok"]:
        failures = [
            f"{item['name']}: {item['detail']}"
            for item in result["checks"]
            if item["status"] == "error"
        ]
        raise ValueError("Runtime checks failed:\n" + "\n".join(failures))
    return result


def doctor(args):
    result = preflight(
        frontends=getattr(args, "frontends", None) or (),
        backends=getattr(args, "backends", None) or (DEFAULT_BACKEND,),
        browser_executable=getattr(args, "browser_executable", None),
        headless=getattr(args, "headless", False),
    )
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
    else:
        for item in result["checks"]:
            print(f"{item['status'].upper()} {item['name']}: {item['detail']}")
        print("Preflight checks do not establish GPU performance or Linux validation.")
    return result["ok"]
