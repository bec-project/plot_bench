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
import time
from pathlib import Path

import psutil
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
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
from .suites import BASELINE_SUITE, FRONTENDS

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts" / "setup"
SCENARIOS = ROOT / "scenarios"
CUSTOM = ROOT / "scenarios_custom"
INSTALLABLE = [
    "rust",
    "pyqtgraph",
    "matplotlib",
    "qtgraphs",
    "qtgraphs-cpp",
    "iced",
    "fyne",
    "jfreechart",
    "plotly",
]

# Each launch slot: sidebar button labels for idle and running states.
SLOTS = {
    "rust": ("Launch Rust source", "Stop Rust source"),
    "python": ("Launch Python source", "Stop Python source"),
    "install": ("Install component", "Stop install"),
    "run": ("Run a suite", "Stop suite"),
    "matrix": ("Matrix editor", "Stop matrix editor"),
}
STATE_MARK = {
    "live": "● live",
    "stopping": "◐ stopping",
    "done": "○ done",
    "stopped": "○ stopped",
    "failed": "✗ failed",
}
# Command-line markers of plotbench processes launched from this checkout.
MARKERS = (
    "plotbench-source-rust",
    "plotbench-iced",
    "plotbench-fyne",
    "plotbench-jfreechart.jar",
    "plotbench-qtgraphs-cpp",
    "/bin/plotbench-",
    "plotbench.cli",
    "plotbench.browser_worker",
)
STOP_GRACE = 8.0  # seconds after the Ctrl+C-style SIGINT before escalating
QUIT_GRACE = 3.0  # shorter on quit so exiting never hangs for long
KILL_GRACE = 3.0
# Leftover detection only considers processes launched from this checkout.
SCOPE = str(ROOT)


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
    #env { height: auto; max-height: 35%; margin-bottom: 1; }
    #running { height: auto; max-height: 30%; margin-bottom: 1; }
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
        self.labels = {}
        self.started = {}
        self.stopping = set()
        self.leftovers = []
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
                yield Button("Stop all", id="stopall", variant="error")
                yield Button("Stop leftovers", id="leftovers", variant="error", disabled=True)
                yield Button("Refresh", id="refresh")
            with Vertical(id="main"):
                yield Static("Environments", classes="section-title")
                yield DataTable(id="env", cursor_type="row", zebra_stripes=True)
                yield Static("Running", classes="section-title")
                yield DataTable(id="running", cursor_type="none")
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
        self.query_one("#running", DataTable).add_columns(
            "Process", "PID", "Owner", "Uptime", "Children"
        )
        self.refresh_running()
        if self.leftovers:
            self.notify(
                f"{len(self.leftovers)} plotbench process(es) from an earlier session are "
                "still running — use Stop leftovers.",
                severity="warning",
                timeout=10,
            )
        self.set_interval(2.0, self.refresh_running)

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
        elif slot == "stopall":
            self.stop_all()
        elif slot == "leftovers":
            self.stop_leftovers()
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
                    value = f"{tag}/{path.name}"
                    if value == BASELINE_SUITE:
                        # The official suite is pinned first so it is the obvious choice.
                        suites.insert(0, (f"{value}  (official baseline)", value))
                    else:
                        suites.append((value, value))
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
        self.labels[slot] = label
        self.stopping.discard(slot)
        self._set_button(slot, running=True)
        self._set_tab(slot, "live")
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
            self._set_tab(slot, "failed")
            return
        self.procs[slot] = proc
        self.started[slot] = time.monotonic()
        self.refresh_running()
        assert proc.stdout is not None
        async for raw in proc.stdout:
            log.write(raw.decode(errors="replace").rstrip())
        code = await proc.wait()
        log.write(f"[exited with code {code}]")
        self.procs[slot] = None
        self._set_button(slot, running=False)
        if slot in self.stopping:
            self._set_tab(slot, "stopped")
        else:
            self._set_tab(slot, "done" if code == 0 else "failed")
        self.stopping.discard(slot)
        self.refresh_running()
        if slot == "install":
            self.refresh_env()

    # Every stop works on the whole process tree, snapshotted before the first
    # signal: a demo or a suite run spawns its source and frontend in their own
    # sessions, so signalling only the direct child would orphan them. Ctrl+C
    # semantics come first (SIGINT lets a run finalize its report and a demo stop
    # what it started), then SIGTERM, then SIGKILL for anything still alive.
    @staticmethod
    def _tree(pid):
        try:
            root = psutil.Process(pid)
            return [root, *root.children(recursive=True)]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return []

    @staticmethod
    def _stop_trees_blocking(pids, first_grace, grace) -> None:
        alive = [proc for pid in pids for proc in PlotbenchTUI._tree(pid)]
        for sig, wait in ((signal.SIGINT, first_grace), (signal.SIGTERM, grace)):
            if not alive:
                return
            for proc in alive:
                try:
                    proc.send_signal(sig)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            _, alive = psutil.wait_procs(alive, timeout=wait)
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        psutil.wait_procs(alive, timeout=grace)

    def terminate(self, slot) -> None:
        proc = self.procs.get(slot)
        if proc is None or proc.returncode is not None:
            return
        self.stopping.add(slot)
        self._set_tab(slot, "stopping")
        self.run_worker(
            asyncio.to_thread(self._stop_trees_blocking, [proc.pid], STOP_GRACE, KILL_GRACE),
            exclusive=False,
        )

    def stop_all(self) -> None:
        for slot in list(self.procs):
            self.terminate(slot)

    def stop_leftovers(self) -> None:
        pids = [proc.pid for proc in self.leftovers]
        if not pids:
            return

        async def stop():
            await asyncio.to_thread(self._stop_trees_blocking, pids, QUIT_GRACE, KILL_GRACE)
            self.refresh_running()

        self.run_worker(stop(), exclusive=False)

    def action_stop(self) -> None:
        active = self.query_one("#tabs", TabbedContent).active
        if active.startswith("pane-"):
            self.terminate(active[len("pane-") :])

    def on_unmount(self) -> None:
        # Quitting must not leak anything: stop every owned tree, blocking briefly.
        pids = [
            proc.pid for proc in self.procs.values() if proc is not None and proc.returncode is None
        ]
        if pids:
            self._stop_trees_blocking(pids, QUIT_GRACE, KILL_GRACE)

    # -- running-process tracker ---------------------------------------------
    def refresh_running(self) -> None:
        try:
            table = self.query_one("#running", DataTable)
        except NoMatches:
            return
        table.clear()
        owned = set()
        for slot, proc in list(self.procs.items()):
            if proc is None or proc.returncode is not None:
                continue
            tree = self._tree(proc.pid)
            owned.update(member.pid for member in tree)
            children = ", ".join(sorted({self._describe(member) for member in tree[1:]})) or "—"
            uptime = _uptime(time.monotonic() - self.started.get(slot, time.monotonic()))
            table.add_row(self.labels.get(slot, slot), str(proc.pid), "this TUI", uptime, children)
        self.leftovers = self._find_leftovers(owned)
        for proc in self.leftovers:
            uptime = _uptime(time.time() - proc.create_time())
            table.add_row(self._describe(proc), str(proc.pid), "leftover", uptime, "—")
        button = self.query_one("#leftovers", Button)
        button.disabled = not self.leftovers
        button.label = (
            f"Stop leftovers ({len(self.leftovers)})" if self.leftovers else "Stop leftovers"
        )

    @staticmethod
    def _find_leftovers(owned):
        """Plotbench processes from this checkout that this TUI does not own."""
        found = []
        me = os.getpid()
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                pid = proc.info["pid"]
                cmdline = " ".join(proc.info["cmdline"] or [])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            if pid == me or pid in owned or SCOPE not in cmdline:
                continue
            if cmdline.rstrip().endswith("plotbench tui"):
                continue  # another TUI session owns and stops its own processes
            if any(marker in cmdline for marker in MARKERS):
                found.append(proc)
        return found

    @staticmethod
    def _describe(proc) -> str:
        try:
            cmdline = " ".join(proc.cmdline())
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return "?"
        if "plotbench-source-rust" in cmdline:
            return "rust source"
        if "plotbench.browser_worker" in cmdline:
            return "plotly frontend"
        if "plotbench.cli" in cmdline:
            tail = cmdline.split("plotbench.cli", 1)[1].split()
            return " ".join(tail[:2]) or "plotbench"
        for name in FRONTENDS:
            if f"plotbench-{name}" in cmdline:
                return f"{name} frontend"
        try:
            return proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return "?"

    # -- helpers --------------------------------------------------------------
    def _set_button(self, slot, running) -> None:
        if slot not in SLOTS:  # demos have no toggle button; each lives in its own tab
            return
        button = self.query_one(f"#{slot}", Button)
        button.label = SLOTS[slot][1 if running else 0]
        button.variant = "error" if running else "default"

    def _set_tab(self, slot, state) -> None:
        label = self.labels.get(slot, slot)
        self.query_one("#tabs", TabbedContent).get_tab(
            f"pane-{slot}"
        ).label = f"{label}  {STATE_MARK[state]}"


def _uptime(seconds) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def run_tui() -> None:
    if not sys.stdout.isatty():
        raise RuntimeError("plotbench tui requires an interactive terminal")
    PlotbenchTUI().run()
