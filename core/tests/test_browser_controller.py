import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from plotbench.browser_controller import BrowserController
from plotbench.browser_worker import BrowserCompletion, run_unobserved_page


class FakeInput:
    def __init__(self, on_write=None):
        self.writes = []
        self.on_write = on_write

    def write(self, data):
        self.writes.append(json.loads(data))
        if self.on_write:
            self.on_write(self.writes[-1])

    async def drain(self):
        pass


class FakeProcess:
    def __init__(self):
        self.stdout = asyncio.StreamReader()
        self.stdin = FakeInput()
        self.returncode = None
        self.killed = False
        self.exited = asyncio.Event()

    def emit(self, message):
        self.stdout.feed_data((json.dumps(message) + "\n").encode())

    def exit(self, code=0):
        self.returncode = code
        self.stdout.feed_eof()
        self.exited.set()

    def kill(self):
        self.killed = True
        self.exit(-9)

    async def wait(self):
        await self.exited.wait()
        return self.returncode


def notification(event, **changes):
    return {
        "event": event,
        "state": {
            "submitted": 12,
            "running": event == "started",
            "complete": event == "stopped",
            "stop_reason": "duration" if event == "stopped" else None,
            **changes,
        },
    }


async def finish_reader(controller):
    controller.closing = True
    controller.process.stdout.feed_eof()
    await controller.reader


def test_unexpected_eof_fails_completion_and_outstanding_command():
    async def check():
        process = FakeProcess()
        completion = BrowserCompletion(1)
        controller = BrowserController(process, completion, {})
        request = asyncio.create_task(controller.call("screenshot", path="/tmp/final.png"))
        await asyncio.sleep(0)
        process.exit(1)
        with pytest.raises(RuntimeError, match="exited before closing"):
            await request
        with pytest.raises(RuntimeError, match="exited before closing"):
            await completion.wait()
        assert controller.pending == {}
        await controller.reader

    asyncio.run(check())


@pytest.mark.parametrize(
    "wire, expected",
    [
        (b"not-json\n", "Invalid browser controller output"),
        (b'{"event":"mystery"}\n', "Unknown browser controller event"),
        (b'{"event":"ready","metadata":null}\n', "Invalid browser controller output"),
    ],
)
def test_invalid_protocol_is_a_completion_error(wire, expected):
    async def check():
        process = FakeProcess()
        completion = BrowserCompletion(1)
        controller = BrowserController(process, completion, {})
        process.stdout.feed_data(wire)
        await controller.reader
        with pytest.raises(RuntimeError, match=expected):
            await completion.wait()

    asyncio.run(check())


def test_command_after_reader_failure_rejects_without_waiting_for_unread_reply():
    async def check():
        process = FakeProcess()
        controller = BrowserController(process, BrowserCompletion(1), {})
        process.stdout.feed_data(b"invalid-json\n")
        await controller.reader
        # The process may still be alive with writable stdin; no reader remains
        # to acknowledge close. Cleanup must not wait for the 30 second call timeout.
        with pytest.raises(RuntimeError, match="controller"):
            await asyncio.wait_for(controller.call("close"), timeout=0.1)
        assert not process.stdin.writes

    asyncio.run(check())


def test_ready_metadata_and_lifecycle_errors_are_forwarded():
    async def check():
        process = FakeProcess()
        completion = BrowserCompletion(1)
        metadata = {}
        controller = BrowserController(process, completion, metadata)
        process.emit(
            {"event": "ready", "metadata": {"browser_network_instrumentation": "disabled"}}
        )
        process.emit({"event": "lifecycle", "message": notification("started")})
        process.emit(
            {
                "event": "lifecycle",
                "message": notification("stopped", metrics_error="metrics export failed"),
            }
        )
        with pytest.raises(RuntimeError, match="metrics export failed"):
            await completion.wait()
        assert metadata["browser_network_instrumentation"] == "disabled"
        await finish_reader(controller)

    asyncio.run(check())


def test_immediate_reply_error_is_not_lost_and_pending_call_is_removed():
    async def check():
        process = FakeProcess()
        completion = BrowserCompletion(1)
        controller = BrowserController(process, completion, {})

        def reply(command):
            process.emit({"event": "reply", "id": command["id"], "error": "capture failed"})
            process.emit({"event": "error", "error": "capture failed"})

        process.stdin.on_write = reply
        with pytest.raises(RuntimeError, match="capture failed"):
            await controller.call("screenshot", path="/tmp/final.png")
        assert controller.pending == {}
        with pytest.raises(RuntimeError, match="capture failed"):
            await completion.wait()
        await finish_reader(controller)

    asyncio.run(check())


def test_close_acknowledgement_and_process_exit_cleanup():
    async def check():
        process = FakeProcess()
        controller = BrowserController(process, BrowserCompletion(1), {})

        def reply(command):
            assert command["command"] == "close"
            process.emit({"event": "reply", "id": command["id"]})
            process.exit()

        process.stdin.on_write = reply
        await controller.close()
        assert process.returncode == 0
        assert not process.killed
        assert controller.reader.done()

    asyncio.run(check())


@pytest.mark.parametrize("failure", [None, "renderer crashed"])
def test_unobserved_page_maps_options_and_captures_only_after_completion(monkeypatch, failure):
    async def check():
        started = asyncio.Event()
        commands = []
        holder = {}

        class Controller:
            async def send(self, command, **payload):
                commands.append((command, payload))
                holder["completion"].notify(notification("started"))
                started.set()

            async def call(self, command, **payload):
                assert holder["completion"].finished.is_set()
                commands.append((command, payload))

            async def close(self):
                commands.append(("close", {}))

        async def launch(completion, metadata):
            holder["completion"] = completion
            metadata["browser_network_instrumentation"] = "disabled"
            return Controller()

        monkeypatch.setattr(
            "plotbench.browser_worker.BrowserController", SimpleNamespace(launch=launch)
        )
        args = SimpleNamespace(
            duration=1, width=1100, height=820, screenshot=Path("/tmp/final.png")
        )
        options = {"executable_path": "/custom/chromium", "headless": False, "args": ["--test-arg"]}
        metadata = {"qa_screenshot": False}
        run = asyncio.create_task(
            run_unobserved_page(args, "http://localhost/page", options, metadata)
        )
        await started.wait()
        await asyncio.sleep(0)
        assert [command for command, _ in commands] == ["start"]
        assert commands[0][1] == {
            "options": {
                "executablePath": "/custom/chromium",
                "headless": False,
                "args": ["--test-arg"],
            },
            "width": 1100,
            "height": 820,
            "url": "http://localhost/page",
        }
        assert "executable_path" in options, "caller options must remain intact"
        if failure:
            holder["completion"].fail(failure)
            with pytest.raises(RuntimeError, match=failure):
                await run
            assert [command for command, _ in commands] == ["start", "close"]
            assert metadata["qa_screenshot"] is False
        else:
            holder["completion"].notify(notification("stopped"))
            await run
            assert [command for command, _ in commands] == ["start", "screenshot", "close"]
            assert metadata["qa_screenshot"] is True
            assert metadata["termination_reason"] == "duration"

    asyncio.run(check())
