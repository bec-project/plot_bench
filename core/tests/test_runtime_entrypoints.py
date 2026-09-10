"""Preflight failures precede creating campaigns or starting sources."""

import json
from types import SimpleNamespace

import pytest

from plotbench import cli, probe, runner, runtime


@pytest.mark.parametrize("kind", ["run", "probe"])
def test_failed_preflight_leaves_no_result_directory(tmp_path, monkeypatch, kind):
    suite = tmp_path / "suite.json"
    suite.write_text(
        json.dumps(
            {
                "frontends": ["pyqtgraph"],
                "backends": ["python"],
                "modes": ["stream"],
                "repetitions": 1,
                "cases": [{"name": "small", "config": {}}],
            }
        )
    )
    output = tmp_path / "results"
    args = SimpleNamespace(suite=suite, output=output, dry_run=False, headless=False)
    module = runner if kind == "run" else probe

    def unavailable(**options):
        assert options["backends"] == ["python"]
        raise ValueError("Required runtime unavailable")

    def unexpected_source(*args, **kwargs):
        pytest.fail("The source must not start after a failed preflight")

    monkeypatch.setattr(module, "require_preflight", unavailable)
    monkeypatch.setattr(module, "source_process", unexpected_source)
    with pytest.raises(ValueError, match="Required runtime unavailable"):
        (runner.run_suite if kind == "run" else probe.run_probe_suite)(args)
    assert not output.exists()


def test_demo_checks_runtime_before_starting_an_owned_source(monkeypatch):
    args = SimpleNamespace(
        url="http://127.0.0.1:8765", backend="python", frontend="pyqtgraph", mode="stream"
    )

    def offline(*args, **kwargs):
        raise OSError("No existing source")

    def unavailable(**options):
        assert options["backends"] == ["python"]
        raise ValueError("No graphical session")

    def unexpected_source(*args, **kwargs):
        pytest.fail("Preflight must finish before creating a source")

    monkeypatch.setattr(runner, "request", offline)
    monkeypatch.setattr(runner, "require_preflight", unavailable)
    monkeypatch.setattr(runner, "source_process", unexpected_source)
    with pytest.raises(ValueError, match="No graphical session"):
        runner.launch_demo(args)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8765", "http://source.example:8765"])
def test_attached_demo_does_not_require_a_local_source_build(monkeypatch, url):
    args = SimpleNamespace(url=url, backend="rust", frontend="pyqtgraph", mode="stream")
    checks = []
    monkeypatch.setattr(runner, "request", lambda *args, **kwargs: b'{"backend":"rust"}')
    monkeypatch.setattr(runner, "require_preflight", lambda **options: checks.append(options))
    monkeypatch.setattr(
        runner,
        "frontend_environment",
        lambda **options: (
            {} if options["frontends"] == ["pyqtgraph"] else pytest.fail("Wrong selection")
        ),
    )
    monkeypatch.setattr(runner, "frontend_command", lambda *args, **kwargs: ["frontend"])
    monkeypatch.setattr(
        runner.subprocess,
        "Popen",
        lambda *args, **kwargs: SimpleNamespace(wait=lambda: None, returncode=0),
    )

    def unexpected_source(*args, **kwargs):
        pytest.fail("An attached demo must not start a local source")

    monkeypatch.setattr(runner, "source_process", unexpected_source)
    runner.launch_demo(args)
    assert checks == [{"frontends": ["pyqtgraph"], "backends": [], "browser_executable": None}]


def test_doctor_json_failure_is_machine_readable_and_nonzero(monkeypatch, capsys):
    result = {
        "ok": False,
        "checks": [{"name": "plotly", "status": "error", "detail": "Browser missing"}],
        "runtime": {},
    }
    monkeypatch.setattr(runtime, "preflight", lambda **kwargs: result)
    monkeypatch.setattr("sys.argv", ["plotbench", "doctor", "--frontends", "plotly", "--json"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out) == result


def test_missing_tui_dependencies_point_to_repo_setup(monkeypatch, capsys):
    import sys

    monkeypatch.setitem(sys.modules, "plotbench.tui", None)
    monkeypatch.setattr(sys, "argv", ["plotbench", "tui"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    message = capsys.readouterr().err
    assert "./scripts/setup core" in message
    assert "pip install" not in message
