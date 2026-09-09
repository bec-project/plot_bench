"""The interactive launcher, exercised headlessly with Textual's test harness."""

import asyncio
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


def test_run_tui_requires_an_interactive_terminal(monkeypatch):
    import plotbench.tui as tui

    class NotATerminal:
        def isatty(self):
            return False

    monkeypatch.setattr(tui.sys, "stdout", NotATerminal())
    with pytest.raises(RuntimeError, match="interactive terminal"):
        tui.run_tui()
