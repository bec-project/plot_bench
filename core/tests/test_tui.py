"""The interactive launcher, exercised headlessly with Textual's test harness."""

import asyncio

import pytest
from textual.widgets import DataTable

from plotbench.backends import BACKENDS
from plotbench.suites import FRONTENDS
from plotbench.tui import PlotbenchTUI


def test_tui_lists_every_component_and_dispatches_launch_commands():
    async def exercise():
        app = PlotbenchTUI()
        calls = []
        # Record launches instead of starting real subprocesses.
        app.start = lambda argv, label: calls.append((list(argv), label))
        async with app.run_test() as pilot:
            table = app.query_one("#env", DataTable)
            assert table.row_count == len(FRONTENDS) + len(BACKENDS)
            await pilot.click("#rust")
            await pilot.click("#python")
            await pilot.click("#matrix")

        labels = [label for _, label in calls]
        assert labels == ["Rust source", "Python source", "Matrix editor"]
        assert calls[0][0][-2:] == ["--backend", "rust"]
        assert calls[1][0][-2:] == ["--backend", "python"]
        assert calls[2][0][-1] == "matrix"
        assert all(argv[:3] for argv, _ in calls)  # python -m plotbench.cli ...

    asyncio.run(exercise())


def test_tui_refresh_action_keeps_the_table_populated():
    async def exercise():
        app = PlotbenchTUI()
        async with app.run_test() as pilot:
            await pilot.press("r")
            table = app.query_one("#env", DataTable)
            assert table.row_count == len(FRONTENDS) + len(BACKENDS)

    asyncio.run(exercise())


def test_run_tui_requires_an_interactive_terminal(monkeypatch):
    import plotbench.tui as tui

    class NotATerminal:
        def isatty(self):
            return False

    monkeypatch.setattr(tui.sys, "stdout", NotATerminal())
    with pytest.raises(RuntimeError, match="interactive terminal"):
        tui.run_tui()
