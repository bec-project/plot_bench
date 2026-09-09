import json
from types import SimpleNamespace

import pytest

from plotbench.backends import backend_from_health
from plotbench.runner import launch_demo, run_suite


def test_existing_source_backend_is_verified_before_launch(monkeypatch):
    monkeypatch.setattr("plotbench.runner.request", lambda *a, **kw: b'{"backend":"python"}')
    args = SimpleNamespace(url="http://localhost:8765", backend="rust")
    with pytest.raises(RuntimeError, match="running python, but rust was requested"):
        launch_demo(args)


def test_backend_identity_is_explicit_with_legacy_python_default():
    assert backend_from_health({}) == "python"
    assert backend_from_health({"backend": "rust"}) == "rust"
    with pytest.raises(ValueError, match="backend"):
        backend_from_health({"backend": "unexpected"})


def test_suite_expands_backends_without_changing_delivery_modes(tmp_path, capsys):
    suite = tmp_path / "suite.json"
    suite.write_text(
        json.dumps(
            dict(
                frontends=["pyqtgraph"],
                backends=["python", "rust"],
                modes=["stream", "replay"],
                repetitions=1,
                cases=[dict(name="waveform", config={"view": "waveform"})],
            )
        )
    )
    args = SimpleNamespace(
        suite=suite, limit=None, frontends=None, modes=None, backends=None, dry_run=True
    )
    run_suite(args)
    output = capsys.readouterr().out
    assert "4 sequential runs" in output
    for mode in ("stream", "replay"):
        for backend in ("python", "rust"):
            assert f"waveform / {mode} / pyqtgraph / {backend} / repeat 1" in output


def test_duplicate_backend_selection_is_rejected(tmp_path):
    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps(dict(cases=[dict(name="waveform", config={})])))
    args = SimpleNamespace(
        suite=suite,
        limit=None,
        frontends=None,
        modes=None,
        backends=["python", "python"],
        dry_run=True,
    )
    with pytest.raises(ValueError, match="duplicates"):
        run_suite(args)


@pytest.mark.parametrize(
    "field,value",
    [
        ("measurement_seconds", float("nan")),
        ("warmup_seconds", float("inf")),
        ("cooldown_seconds", -1),
    ],
)
def test_suite_rejects_invalid_timing_before_launch(tmp_path, field, value):
    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps({"cases": [dict(name="waveform", config={})], field: value}))
    args = SimpleNamespace(
        suite=suite, limit=None, frontends=None, modes=None, backends=None, dry_run=True
    )
    with pytest.raises(ValueError, match="timing"):
        run_suite(args)
