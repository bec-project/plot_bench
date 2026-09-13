"""The interactive launcher, exercised headlessly with Textual's test harness."""

import asyncio
import subprocess
import sys

import pytest
from textual.widgets import Button, DataTable, TabPane

from plotbench.backends import BACKENDS
from plotbench.suites import FRONTENDS
from plotbench.tui import SLOTS, PlotbenchTUI


def _label(button):
    return getattr(button.label, "plain", str(button.label))


def test_tui_lists_every_component_and_dispatches_launch_commands():
    async def exercise():
        app = PlotbenchTUI()
        calls = []

        async def fake_launch(slot, argv, label):
            calls.append((slot, list(argv), label))

        app._launch = fake_launch
        async with app.run_test() as pilot:
            table = app.query_one("#env", DataTable)
            assert table.row_count == len(FRONTENDS) + len(BACKENDS)
            await pilot.click("#rust")
            await pilot.click("#python")
            await pilot.click("#matrix")
            await pilot.pause()

        assert [slot for slot, _, _ in calls] == ["rust", "python", "matrix"]
        assert calls[0][1][-2:] == ["--backend", "rust"]
        assert calls[1][1][-2:] == ["--backend", "python"]
        assert calls[2][1][-1] == "matrix"

    asyncio.run(exercise())


def test_tui_runs_actions_concurrently_in_separate_tabs_and_toggles_buttons():
    async def exercise():
        app = PlotbenchTUI()
        sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
        async with app.run_test() as pilot:
            app.run_worker(app._launch("rust", sleeper, "Rust source"))
            app.run_worker(app._launch("python", sleeper, "Python source"))
            for _ in range(200):
                await pilot.pause()
                if app._slot_running("rust") and app._slot_running("python"):
                    break
            # Both processes run at the same time, each with its own tab.
            assert app._slot_running("rust") and app._slot_running("python")
            assert len(app.query(TabPane)) == 2
            assert _label(app.query_one("#rust", Button)) == SLOTS["rust"][1]
            assert _label(app.query_one("#python", Button)) == SLOTS["python"][1]

            app.terminate("rust")
            app.terminate("python")
            for _ in range(400):
                await pilot.pause()
                if not app._slot_running("rust") and not app._slot_running("python"):
                    break
            assert not app._slot_running("rust") and not app._slot_running("python")
            assert _label(app.query_one("#rust", Button)) == SLOTS["rust"][0]

    asyncio.run(exercise())


def test_demo_launches_the_chosen_frontend_against_the_chosen_source():
    async def exercise():
        app = PlotbenchTUI()
        calls = []

        async def fake_launch(slot, argv, label):
            calls.append((slot, list(argv), label))

        app._launch = fake_launch
        async with app.run_test() as pilot:
            app.start_demo("pyqtgraph", "rust")
            app.start_demo("plotly", "python")
            await pilot.pause()

        assert [slot for slot, _, _ in calls] == ["demo-pyqtgraph", "demo-plotly"]
        assert calls[0][1][-4:] == ["demo", "pyqtgraph", "--backend", "rust"]
        assert calls[1][1][-4:] == ["demo", "plotly", "--backend", "python"]
        assert calls[0][2] == "demo pyqtgraph (rust)"

    asyncio.run(exercise())


def test_demo_is_refused_for_a_frontend_that_is_not_installed(monkeypatch):
    import plotbench.tui as tui

    monkeypatch.setattr(tui, "component_installed", lambda name: False)

    async def exercise():
        app = PlotbenchTUI()
        calls = []

        async def fake_launch(slot, argv, label):
            calls.append(slot)

        app._launch = fake_launch
        async with app.run_test() as pilot:
            app.demo_action("iced")
            await pilot.pause()
        assert calls == []

    asyncio.run(exercise())


def test_demos_run_concurrently_in_their_own_tabs_and_picking_again_stops_one():
    async def exercise():
        app = PlotbenchTUI()
        sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
        async with app.run_test() as pilot:
            app.run_worker(app._launch("demo-iced", sleeper, "demo iced (rust)"))
            app.run_worker(app._launch("demo-plotly", sleeper, "demo plotly (rust)"))
            for _ in range(200):
                await pilot.pause()
                if app._slot_running("demo-iced") and app._slot_running("demo-plotly"):
                    break
            # Two demos at once, each in its own tab; no toggle button is involved.
            assert app._slot_running("demo-iced") and app._slot_running("demo-plotly")
            assert {pane.id for pane in app.query(TabPane)} >= {
                "pane-demo-iced",
                "pane-demo-plotly",
            }

            # Choosing a running demo again stops just that one.
            app.demo_action("iced")
            for _ in range(400):
                await pilot.pause()
                if not app._slot_running("demo-iced"):
                    break
            assert not app._slot_running("demo-iced")
            assert app._slot_running("demo-plotly")

            app.terminate("demo-plotly")
            for _ in range(400):
                await pilot.pause()
                if not app._slot_running("demo-plotly"):
                    break
            assert not app._slot_running("demo-plotly")

    asyncio.run(exercise())


# A child that spawns a grandchild in its OWN session, exactly like `demo` and
# `run` spawn their source and frontend. Signalling the child's group alone would
# orphan the grandchild — the leak this guards against.
GRANDCHILD_SPAWNER = (
    "import subprocess, sys, time; "
    "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
    "start_new_session=True); time.sleep(60)"
)


def _gone(proc):
    import psutil

    return not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE


async def _launch_tree(app, pilot, slot, label):
    """Launch the spawner under a slot and return the (child, grandchild) psutil procs."""
    import psutil

    app.run_worker(app._launch(slot, [sys.executable, "-c", GRANDCHILD_SPAWNER], label))
    for _ in range(600):
        await pilot.pause()
        if app._slot_running(slot):
            child = psutil.Process(app.procs[slot].pid)
            kids = child.children(recursive=True)
            if kids:
                return child, kids[0]
    raise AssertionError("grandchild never appeared")


def test_stopping_a_slot_also_stops_grandchildren_in_other_sessions():
    async def exercise():
        import os

        app = PlotbenchTUI()
        async with app.run_test() as pilot:
            child, grandchild = await _launch_tree(app, pilot, "demo-iced", "demo iced (rust)")
            assert os.getsid(grandchild.pid) != os.getsid(child.pid)  # separate session
            app.terminate("demo-iced")
            for _ in range(900):
                await pilot.pause()
                if not app._slot_running("demo-iced") and _gone(grandchild):
                    break
            assert not app._slot_running("demo-iced")
            assert _gone(grandchild), "grandchild leaked after stopping its slot"

    asyncio.run(exercise())


def test_quitting_the_tui_stops_everything_it_started_including_grandchildren():
    async def exercise():
        app = PlotbenchTUI()
        async with app.run_test() as pilot:
            child, grandchild = await _launch_tree(app, pilot, "run", "suite smoke.json")
        # Leaving the context quits the app; on_unmount must have reaped both.
        assert _gone(child)
        assert _gone(grandchild), "grandchild leaked after quitting the TUI"

    asyncio.run(exercise())


def test_tracker_lists_owned_processes_and_detects_and_stops_leftovers(monkeypatch, tmp_path):
    import plotbench.tui as tui

    # Narrow detection to a fake checkout so the real plotbench processes on this
    # machine are neither listed nor stopped by the test.
    monkeypatch.setattr(tui, "SCOPE", str(tmp_path))
    marker = str(tmp_path / "backends/rust/target/release/plotbench-source-rust")
    leftover = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)", marker], start_new_session=True
    )
    try:

        async def exercise():
            app = PlotbenchTUI()
            sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
            async with app.run_test() as pilot:
                app.run_worker(app._launch("python", sleeper, "Python source"))
                for _ in range(600):
                    await pilot.pause()
                    app.refresh_running()
                    if app._slot_running("python") and any(
                        proc.pid == leftover.pid for proc in app.leftovers
                    ):
                        break
                assert any(proc.pid == leftover.pid for proc in app.leftovers)
                assert app.query_one("#running", DataTable).row_count >= 2
                assert not app.query_one("#leftovers", Button).disabled

                app.stop_leftovers()
                for _ in range(900):
                    await pilot.pause()
                    if leftover.poll() is not None:
                        break
                assert leftover.poll() is not None, "leftover was not stopped"

                app.terminate("python")
                for _ in range(600):
                    await pilot.pause()
                    if not app._slot_running("python"):
                        break
                assert not app._slot_running("python")

        asyncio.run(exercise())
    finally:
        if leftover.poll() is None:
            leftover.kill()


def test_run_tui_requires_an_interactive_terminal(monkeypatch):
    import plotbench.tui as tui

    class NotATerminal:
        def isatty(self):
            return False

    monkeypatch.setattr(tui.sys, "stdout", NotATerminal())
    with pytest.raises(RuntimeError, match="interactive terminal"):
        tui.run_tui()
