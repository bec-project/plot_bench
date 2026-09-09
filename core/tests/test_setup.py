import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "arguments,dev_flag",
    [([], "--no-dev"), (["core"], "--no-dev"), (["core", "--dev"], "--group dev")],
)
def test_core_setup_does_not_require_frontend_tools_or_empty_bash_arrays(
    tmp_path, arguments, dev_flag
):
    root = Path(__file__).resolve().parents[2]
    tool = tmp_path / "uv"
    log = tmp_path / "calls"
    tool.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$PLOTBENCH_SETUP_LOG"\n')
    tool.chmod(0o755)
    environment = dict(os.environ, PATH=f"{tmp_path}:/usr/bin:/bin", PLOTBENCH_SETUP_LOG=str(log))
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


@pytest.mark.parametrize("existing_cache", [False, True])
def test_cpp_setup_preserves_existing_cmake_generator(tmp_path, existing_cache):
    import shutil

    source = Path(__file__).resolve().parents[2]
    (tmp_path / "scripts").mkdir()
    shutil.copy2(source / "scripts/setup", tmp_path / "scripts/setup")
    for name in (".python-version", ".node-version"):
        shutil.copy2(source / name, tmp_path / name)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    log = tmp_path / "commands"
    for tool in ("uv", "cmake", "ninja"):
        executable = binaries / tool
        executable.write_text(
            '#!/bin/sh\nprintf "%s %s\\n" "' + tool + '" "$*" >> "$PLOTBENCH_SETUP_LOG"\n'
        )
        executable.chmod(0o755)
    python = tmp_path / ".envs/plotting-benchmark/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(0o755)
    if existing_cache:
        cache = tmp_path / "frontends/qtgraphs-cpp/build/CMakeCache.txt"
        cache.parent.mkdir(parents=True)
        cache.write_text("CMAKE_GENERATOR:INTERNAL=Unix Makefiles\n")
    environment = dict(os.environ, PATH=f"{binaries}:/usr/bin:/bin", PLOTBENCH_SETUP_LOG=str(log))
    environment.pop("PLOTBENCH_QT_PREFIX", None)
    result = subprocess.run(
        ["bash", "scripts/setup", "qtgraphs-cpp"],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    configure = next(line for line in log.read_text().splitlines() if line.startswith("cmake -S"))
    assert ("-G Ninja" in configure) is not existing_cache
