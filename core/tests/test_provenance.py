import json
import subprocess
from types import SimpleNamespace

import pytest

from plotbench import provenance


def write(root, relative, content="source"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def create_component(root, component):
    directory = "backends/rust" if component == "rust" else f"frontends/{component}"
    source = write(
        root, f"{directory}/src/main.ts" if component == "plotly" else f"{directory}/src/main.rs"
    )
    artifact = root / provenance.ARTIFACTS[component]
    entrypoint = artifact / "index.html" if component == "plotly" else artifact
    write(root, entrypoint.relative_to(root), "compiled artifact")
    if component == "plotly":
        write(root, f"{directory}/dist/assets/main.js", "compiled JavaScript")
    return source, artifact, entrypoint


@pytest.mark.parametrize("component", ["rust", "iced", "plotly"])
def test_recorded_build_matches_sources_and_actual_artifact_bytes(tmp_path, component):
    source, artifact, entrypoint = create_component(tmp_path, component)
    provenance.record_build(component, tmp_path)
    identity = provenance.require_current_artifact(component, tmp_path)
    assert identity["matches_sources"] is True
    assert identity["matches_artifact"] is True
    assert identity["entrypoint_present"] is True
    assert identity["files"][entrypoint.relative_to(tmp_path).as_posix()] == provenance.file_hash(
        entrypoint
    )
    assert (
        identity["build"]["checkout_source_sha256"]
        == provenance.capture_provenance(tmp_path)["source_sha256"]
    )
    assert all(not name.endswith("/plotbench-build.json") for name in identity["files"])

    entrypoint.write_text("different actual executable or bundle")
    changed = provenance.artifact_identity(component, tmp_path)
    assert changed["matches_sources"] is True
    assert changed["matches_artifact"] is False
    with pytest.raises(RuntimeError, match=f"./scripts/setup {component}"):
        provenance.require_current_artifact(component, tmp_path)


@pytest.mark.parametrize("component", ["rust", "iced", "plotly"])
def test_source_edits_invalidate_build_even_when_artifact_is_unchanged(tmp_path, component):
    source, artifact, entrypoint = create_component(tmp_path, component)
    provenance.record_build(component, tmp_path)
    source.write_text("updated source awaiting rebuild")
    identity = provenance.artifact_identity(component, tmp_path)
    assert identity["matches_sources"] is False
    assert identity["matches_artifact"] is True
    with pytest.raises(RuntimeError, match="before measuring"):
        provenance.require_current_artifact(component, tmp_path)


def test_source_fingerprint_ignores_outputs_dependencies_and_presentation_files(tmp_path):
    source, artifact, entrypoint = create_component(tmp_path, "plotly")
    original = provenance.component_source_hash("plotly", tmp_path)
    for folder in (
        "node_modules",
        "dist",
        "target",
        ".cache",
        ".envs",
        ".cargo-cache",
        ".qa-results",
        "results",
        "screenshots",
        "docs",
        "audit",
        ".idea",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "test-results",
        "playwright-report",
    ):
        write(tmp_path, f"frontends/plotly/{folder}/generated.json", "generated output")
    write(tmp_path, "frontends/plotly/README.md", "presentation changes")
    assert provenance.component_source_hash("plotly", tmp_path) == original
    write(tmp_path, "frontends/plotly/public/palette.bin", "bundled binary asset")
    assert provenance.component_source_hash("plotly", tmp_path) != original


def test_bundle_file_addition_or_removal_invalidates_actual_build_identity(tmp_path):
    source, artifact, entrypoint = create_component(tmp_path, "plotly")
    provenance.record_build("plotly", tmp_path)
    asset = artifact / "assets/main.js"
    asset.unlink()
    assert provenance.artifact_identity("plotly", tmp_path)["matches_artifact"] is False
    asset.write_text("compiled JavaScript")
    extra = write(tmp_path, "frontends/plotly/dist/assets/extra.js", "unrecorded asset")
    assert provenance.artifact_identity("plotly", tmp_path)["matches_artifact"] is False
    extra.unlink()
    assert provenance.require_current_artifact("plotly", tmp_path)["matches_artifact"] is True


@pytest.mark.parametrize("component", ["rust", "plotly"])
def test_missing_manifest_and_deleted_entrypoint_are_never_verified(tmp_path, component):
    source, artifact, entrypoint = create_component(tmp_path, component)
    identity = provenance.artifact_identity(component, tmp_path)
    assert identity["build"] is None
    assert identity["matches_sources"] is None
    with pytest.raises(RuntimeError, match="missing, changed, or unverified"):
        provenance.require_current_artifact(component, tmp_path)
    provenance.record_build(component, tmp_path)
    entrypoint.unlink()
    assert provenance.artifact_identity(component, tmp_path)["matches_artifact"] is False
    with pytest.raises(FileNotFoundError):
        provenance.record_build(component, tmp_path)


@pytest.mark.parametrize(
    "content", ["{", "null", "[]", '"text"', "{}", '{"source_sha256": "a", "files": []}']
)
def test_corrupt_manifest_is_rejected_and_next_build_can_repair_it(tmp_path, content):
    source, artifact, entrypoint = create_component(tmp_path, "iced")
    manifest = artifact.parent / "plotbench-build.json"
    manifest.write_text(content)
    identity = provenance.artifact_identity("iced", tmp_path)
    assert identity["build_error"]
    assert identity["matches_sources"] is False
    with pytest.raises(RuntimeError, match="./scripts/setup iced"):
        provenance.require_current_artifact("iced", tmp_path)
    provenance.record_build("iced", tmp_path)
    assert provenance.require_current_artifact("iced", tmp_path)["matches_artifact"] is True


def test_empty_plotly_dist_cannot_be_blessed_even_with_matching_empty_manifest(tmp_path):
    write(tmp_path, "frontends/plotly/src/main.ts", "source")
    dist = tmp_path / provenance.ARTIFACTS["plotly"]
    dist.mkdir()
    (dist / "plotbench-build.json").write_text(
        json.dumps(
            {"source_sha256": provenance.component_source_hash("plotly", tmp_path), "files": {}}
        )
    )
    identity = provenance.artifact_identity("plotly", tmp_path)
    assert identity["matches_sources"] is True
    assert identity["matches_artifact"] is False
    with pytest.raises(RuntimeError, match="./scripts/setup plotly"):
        provenance.require_current_artifact("plotly", tmp_path)
    with pytest.raises(FileNotFoundError, match="index.html"):
        provenance.record_build("plotly", tmp_path)


def test_exported_source_tree_without_git_still_records_code_and_lock_identity(
    tmp_path, monkeypatch
):
    def no_git(*args):
        raise FileNotFoundError("git is unavailable")

    monkeypatch.setattr(provenance, "git_output", no_git)
    source = write(tmp_path, "core/src/plotbench/entry.py", "initial")
    lock = write(tmp_path, "frontends/plotly/package-lock.json", '{"lockfileVersion":3}')
    first = provenance.capture_provenance(tmp_path)
    assert first["git"] is None
    assert first["git_error"] == "FileNotFoundError"
    assert first["lockfiles"] == {lock.relative_to(tmp_path).as_posix(): provenance.file_hash(lock)}
    write(tmp_path, "custom-benchmark-output/run-0001/run.json", "measurement output")
    write(tmp_path, "summary.json", "report generated directly in the checkout")
    assert provenance.capture_provenance(tmp_path)["source_sha256"] == first["source_sha256"]
    source.write_text("changed without git")
    assert provenance.capture_provenance(tmp_path)["source_sha256"] != first["source_sha256"]


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], stderr=subprocess.DEVNULL, timeout=10
    )


def test_git_dirty_context_tracks_staged_and_untracked_source_content(tmp_path):
    git(tmp_path, "init", "--quiet")
    source = write(tmp_path, "core/src/plotbench/main.py", "initial source")
    write(tmp_path, ".gitignore", "results/\n")
    git(tmp_path, "add", ".")
    git(
        tmp_path,
        "-c",
        "user.name=Plotbench test",
        "-c",
        "user.email=test@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "-m",
        "test: provenance fixture",
    )
    clean = provenance.capture_provenance(tmp_path)
    assert clean["git"]["commit"] == git(tmp_path, "rev-parse", "HEAD").decode().strip()
    assert clean["git"]["dirty"] is False
    source.write_text("staged source edit")
    git(tmp_path, "add", ".")
    dirty = provenance.capture_provenance(tmp_path)
    assert dirty["git"]["dirty"] is True
    assert dirty["git"]["tracked_diff_sha256"] != clean["git"]["tracked_diff_sha256"]
    assert dirty["source_sha256"] != clean["source_sha256"]
    untracked = write(tmp_path, "core/src/plotbench/new_module.py", "first untracked content")
    first_untracked = provenance.capture_provenance(tmp_path)
    untracked.write_text("different untracked content")
    second_untracked = provenance.capture_provenance(tmp_path)
    assert (
        second_untracked["git"]["tracked_diff_sha256"]
        == first_untracked["git"]["tracked_diff_sha256"]
    )
    assert second_untracked["source_sha256"] != first_untracked["source_sha256"]
    write(tmp_path, "results/report.json", "generated output")
    assert (
        provenance.capture_provenance(tmp_path)["source_sha256"]
        == second_untracked["source_sha256"]
    )


def test_nested_export_does_not_borrow_parent_repository_commit(tmp_path):
    git(tmp_path, "init", "--quiet")
    exported = tmp_path / "exported"
    write(exported, "core/src/main.py", "exported source")
    captured = provenance.capture_provenance(exported)
    assert captured["git"] is None
    assert len(captured["source_sha256"]) == 64


@pytest.mark.parametrize("entrypoint", ["frontend_suite", "receiver_probe"])
def test_stale_release_is_rejected_before_creating_output_or_starting_processes(
    tmp_path, monkeypatch, entrypoint
):
    from plotbench import probe, runner

    source, artifact, binary = create_component(tmp_path, "rust")
    provenance.record_build("rust", tmp_path)
    binary.write_text("unrecorded replacement executable")
    suite = write(
        tmp_path,
        "suite.json",
        json.dumps(
            {
                "cases": [{"name": "tiny", "config": {"view": "waveform"}}],
                "backends": ["rust"],
                "frontends": ["pyqtgraph"],
                "repetitions": 1,
            }
        ),
    )
    output = tmp_path / "measurement-output"
    args = SimpleNamespace(
        suite=suite,
        output=output,
        limit=None,
        frontends=None,
        modes=None,
        backends=None,
        warmup=None,
        duration=None,
        repetitions=None,
        dry_run=False,
        headless=True,
    )
    module = runner if entrypoint == "frontend_suite" else probe
    run = runner.run_suite if entrypoint == "frontend_suite" else probe.run_probe_suite

    def unexpected_process(*args, **kwargs):
        pytest.fail("Stale artifact check must happen before launching a process")

    monkeypatch.setattr(module, "source_process", unexpected_process)
    monkeypatch.setattr(
        module,
        "require_current_artifact",
        lambda component: provenance.require_current_artifact(component, tmp_path),
    )
    with pytest.raises(RuntimeError, match="./scripts/setup rust"):
        run(args)
    assert not output.exists()


def test_native_artifact_hash_includes_qml_and_cmake_configuration(tmp_path):
    component = tmp_path / "frontends" / "qtgraphs-cpp"
    component.mkdir(parents=True)
    for filename in ("Main.qml", "CMakeLists.txt"):
        path = component / filename
        before = provenance.component_source_hash("qtgraphs-cpp", tmp_path)
        path.write_text("first version")
        first = provenance.component_source_hash("qtgraphs-cpp", tmp_path)
        assert first != before
        path.write_text("second version")
        assert provenance.component_source_hash("qtgraphs-cpp", tmp_path) != first


@pytest.mark.parametrize(
    "filename,initial,updated",
    [(".node-version", "24.19.0", "24.20.0"), (".uv-version", "0.11.26", "0.12.0")],
)
def test_checkout_hash_includes_declared_toolchains(tmp_path, filename, initial, updated):
    path = tmp_path / filename
    path.write_text(initial + "\n")
    before = provenance.source_hash(tmp_path, checkout=True)
    path.write_text(updated + "\n")
    assert provenance.source_hash(tmp_path, checkout=True) != before


@pytest.mark.parametrize("filename", ["main.go", "go.mod", "go.sum"])
def test_fyne_go_sources_and_dependencies_invalidate_native_build(tmp_path, filename):
    write(tmp_path, "frontends/fyne/build/plotbench-fyne", "compiled")
    source = write(tmp_path, f"frontends/fyne/{filename}", "before")
    provenance.record_build("fyne", tmp_path)
    provenance.require_current_artifact("fyne", tmp_path)
    source.write_text("after")
    with pytest.raises(RuntimeError, match="unverified"):
        provenance.require_current_artifact("fyne", tmp_path)
