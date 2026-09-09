"""Interactive launcher (Textual): inspect environments and launch sources,
component setup, benchmark suites and the matrix editor from one place.

The TUI orchestrates the same commands you would run by hand: `./scripts/setup`
for installs and `python -m plotbench.cli ...` for everything else. It therefore
expects a repository checkout; component installs are disabled when `scripts/`
is absent. It never measures anything itself.
"""

import asyncio
import os
import signal
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, OptionList, RichLog, Static
from textual.widgets.option_list import Option

from .backends import BACKENDS
from .runtime import component_installed, setup_component
from .suites import FRONTENDS

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts" / "setup"
SCENARIOS = ROOT / "scenarios"
CUSTOM = ROOT / "scenarios_custom"
# The components `./scripts/setup` can install, in a sensible offer order.
INSTALLABLE = ["rust", "pyqtgraph", "matplotlib", "qtgraphs", "qtgraphs-cpp", "iced", "plotly"]


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
    #env { height: auto; max-height: 50%; margin-bottom: 1; }
    #running { color: $text-muted; margin-bottom: 1; }
    #log { height: 1fr; border: solid $panel; background: $surface; padding: 0 1; }
    .spacer { height: 1fr; }
    ChooseScreen { align: center middle; }
    #dialog { width: 70; height: auto; max-height: 80%; padding: 1 2; background: $surface; border: solid $accent; }
    #dialog-title { text-style: bold; margin-bottom: 1; }
    #dialog-options { height: auto; max-height: 20; margin-bottom: 1; }
    """
    BINDINGS = [("q", "quit", "Quit"), ("r", "refresh", "Refresh"), ("x", "stop", "Stop process")]

    def __init__(self):
        super().__init__()
        self.proc = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("Actions", classes="section-title")
                yield Button("Launch Rust source", id="rust")
                yield Button("Launch Python source", id="python")
                yield Button("Install component", id="install")
                yield Button("Run a suite", id="run")
                yield Button("Matrix editor", id="matrix")
                yield Static("", classes="spacer")
                yield Button("Refresh", id="refresh")
                yield Button("Stop process", id="stop", variant="error")
            with Vertical(id="main"):
                yield Static("Environments", classes="section-title")
                yield DataTable(id="env", cursor_type="row", zebra_stripes=True)
                yield Static("Idle.", id="running")
                yield RichLog(id="log", markup=False, highlight=False, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#env", DataTable)
        table.add_columns("Component", "Type", "Installed", "Install with")
        if not SCRIPTS.exists():
            self.query_one("#install", Button).disabled = True
        self.refresh_env()
        if not SCRIPTS.exists():
            self.log_write("scripts/setup not found — component installs are disabled.")
        self.log_write("Ready. Choose an action on the left; press x to stop a running process.")

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
        self.log_write("Environments refreshed.")

    # -- actions --------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "rust": lambda: self.start(_cli("serve", "--backend", "rust"), "Rust source"),
            "python": lambda: self.start(_cli("serve", "--backend", "python"), "Python source"),
            "matrix": lambda: self.start(_cli("matrix"), "Matrix editor"),
            "install": self.choose_install,
            "run": self.choose_run,
            "refresh": self.action_refresh,
            "stop": self.action_stop,
        }
        handler = actions.get(event.button.id)
        if handler:
            handler()

    def choose_install(self) -> None:
        if not SCRIPTS.exists():
            self.notify("scripts/setup not found; run the TUI from a repository checkout.")
            return
        options = [
            (f"{name}  {'installed' if component_installed(name) else 'missing'}", name)
            for name in INSTALLABLE
        ]

        def installed(value):
            if value:
                self.start(["./scripts/setup", value], f"setup {value}")

        self.push_screen(ChooseScreen("Install or rebuild which component?", options), installed)

    def choose_run(self) -> None:
        suites = []
        for directory, tag in ((SCENARIOS, "scenarios"), (CUSTOM, "scenarios_custom")):
            if directory.is_dir():
                for path in sorted(directory.glob("*.json")):
                    suites.append((f"{tag}/{path.name}", f"{tag}/{path.name}"))
        if not suites:
            self.notify("No suites found in scenarios/ or scenarios_custom/.")
            return

        def chosen(value):
            if value:
                self.start(_cli("run", "--suite", value), f"run {value}")

        self.push_screen(ChooseScreen("Run which suite?", suites), chosen)

    # -- process management ---------------------------------------------------
    def start(self, argv, label) -> None:
        if self.proc is not None and self.proc.returncode is None:
            self.notify(
                "A process is already running — press x to stop it first.", severity="warning"
            )
            return
        self.run_worker(self._run(argv, label), exclusive=False)

    async def _run(self, argv, label) -> None:
        self.log_write(f"$ {' '.join(str(part) for part in argv)}")
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            self.log_write(f"Failed to start {label}: {exc}")
            self.proc = None
            return
        self.set_running(f"running: {label}  (pid {self.proc.pid}) — press x to stop")
        assert self.proc.stdout is not None
        async for raw in self.proc.stdout:
            self.log_write(raw.decode(errors="replace").rstrip())
        code = await self.proc.wait()
        self.log_write(f"[{label}] exited with code {code}.")
        self.proc = None
        self.set_running("Idle.")
        self.refresh_env()

    def action_stop(self) -> None:
        self._terminate()

    def _terminate(self) -> bool:
        if self.proc is None or self.proc.returncode is not None:
            self.notify("No process is running.")
            return False
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
            self.log_write("Sent SIGTERM to the running process.")
        except (ProcessLookupError, OSError) as exc:
            self.log_write(f"Could not stop the process: {exc}")
        return True

    def on_unmount(self) -> None:
        if self.proc is not None and self.proc.returncode is None:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass

    # -- helpers --------------------------------------------------------------
    def set_running(self, text) -> None:
        self.query_one("#running", Static).update(text)

    def log_write(self, text) -> None:
        self.query_one("#log", RichLog).write(text)


def run_tui() -> None:
    if not sys.stdout.isatty():
        raise RuntimeError("plotbench tui requires an interactive terminal")
    PlotbenchTUI().run()
