"""Interactive launcher (Textual): inspect environments and launch sources,
component setup, benchmark suites and the matrix editor from one place.

Each action runs as an independent process with its own output tab, so a source,
a suite run, a setup, the matrix editor and several frontend demos can all run at
once. A launch button toggles to Stop while its action is running; a running demo
is stopped by choosing it again in the demo picker. The TUI orchestrates the same
commands you would run by hand (`./scripts/setup` for installs, `python -m
plotbench.cli ...` otherwise); it expects a repository checkout and never measures
anything itself.
"""

import asyncio
import os
import signal
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    OptionList,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)
from textual.widgets.option_list import Option

from .backends import BACKENDS
from .runtime import component_installed, setup_component
from .suites import FRONTENDS

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts" / "setup"
SCENARIOS = ROOT / "scenarios"
CUSTOM = ROOT / "scenarios_custom"
INSTALLABLE = ["rust", "pyqtgraph", "matplotlib", "qtgraphs", "qtgraphs-cpp", "iced", "plotly"]

# Each launch slot: sidebar button labels for idle and running states.
SLOTS = {
    "rust": ("Launch Rust source", "Stop Rust source"),
    "python": ("Launch Python source", "Stop Python source"),
    "install": ("Install component", "Stop install"),
    "run": ("Run a suite", "Stop suite"),
    "matrix": ("Matrix editor", "Stop matrix editor"),
}
STATE_MARK = {"live": "● live", "done": "○ done", "failed": "✗ failed"}


def _cli(*args):
    return [sys.executable, "-m", "plotbench.cli", *args]


class ChooseScreen(ModalScreen):
    """A small modal that dismisses with the chosen value (or None on cancel)."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, title, options):
        super().__init__()
        self._title = title
        self._options = options

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._title, id="dialog-title")
            yield OptionList(*(Option(label) for label, _ in self._options), id="dialog-options")
            yield Button("Cancel", id="dialog-cancel")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self._options[event.option_index][1])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class PlotbenchTUI(App):
    TITLE = "Plotbench"
    SUB_TITLE = "interactive launcher"
    CSS = """
    #body { height: 1fr; }
    #sidebar { width: 30; padding: 1 1; border-right: solid $panel; }
    #sidebar Button { width: 100%; margin-bottom: 1; }
    #main { padding: 1 2; }
    .section-title { text-style: bold; color: $accent; margin-bottom: 1; }
    #env { height: auto; max-height: 45%; margin-bottom: 1; }
    #tabs { height: 1fr; }
    RichLog { background: $surface; padding: 0 1; }
    .spacer { height: 1fr; }
    ChooseScreen { align: center middle; }
    #dialog { width: 70; height: auto; max-height: 80%; padding: 1 2; background: $surface; border: solid $accent; }
    #dialog-title { text-style: bold; margin-bottom: 1; }
    #dialog-options { height: auto; max-height: 20; margin-bottom: 1; }
    """
    BINDINGS = [("q", "quit", "Quit"), ("r", "refresh", "Refresh"), ("x", "stop", "Stop active")]

    def __init__(self):
        super().__init__()
        self.procs = {}
        self._panes = set()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("Actions", classes="section-title")
                for slot, (idle, _) in SLOTS.items():
                    yield Button(idle, id=slot)
                yield Button("Launch demo", id="demo")
                yield Static("", classes="spacer")
                yield Button("Refresh", id="refresh")
            with Vertical(id="main"):
                yield Static("Environments", classes="section-title")
                yield DataTable(id="env", cursor_type="row", zebra_stripes=True)
                yield Static(
                    "Output — each action gets a tab; several can run at once",
                    classes="section-title",
                )
                yield TabbedContent(id="tabs")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#env", DataTable)
        table.add_columns("Component", "Type", "Installed", "Install with")
        if not SCRIPTS.exists():
            self.query_one("#install", Button).disabled = True
        self.refresh_env()

    # -- environment table ---------------------------------------------------
    def refresh_env(self) -> None:
        table = self.query_one("#env", DataTable)
        table.clear()
        for name in FRONTENDS:
            installed = "yes" if component_installed(name) else "no"
            table.add_row(name, "frontend", installed, f"./scripts/setup {setup_component(name)}")
        for name in BACKENDS:
            installed = "yes" if component_installed(name) else "no"
            setup = "n/a (core)" if name == "python" else f"./scripts/setup {name}"
            table.add_row(name, "source", installed, setup)

    def action_refresh(self) -> None:
        self.refresh_env()

    # -- actions --------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        slot = event.button.id
        if slot == "refresh":
            self.action_refresh()
        elif slot == "demo":
            self.choose_demo()
        elif slot in SLOTS:
            self.toggle(slot)

    def toggle(self, slot) -> None:
        if self._slot_running(slot):
            self.terminate(slot)
            return
        if slot == "install":
            self.choose_install()
        elif slot == "run":
            self.choose_run()
        elif slot == "rust":
            self.run_worker(self._launch("rust", _cli("serve", "--backend", "rust"), "Rust source"))
        elif slot == "python":
            self.run_worker(
                self._launch("python", _cli("serve", "--backend", "python"), "Python source")
            )
        elif slot == "matrix":
            self.run_worker(self._launch("matrix", _cli("matrix"), "Matrix editor"))

    def choose_install(self) -> None:
        if not SCRIPTS.exists():
            self.notify("scripts/setup not found; run the TUI from a repository checkout.")
            return
        options = [
            (f"{name}  {'installed' if component_installed(name) else 'missing'}", name)
            for name in INSTALLABLE
        ]

        def picked(value):
            if value:
                self.run_worker(
                    self._launch("install", ["./scripts/setup", value], f"setup {value}")
                )

        self.push_screen(ChooseScreen("Install or rebuild which component?", options), picked)

    def choose_run(self) -> None:
        suites = []
        for directory, tag in ((SCENARIOS, "scenarios"), (CUSTOM, "scenarios_custom")):
            if directory.is_dir():
                for path in sorted(directory.glob("*.json")):
                    suites.append((f"{tag}/{path.name}", f"{tag}/{path.name}"))
        if not suites:
            self.notify("No suites found in scenarios/ or scenarios_custom/.")
            return

        def picked(value):
            if value:
                label = f"suite {value.split('/')[-1]}"
                self.run_worker(self._launch("run", _cli("run", "--suite", value), label))

        self.push_screen(ChooseScreen("Run which suite?", suites), picked)

    def choose_demo(self) -> None:
        options = []
        for name in FRONTENDS:
            if self._slot_running(f"demo-{name}"):
                state = "running — select to stop"
            else:
                state = "installed" if component_installed(name) else "missing"
            options.append((f"{name}  {state}", name))

        def picked(frontend):
            if frontend:
                self.demo_action(frontend)

        self.push_screen(
            ChooseScreen("Demo which frontend? Running demos share one source.", options), picked
        )

    def demo_action(self, frontend) -> None:
        """Stop this frontend's running demo, or choose a source and launch one."""
        slot = f"demo-{frontend}"
        if self._slot_running(slot):
            self.terminate(slot)
            return
        if not component_installed(frontend):
            self.notify(f"{frontend} is not installed; use Install component first.")
            return
        options = sorted(
            (
                (f"{name}  {'installed' if component_installed(name) else 'missing'}", name)
                for name in BACKENDS
            ),
            key=lambda item: item[1] != "rust",  # Rust first: the CLI's default source
        )

        def picked(backend):
            if backend:
                self.start_demo(frontend, backend)

        self.push_screen(ChooseScreen(f"Source for the {frontend} demo?", options), picked)

    def start_demo(self, frontend, backend) -> None:
        """Each demo gets its own slot and tab, so several can run against one source."""
        self.run_worker(
            self._launch(
                f"demo-{frontend}",
                _cli("demo", frontend, "--backend", backend),
                f"demo {frontend} ({backend})",
            )
        )

    # -- process management ---------------------------------------------------
    def _slot_running(self, slot) -> bool:
        proc = self.procs.get(slot)
        return proc is not None and proc.returncode is None

    async def _launch(self, slot, argv, label) -> None:
        if self._slot_running(slot):
            self.notify(f"{label} is already running.")
            return
        tabs = self.query_one("#tabs", TabbedContent)
        pane_id, log_id = f"pane-{slot}", f"log-{slot}"
        if pane_id not in self._panes:
            log = RichLog(id=log_id, markup=False, highlight=False, wrap=True)
            await tabs.add_pane(TabPane(label, log, id=pane_id))
            self._panes.add(pane_id)
        else:
            log = self.query_one(f"#{log_id}", RichLog)
            log.clear()
        tabs.active = pane_id
        self._set_button(slot, running=True)
        self._set_tab(slot, label, "live")
        log.write(f"$ {' '.join(str(part) for part in argv)}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            log.write(f"Failed to start: {exc}")
            self._set_button(slot, running=False)
            self._set_tab(slot, label, "failed")
            return
        self.procs[slot] = proc
        assert proc.stdout is not None
        async for raw in proc.stdout:
            log.write(raw.decode(errors="replace").rstrip())
        code = await proc.wait()
        log.write(f"[exited with code {code}]")
        self.procs[slot] = None
        self._set_button(slot, running=False)
        self._set_tab(slot, label, "done" if code == 0 else "failed")
        if slot == "install":
            self.refresh_env()

    def terminate(self, slot) -> None:
        proc = self.procs.get(slot)
        if proc is None or proc.returncode is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass

    def action_stop(self) -> None:
        active = self.query_one("#tabs", TabbedContent).active
        if active.startswith("pane-"):
            self.terminate(active[len("pane-") :])

    def on_unmount(self) -> None:
        for proc in self.procs.values():
            if proc is not None and proc.returncode is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass

    # -- helpers --------------------------------------------------------------
    def _set_button(self, slot, running) -> None:
        if slot not in SLOTS:  # demos have no toggle button; each lives in its own tab
            return
        button = self.query_one(f"#{slot}", Button)
        button.label = SLOTS[slot][1 if running else 0]
        button.variant = "error" if running else "default"

    def _set_tab(self, slot, label, state) -> None:
        self.query_one("#tabs", TabbedContent).get_tab(
            f"pane-{slot}"
        ).label = f"{label}  {STATE_MARK[state]}"


def run_tui() -> None:
    if not sys.stdout.isatty():
        raise RuntimeError("plotbench tui requires an interactive terminal")
    PlotbenchTUI().run()
