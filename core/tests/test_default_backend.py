"""New commands default to Rust while explicit Python requests remain usable."""

import json
from types import SimpleNamespace

import pytest

from plotbench import backends, cli, runner, runtime


@pytest.mark.parametrize("backend", [None, "python"])
def test_serve_selects_rust_by_default_and_allows_python(monkeypatch, tmp_path, backend):
    selected = []
    monkeypatch.setattr(backends, "launch_rust_source", lambda *args: selected.append("rust"))
    monkeypatch.setattr(
        "plotbench.server.Server", lambda *args: SimpleNamespace(app=lambda: "python")
    )
    monkeypatch.setattr("aiohttp.web.run_app", lambda app, **kwargs: selected.append(app))
    argv = ["plotbench", "serve", "--output", str(tmp_path / "source")]
    if backend:
        argv += ["--backend", backend]
    monkeypatch.setattr("sys.argv", argv)
    cli.main()
    assert selected == [backend or "rust"]


@pytest.mark.parametrize("backend", [None, "python"])
def test_demo_cli_selects_rust_by_default_and_allows_python(monkeypatch, backend):
    selected = []
    monkeypatch.setattr(runner, "launch_demo", lambda args: selected.append(args.backend))
    argv = ["plotbench", "demo", "pyqtgraph"]
    if backend:
        argv += ["--backend", backend]
    monkeypatch.setattr("sys.argv", argv)
    cli.main()
    assert selected == [backend or "rust"]


def test_default_demo_refuses_to_silently_attach_to_python(monkeypatch):
    monkeypatch.setattr(runner, "request", lambda *args, **kwargs: b'{"backend":"python"}')
    with pytest.raises(RuntimeError, match="running python, but rust was requested"):
        runner.launch_demo(SimpleNamespace(url="http://127.0.0.1:8765", backend=None))


@pytest.mark.parametrize("backend", [None, "python"])
def test_doctor_checks_the_selected_default_source(monkeypatch, capsys, backend):
    selected = []

    def preflight(**options):
        selected.extend(options["backends"])
        return {"ok": True, "checks": [], "runtime": {}}

    monkeypatch.setattr(runtime, "preflight", preflight)
    argv = ["plotbench", "doctor", "--json"]
    if backend:
        argv += ["--backends", backend]
    monkeypatch.setattr("sys.argv", argv)
    cli.main()
    assert selected == [backend or "rust"]
    assert json.loads(capsys.readouterr().out)["ok"]


@pytest.mark.parametrize("kind", ["run", "probe"])
@pytest.mark.parametrize("backend", [None, "python"])
def test_json_previews_default_to_rust_and_allow_python(
    tmp_path, monkeypatch, capsys, kind, backend
):
    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps({"cases": [{"name": "small", "config": {}}]}))
    argv = ["plotbench", kind, "--suite", str(suite), "--dry-run", "--json"]
    if backend:
        argv += ["--backends", backend]
    monkeypatch.setattr("sys.argv", argv)
    cli.main()
    plan = json.loads(capsys.readouterr().out)
    assert plan["selected_backends"] == [backend or "rust"]
    assert {job["backend"] for job in plan["jobs"]} == {backend or "rust"}


@pytest.mark.parametrize("kind", ["run", "probe"])
def test_bundled_default_suite_selects_rust(monkeypatch, capsys, kind):
    monkeypatch.setattr("sys.argv", ["plotbench", kind, "--dry-run", "--json"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["selected_backends"] == ["rust"]
