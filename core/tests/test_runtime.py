from types import SimpleNamespace

import pytest

from plotbench import runtime


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
