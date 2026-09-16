import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from plotbench import runtime


@pytest.mark.parametrize("frontend", runtime.PYTHON_FRONTENDS)
def test_cold_frontend_import_gets_longer_timeout(monkeypatch, tmp_path, frontend):
    monkeypatch.setattr(runtime.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    (tmp_path / ".python-version").write_text(runtime.platform.python_version())
    executable = runtime._executable(frontend)
    executable.parent.mkdir(parents=True)
    executable.touch(mode=0o755)
    commands = []

    def slow_import(command, **options):
        commands.append(command)
        # Model a successful cold import taking longer than the old deadline.
        if options["timeout"] < 20:
            raise subprocess.TimeoutExpired(command, options["timeout"])
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"python": runtime.platform.python_version(), "qt": "6.11.2", "wayland_plugins": []}
            ),
        )

    monkeypatch.setattr(runtime.subprocess, "run", slow_import)
    result = runtime.preflight(frontends=[frontend])
    assert result["ok"], result["checks"]
    assert len(commands) == 1
    assert commands[0][:2] == [str(executable.with_name("python")), "-c"]
    assert f"import plotbench_{frontend}.app" in commands[0][2]
    assert result["runtime"]["components"][frontend]["qt"] == "6.11.2"


def test_short_runtime_queries_keep_short_timeout(monkeypatch):
    def version_query(command, **options):
        assert options["timeout"] == 15
        return SimpleNamespace(returncode=0, stdout="version\n")

    monkeypatch.setattr(runtime.subprocess, "run", version_query)
    assert runtime._run_check(["tool", "--version"]) == "version"


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_runtime_timeout_stops_process_and_reports_captured_output(stream):
    command = [
        sys.executable,
        "-c",
        f"import sys, time; print('initializing font cache', file=sys.{stream}, flush=True); time.sleep(5)",
    ]
    with pytest.raises(ValueError) as error:
        runtime._run_check(command, timeout=0.5)
    message = str(error.value)
    assert "timed out after 0.5 seconds" in message
    assert "initializing font cache" in message
    assert "time.sleep" not in message


def linux(monkeypatch):
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(runtime.platform, "libc_ver", lambda: ("glibc", "2.34"))


def test_wayland_socket_is_required_without_xwayland_fallback(monkeypatch, tmp_path):
    linux(monkeypatch)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    with pytest.raises(ValueError, match="native Wayland"):
        runtime.frontend_environment(frontends=["pyqtgraph"])
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-test")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="Cannot connect"):
        runtime.frontend_environment(frontends=["pyqtgraph"])
    connections = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, seconds):
            assert seconds == 1

        def connect(self, path):
            connections.append(path)

    monkeypatch.setattr(runtime.socket, "socket", lambda family: Connection())
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    assert runtime.frontend_environment(frontends=["pyqtgraph"])["QT_QPA_PLATFORM"] == "wayland"
    assert runtime.browser_launch_options()["args"] == ["--ozone-platform=wayland"]
    assert connections == [str(tmp_path / "wayland-test")] * 2
    monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")
    with pytest.raises(ValueError, match="conflicts"):
        runtime.frontend_environment(frontends=["pyqtgraph"])


@pytest.mark.parametrize("frontends", [["plotly"], ["iced"], ["plotly", "iced"]])
def test_non_qt_frontends_keep_irrelevant_qt_settings_but_still_require_wayland(
    monkeypatch, frontends
):
    linux(monkeypatch)
    monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")
    checked = []
    monkeypatch.setattr(runtime, "require_wayland", lambda: checked.append(True))
    environment = runtime.frontend_environment(frontends=frontends)
    assert environment["QT_QPA_PLATFORM"] == "xcb"
    assert checked == [True]

    def no_desktop():
        raise ValueError("native Wayland unavailable")

    monkeypatch.setattr(runtime, "require_wayland", no_desktop)
    with pytest.raises(ValueError, match="native Wayland"):
        runtime.frontend_environment(frontends=frontends)


@pytest.mark.parametrize("frontend", runtime.QT_FRONTENDS)
def test_every_selected_qt_frontend_rejects_xcb(monkeypatch, frontend):
    linux(monkeypatch)
    monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")
    monkeypatch.setattr(runtime, "require_wayland", lambda: None)
    with pytest.raises(ValueError, match="QT_QPA_PLATFORM='xcb'"):
        runtime.frontend_environment(frontends=["plotly", frontend])


def test_preflight_passes_selected_frontends_to_desktop_check(monkeypatch, tmp_path):
    linux(monkeypatch)
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    (tmp_path / ".python-version").write_text(runtime.platform.python_version())
    selections = []
    monkeypatch.setattr(
        runtime,
        "frontend_environment",
        lambda **options: selections.append(options["frontends"]) or {"ready": "yes"},
    )
    result = runtime.preflight(frontends=["matplotlib"])
    assert selections == [["matplotlib"]]
    assert next(item for item in result["checks"] if item["name"] == "desktop")["status"] == "ok"


def test_headless_browser_diagnostic_does_not_require_a_desktop(monkeypatch):
    linux(monkeypatch)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert runtime.browser_launch_options(headless=True) == {"headless": True}


def test_browser_executable_is_validated_and_passed_as_one_path(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime.platform, "system", lambda: "Darwin")
    path = tmp_path / "browser with spaces"
    with pytest.raises(ValueError, match="not executable"):
        runtime.browser_launch_options(browser_executable=path)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    assert runtime.browser_launch_options(browser_executable=path) == {
        "headless": False,
        "executable_path": str(path.resolve()),
    }


def test_preflight_checks_only_selected_components_and_supported_libc(monkeypatch, tmp_path):
    linux(monkeypatch)
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    (tmp_path / ".python-version").write_text(runtime.platform.python_version())
    (tmp_path / "rust-toolchain.toml").write_text('[toolchain]\nchannel="1.96.1"\n')
    assert runtime.preflight(backends=["python"])["ok"]
    missing = runtime.preflight(backends=["rust"])
    assert not missing["ok"]
    assert any("./scripts/setup rust" in item["detail"] for item in missing["checks"])
    monkeypatch.setattr(runtime.platform, "libc_ver", lambda: ("glibc", "2.28"))
    with pytest.raises(ValueError, match="glibc 2.34"):
        runtime.require_preflight(backends=["python"])


def test_doctor_json_is_machine_readable(monkeypatch, capsys):
    monkeypatch.setattr(
        runtime, "preflight", lambda **kwargs: {"ok": False, "checks": [], "runtime": {}}
    )
    assert not runtime.doctor(SimpleNamespace(json=True))
    import json

    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_session_metadata_omits_socket_paths(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "/private/run/user/session/socket")
    assert runtime.display_session()["wayland_available"]
    assert "/private/run" not in str(runtime.display_session())


def test_linux_without_session_does_not_claim_wayland(monkeypatch):
    linux(monkeypatch)
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert runtime.display_session()["display_protocol"] is None


def test_preflight_rejects_stale_native_build(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    (tmp_path / ".python-version").write_text(runtime.platform.python_version())
    (tmp_path / "rust-toolchain.toml").write_text('[toolchain]\nchannel="1.96.1"\n')
    executable = runtime._executable("rust")
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    result = runtime.preflight(backends=["rust"])
    assert not result["ok"]
    assert any("unverified" in item["detail"] for item in result["checks"])


@pytest.mark.parametrize("protocol,ok", [("wayland", True), ("unverified", False)])
def test_fyne_doctor_rejects_non_wayland_linux_build(monkeypatch, tmp_path, protocol, ok):
    linux(monkeypatch)
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    monkeypatch.setattr(runtime, "require_wayland", lambda: None)
    monkeypatch.setattr(runtime, "require_current_artifact", lambda *args: {})
    monkeypatch.setattr(runtime.shutil, "which", lambda name: None)
    (tmp_path / ".python-version").write_text(runtime.platform.python_version())
    exe = runtime._executable("fyne")
    exe.parent.mkdir(parents=True)
    exe.touch(mode=0o755)
    monkeypatch.setattr(
        runtime,
        "_run_check",
        lambda command, **kwargs: (
            json.dumps({"display_protocol": protocol})
            if command[-1] == "--runtime-info"
            else "go version go1.26 linux/amd64"
        ),
    )
    result = runtime.preflight(frontends=["fyne"])
    assert result["ok"] is ok, result["checks"]


@pytest.mark.parametrize(
    "system,headless,protocol,ok",
    [
        ("Darwin", False, "native", True),
        ("Darwin", True, "native", False),
        ("Linux", False, "xwayland", True),
        ("Linux", False, "native", False),
    ],
)
def test_java_doctor_requires_verified_display(
    monkeypatch, tmp_path, system, headless, protocol, ok
):
    if system == "Linux":
        linux(monkeypatch)
    else:
        monkeypatch.setattr(runtime.platform, "system", lambda: system)
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    monkeypatch.setattr(runtime, "require_wayland", lambda: None)
    monkeypatch.setattr(runtime, "require_xwayland", lambda: None)
    monkeypatch.setattr(runtime, "require_current_artifact", lambda *args: {})
    (tmp_path / ".python-version").write_text(runtime.platform.python_version())
    exe = runtime._executable("jfreechart")
    exe.parent.mkdir(parents=True)
    exe.write_text("jar")  # JARs are deliberately not marked executable.
    java = tmp_path / "bin/java"
    java.parent.mkdir()
    java.write_text("java")
    java.chmod(0o755)
    monkeypatch.setenv("PLOTBENCH_JAVA_HOME", str(tmp_path))
    monkeypatch.setattr(
        runtime,
        "_run_check",
        lambda command, **kwargs: json.dumps(
            {"java_feature": 17, "headless": headless, "display_protocol": protocol}
        ),
    )
    assert runtime.component_installed("jfreechart")
    result = runtime.preflight(frontends=["jfreechart"])
    assert result["ok"] is ok, result["checks"]


def test_jfreechart_linux_requires_xwayland_server(monkeypatch):
    linux(monkeypatch)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(runtime.shutil, "which", lambda name: "/usr/bin/xdpyinfo")
    monkeypatch.setattr(
        runtime, "_run_check", lambda command, **kwargs: "    XWAYLAND  (opcode: 151)"
    )
    runtime.require_xwayland()

    monkeypatch.setattr(runtime, "_run_check", lambda command, **kwargs: "    RANDR  (opcode: 139)")
    with pytest.raises(ValueError, match="not an XWayland"):
        runtime.require_xwayland()
    monkeypatch.delenv("DISPLAY")
    with pytest.raises(ValueError, match="requires XWayland"):
        runtime.require_xwayland()


def test_java_launch_uses_selected_runtime_and_jar(monkeypatch, tmp_path):
    from plotbench import runner

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "java_executable", lambda: "/selected JDK/bin/java")
    jar = tmp_path / "frontends/jfreechart/build/plotbench-jfreechart.jar"
    jar.parent.mkdir(parents=True)
    jar.touch()
    command = runner.frontend_command("jfreechart", "http://localhost:8765", "replay", "test", 3)
    assert command[:3] == ["/selected JDK/bin/java", "-jar", str(jar)]
    assert command[-2:] == ["--duration", "3"]
