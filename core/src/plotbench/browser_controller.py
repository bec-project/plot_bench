"""Small lifecycle-only pipe to the in-process Playwright browser controller."""

import asyncio
import json
from contextlib import suppress
from pathlib import Path


class BrowserController:
    def __init__(self, process, completion, metadata):
        self.process = process
        self.completion = completion
        self.metadata = metadata
        self.pending = {}
        self.next_id = 1
        self.closing = False
        self.reader_error = None
        self.reader = asyncio.create_task(self.read_events())

    @classmethod
    async def launch(cls, completion, metadata):
        import playwright

        driver = Path(playwright.__file__).parent / "driver"
        process = await asyncio.create_subprocess_exec(
            str(driver / "node"),
            str(Path(__file__).with_name("browser_driver.cjs")),
            str(driver / "package"),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        return cls(process, completion, metadata)

    async def read_events(self):
        error = "Browser controller exited before closing was requested"
        try:
            async for line in self.process.stdout:
                message = json.loads(line)
                event = message["event"]
                if event == "ready":
                    self.metadata.update(message["metadata"])
                elif event == "lifecycle":
                    self.completion.notify(message["message"])
                elif event == "error":
                    self.completion.fail(message["error"])
                elif event == "closed":
                    self.completion.closed()
                elif event == "reply":
                    future = self.pending.get(message.get("id"))
                    if future is not None and not future.done():
                        if message.get("error"):
                            future.set_exception(RuntimeError(message["error"]))
                        else:
                            future.set_result(None)
                else:
                    raise ValueError(f"Unknown browser controller event: {event}")
        except Exception as exc:
            error = f"Invalid browser controller output: {exc}"
            self.completion.fail(error)
        finally:
            self.reader_error = error
            if not self.closing:
                self.completion.fail(error)
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(RuntimeError(error))

    async def send(self, command, **payload):
        if self.reader.done():
            raise RuntimeError(self.reader_error or "Browser controller reader stopped")
        identifier = self.next_id
        self.next_id += 1
        self.process.stdin.write(
            (json.dumps(dict(id=identifier, command=command, **payload)) + "\n").encode()
        )
        await self.process.stdin.drain()
        return identifier

    async def call(self, command, **payload):
        # Register before writing so even an immediate reply cannot be lost.
        identifier = self.next_id
        future = asyncio.get_running_loop().create_future()
        self.pending[identifier] = future
        try:
            await self.send(command, **payload)
            await asyncio.wait_for(future, timeout=30)
        finally:
            self.pending.pop(identifier, None)
            future.cancel()

    async def close(self):
        self.closing = True
        try:
            await self.call("close")
            await asyncio.wait_for(self.process.wait(), timeout=10)
            if self.process.returncode:
                raise RuntimeError(f"Browser controller exited with code {self.process.returncode}")
        finally:
            if self.process.returncode is None:
                self.process.kill()
                await self.process.wait()
            self.reader.cancel()
            with suppress(asyncio.CancelledError):
                await self.reader
