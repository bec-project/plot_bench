import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def setup_root(tmp_path):
    source = Path(__file__).resolve().parents[2]
    root = tmp_path / "checkout"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(source / "scripts/setup", root / "scripts/setup")
    for name in (".python-version", ".node-version", ".uv-version"):
        shutil.copy2(source / name, root / name)
    return root


def write_uv(path, version):
    path.write_text(
        '#!/bin/sh\nif [ "$1" = "--version" ]; then\n'
        f'  echo "uv {version} (test)"\n  exit 0\nfi\n'
        'printf "%s\\n" "$*" >> "$PLOTBENCH_SETUP_LOG"\n'
    )
    path.chmod(0o755)


def setup_environment(binaries, log):
    environment = dict(os.environ, PATH=f"{binaries}:/usr/bin:/bin", PLOTBENCH_SETUP_LOG=str(log))
    environment.pop("PLOTBENCH_UV", None)
    environment.pop("PLOTBENCH_QT_PREFIX", None)
    return environment


@pytest.mark.parametrize(
    "arguments,dev_flag",
    [([], "--no-dev"), (["core"], "--no-dev"), (["core", "--dev"], "--group dev")],
)
def test_core_setup_does_not_require_frontend_tools_or_empty_bash_arrays(
    tmp_path, setup_root, arguments, dev_flag
):
    root = setup_root
    tool = tmp_path / "uv"
    log = tmp_path / "calls"
    write_uv(tool, (root / ".uv-version").read_text().strip())
    environment = setup_environment(tmp_path, log)
    result = subprocess.run(
        ["bash", "scripts/setup", *arguments],
        cwd=root,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines()
    assert len(calls) == 2
    assert calls[0] == f"python install {(root / '.python-version').read_text().strip()} --no-bin"
    assert calls[1].startswith("sync --project core ")
    assert dev_flag in calls[1]
    assert "--extra browser" not in calls[1]


@pytest.mark.parametrize("version", ["0.8.23", "0.11.9", "invalid"])
def test_setup_rejects_old_or_unrecognized_uv_before_installing(tmp_path, setup_root, version):
    tool = tmp_path / "uv"
    log = tmp_path / "calls"
    write_uv(tool, version)
    result = subprocess.run(
        ["bash", "scripts/setup", "rust"],
        cwd=setup_root,
        env=setup_environment(tmp_path, log),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 1
    assert not log.exists()
    assert not (setup_root / ".envs").exists()
    assert (setup_root / ".uv-version").read_text().strip() in result.stderr
    assert f"found {version} at {tool}" in result.stderr
    assert "uv self update" in result.stderr
    assert "PLOTBENCH_UV=/path/to/uv" in result.stderr


@pytest.mark.parametrize("version", ["minimum", "0.12.0", "1.0.0"])
def test_setup_uv_override_handles_spaces_and_applies_to_every_sync(tmp_path, setup_root, version):
    write_uv(tmp_path / "uv", "0.8.23")
    tool = tmp_path / "current uv"
    if version == "minimum":
        version = (setup_root / ".uv-version").read_text().strip()
    write_uv(tool, version)
    log = tmp_path / "calls"
    environment = setup_environment(tmp_path, log)
    environment["PLOTBENCH_UV"] = str(tool)
    result = subprocess.run(
        ["bash", "scripts/setup", "pyqtgraph", "matplotlib"],
        cwd=setup_root,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert f"Using uv {version} at {tool}" in result.stdout
    calls = log.read_text().splitlines()
    assert len(calls) == 4
    assert calls[0].startswith("python install ")
    for call, project in zip(
        calls[1:], ("core", "frontends/pyqtgraph", "frontends/matplotlib"), strict=True
    ):
        assert call.startswith(f"sync --project {project} ")


def test_setup_reports_missing_uv_override(tmp_path, setup_root):
    environment = setup_environment(tmp_path, tmp_path / "calls")
    environment["PLOTBENCH_UV"] = str(tmp_path / "missing")
    result = subprocess.run(
        ["bash", "scripts/setup"], cwd=setup_root, env=environment, text=True, capture_output=True
    )
    assert result.returncode == 1
    assert f"uv executable not found: {environment['PLOTBENCH_UV']}" in result.stderr
    assert "https://docs.astral.sh/uv/getting-started/installation/" in result.stderr


@pytest.mark.parametrize("existing_cache", [False, True])
def test_cpp_setup_preserves_existing_cmake_generator(tmp_path, setup_root, existing_cache):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    log = tmp_path / "commands"
    write_uv(binaries / "uv", (setup_root / ".uv-version").read_text().strip())
    for tool in ("cmake", "ninja"):
        executable = binaries / tool
        executable.write_text(
            '#!/bin/sh\nprintf "%s %s\\n" "' + tool + '" "$*" >> "$PLOTBENCH_SETUP_LOG"\n'
        )
        executable.chmod(0o755)
    python = setup_root / ".envs/plotting-benchmark/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(0o755)
    if existing_cache:
        cache = setup_root / "frontends/qtgraphs-cpp/build/CMakeCache.txt"
        cache.parent.mkdir(parents=True)
        cache.write_text("CMAKE_GENERATOR:INTERNAL=Unix Makefiles\n")
    environment = setup_environment(binaries, log)
    result = subprocess.run(
        ["bash", "scripts/setup", "qtgraphs-cpp"],
        cwd=setup_root,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    configure = next(line for line in log.read_text().splitlines() if line.startswith("cmake -S"))
    assert ("-G Ninja" in configure) is not existing_cache
