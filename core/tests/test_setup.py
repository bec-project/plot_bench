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


def write_tool(path, name):
    path.write_text('#!/bin/sh\nprintf "%s %s\\n" "' + name + '" "$*" >> "$PLOTBENCH_SETUP_LOG"\n')
    path.chmod(0o755)


def setup_environment(binaries, log):
    # An isolated HOME keeps a developer's own ~/Qt SDKs out of the tests.
    home = Path(log).with_name("home")
    home.mkdir(exist_ok=True)
    environment = dict(
        os.environ, PATH=f"{binaries}:/usr/bin:/bin", PLOTBENCH_SETUP_LOG=str(log), HOME=str(home)
    )
    for name in ("PLOTBENCH_UV", "PLOTBENCH_QT_PREFIX", "CMAKE_PREFIX_PATH", "Qt6_DIR"):
        environment.pop(name, None)
    return environment


@pytest.fixture
def cpp_toolchain(tmp_path, setup_root):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    write_uv(binaries / "uv", (setup_root / ".uv-version").read_text().strip())
    for tool in ("cmake", "ninja"):
        write_tool(binaries / tool, tool)
    python = setup_root / ".envs/plotting-benchmark/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(0o755)
    return binaries


def write_qt_sdk(home, version, platform, qt_cmake=True):
    prefix = home / "Qt" / version / platform
    (prefix / "lib/cmake/Qt6").mkdir(parents=True)
    (prefix / "lib/cmake/Qt6/Qt6Config.cmake").write_text("")
    if qt_cmake:
        (prefix / "bin").mkdir()
        write_tool(prefix / "bin/qt-cmake", str(prefix / "bin/qt-cmake"))
    return prefix


def run_cpp_setup(setup_root, environment):
    return subprocess.run(
        ["bash", "scripts/setup", "qtgraphs-cpp"],
        cwd=setup_root,
        env=environment,
        text=True,
        capture_output=True,
    )


def configure_call(log):
    return next(
        line for line in log.read_text().splitlines() if " -S frontends/qtgraphs-cpp " in line
    )


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
def test_cpp_setup_preserves_existing_cmake_generator(
    tmp_path, setup_root, cpp_toolchain, existing_cache
):
    if existing_cache:
        cache = setup_root / "frontends/qtgraphs-cpp/build/CMakeCache.txt"
        cache.parent.mkdir(parents=True)
        cache.write_text("CMAKE_GENERATOR:INTERNAL=Unix Makefiles\n")
    log = tmp_path / "commands"
    result = run_cpp_setup(setup_root, setup_environment(cpp_toolchain, log))
    assert result.returncode == 0, result.stderr
    configure = configure_call(log)
    assert configure.startswith("cmake -S")
    assert ("-G Ninja" in configure) is not existing_cache


def test_cpp_setup_uses_the_newest_qt_installer_sdk_when_nothing_selects_qt(
    tmp_path, setup_root, cpp_toolchain
):
    log = tmp_path / "commands"
    environment = setup_environment(cpp_toolchain, log)
    home = Path(environment["HOME"])
    write_qt_sdk(home, "6.8.3", "macos")  # lexically "newer" than 6.11.1
    newest = write_qt_sdk(home, "6.11.1", "macos")
    (home / "Qt/6.12.0/Src").mkdir(parents=True)  # sources only, no SDK
    write_qt_sdk(home, "6.12.0", "ios")  # not a desktop SDK
    result = run_cpp_setup(setup_root, environment)
    assert result.returncode == 0, result.stderr
    assert f"Using the Qt SDK at {newest}" in result.stdout
    configure = configure_call(log)
    assert configure.startswith(f"{newest}/bin/qt-cmake -S")
    assert f"-DCMAKE_PREFIX_PATH={newest}" in configure


@pytest.mark.parametrize(
    "selection", ["PLOTBENCH_QT_PREFIX", "CMAKE_PREFIX_PATH", "Qt6_DIR", "qt-cmake"]
)
def test_cpp_setup_respects_an_explicit_qt_selection(
    tmp_path, setup_root, cpp_toolchain, selection
):
    log = tmp_path / "commands"
    environment = setup_environment(cpp_toolchain, log)
    write_qt_sdk(Path(environment["HOME"]), "6.11.1", "macos")  # must stay unused
    chosen = write_qt_sdk(tmp_path / "elsewhere", "6.9.0", "gcc_64")
    if selection == "qt-cmake":
        write_tool(cpp_toolchain / "qt-cmake", "qt-cmake")
    else:
        environment[selection] = str(chosen)
    result = run_cpp_setup(setup_root, environment)
    assert result.returncode == 0, result.stderr
    assert "Using the Qt SDK" not in result.stdout
    configure = configure_call(log)
    assert "6.11.1" not in configure
    if selection == "PLOTBENCH_QT_PREFIX":
        assert configure.startswith(f"{chosen}/bin/qt-cmake -S")
        assert f"-DCMAKE_PREFIX_PATH={chosen}" in configure
    else:
        # CMake reads CMAKE_PREFIX_PATH and Qt6_DIR itself; qt-cmake carries its own SDK.
        assert configure.startswith("qt-cmake -S" if selection == "qt-cmake" else "cmake -S")
        assert "-DCMAKE_PREFIX_PATH" not in configure


@pytest.mark.parametrize("sdk_present", [False, True])
def test_cpp_setup_failure_explains_how_to_select_a_qt_sdk(
    tmp_path, setup_root, cpp_toolchain, sdk_present
):
    (cpp_toolchain / "cmake").write_text(
        '#!/bin/sh\ncase " $* " in *" -S "*) echo "Could not find Qt6" >&2; exit 1 ;; esac\n'
    )
    log = tmp_path / "commands"
    environment = setup_environment(cpp_toolchain, log)
    prefix = None
    if sdk_present:
        prefix = write_qt_sdk(Path(environment["HOME"]), "6.11.1", "gcc_64", qt_cmake=False)
    result = run_cpp_setup(setup_root, environment)
    assert result.returncode == 1
    assert "Could not find Qt6" in result.stderr
    assert (
        "PLOTBENCH_QT_PREFIX=/path/to/Qt/6.11.1/macos ./scripts/setup qtgraphs-cpp" in result.stderr
    )
    assert 'See "C++ Qt SDK" in docs/setup.md.' in result.stderr
    if sdk_present:
        assert f"CMake did not accept the SDK at {prefix}" in result.stderr
    else:
        assert (
            f"no Qt online-installer SDK under {environment['HOME']}/Qt/<version>" in result.stderr
        )
