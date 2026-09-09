"""Local source, bounded broadcast, replay, controls and raw measurement collector."""

import asyncio
import json
import math
import struct
import time
from contextlib import suppress
from pathlib import Path

import numpy as np
from aiohttp import web

from .generator import make_packet
from .host import host_snapshot
from .palette import COLORMAP
from .provenance import capture_provenance


@web.middleware
async def cors_and_errors(request, handler):
    try:
        response = web.Response() if request.method == "OPTIONS" else await handler(request)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        response = web.json_response({"error": str(exc)}, status=400)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


class Server:
    def __init__(self, config, output):
        self.config = config
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.clients = set()
        self.running = True
        self.generated = self.deadline_misses = self.mailbox_drops = 0
        self.acknowledged = 0
        self.error = None
        self._replay_lock = asyncio.Lock()
        self._raw = (self.output / "measurements.jsonl").open("a", buffering=1)
        self._source = (self.output / "source.jsonl").open("a", buffering=1)
        host = dict(
            host_snapshot(),
            backend="python",
            backend_runtime="aiohttp / NumPy",
            numpy=np.__version__,
            config=config.to_dict(),
            provenance=capture_provenance(),
            emitted_at_boundary="payload packed; before JSON header serialization/insertion",
            generation_boundary="thread dispatch, generation, packing and mailbox publication; excludes JSONL write",
            heartbeat_policy="20 seconds receive-idle then ping; 10 seconds response timeout; inbound activity resets",
            tcp_nodelay=True,
        )
        (self.output / "host.json").write_text(json.dumps(host, indent=2) + "\n")

    async def producer(self):
        generation, seq, deadline = self.config.generation, 0, time.perf_counter()
        while self.running:
            if not self.clients:
                await asyncio.sleep(0.025)
                deadline = time.perf_counter()
                continue
            config = self.config
            if config.generation != generation:
                generation, seq, deadline = config.generation, 0, time.perf_counter()
            started = time.perf_counter()
            try:
                packet = await asyncio.to_thread(make_packet, config, seq)
                self.error = None
            except Exception as exc:
                self.error = f"{type(exc).__name__}: {exc}"
                await asyncio.sleep(1)
                continue
            if self.config.generation != generation:
                continue
            self.generated += 1
            drops = 0
            for queue in tuple(self.clients):
                if queue.full():
                    queue.get_nowait()
                    drops += 1
                queue.put_nowait((packet, seq, generation))
            self.mailbox_drops += drops
            self._source.write(
                json.dumps(
                    dict(
                        time_ms=time.time_ns() / 1e6,
                        seq=seq,
                        generation=generation,
                        generation_ms=(time.perf_counter() - started) * 1000,
                        deadline_misses_total=self.deadline_misses,
                        acknowledgements_total=self.acknowledged,
                        clients=len(self.clients),
                        packet_bytes=len(packet),
                        mailbox_drops=drops,
                        target_hz=config.hz,
                    )
                )
                + "\n"
            )
            seq += 1
            deadline += 1 / config.hz
            now = time.perf_counter()
            if deadline < now:
                missed = int((now - deadline) * config.hz) + 1
                self.deadline_misses += missed
                seq += missed
                deadline += missed / config.hz
            await asyncio.sleep(max(0, deadline - time.perf_counter()))

    async def websocket(self, request):
        ws = web.WebSocketResponse(compress=False, heartbeat=20, max_msg_size=4096)
        await ws.prepare(request)
        queue = asyncio.Queue(maxsize=1)
        self.clients.add(queue)
        acknowledged = asyncio.Event()
        outstanding = None

        async def send():
            nonlocal outstanding
            while not ws.closed:
                packet, seq, generation = await queue.get()
                outstanding = (seq, generation)
                acknowledged.clear()
                await ws.send_bytes(packet)
                await acknowledged.wait()

        sender = asyncio.create_task(send())
        try:
            async for message in ws:
                if message.type == web.WSMsgType.TEXT:
                    try:
                        ack = json.loads(message.data)
                    except json.JSONDecodeError:
                        await ws.close(code=1003, message=b"Expected a JSON frame acknowledgement")
                        break
                    if (
                        isinstance(ack, dict)
                        and type(ack.get("ack")) is int
                        and type(ack.get("generation")) is int
                        and (ack.get("ack"), ack.get("generation")) == outstanding
                    ):
                        outstanding = None
                        self.acknowledged += 1
                        acknowledged.set()
        finally:
            self.clients.discard(queue)
            sender.cancel()
            with suppress(asyncio.CancelledError, ConnectionError):
                await sender
        return ws

    async def get_config(self, request):
        return web.json_response(self.config.to_dict())

    async def set_config(self, request):
        self.config = self.config.updated(await request.json())
        return web.json_response(self.config.to_dict())

    async def health(self, request):
        return web.json_response(
            dict(
                backend="python",
                backend_runtime="aiohttp / NumPy",
                status="ok" if self.error is None else "error",
                error=self.error,
                generated=self.generated,
                deadline_misses=self.deadline_misses,
                acknowledgements=self.acknowledged,
                mailbox_drops=self.mailbox_drops,
                clients=len(self.clients),
                output=str(self.output.resolve()),
                config=self.config.to_dict(),
            )
        )

    async def frame(self, request):
        seq = int(request.query.get("seq", 0))
        packet = await asyncio.to_thread(make_packet, self.config, seq)
        return web.Response(body=packet, content_type="application/octet-stream")

    async def replay(self, request):
        requested = int(request.query.get("count", 16))
        if not 2 <= requested <= 256:
            raise ValueError("replay count must be between 2 and 256")
        async with self._replay_lock:
            config = self.config
            count = min(requested, (256 * 1024 * 1024 - 4) // (config.payload_bytes + 4096))
            if count < 2:
                raise ValueError(
                    "replay needs at least two frames within 256 MiB; reduce the dimensions"
                )
            response = web.StreamResponse(
                headers={
                    "Content-Type": "application/octet-stream",
                    "Access-Control-Allow-Origin": "*",
                }
            )
            await response.prepare(request)
            await response.write(struct.pack("<I", count))
            for seq in range(count):
                packet = await asyncio.to_thread(make_packet, config, seq)
                await response.write(struct.pack("<I", len(packet)))
                await response.write(packet)
            await response.write_eof()
            return response

    async def metrics(self, request):
        batch = await request.json()
        for key in ("frontend", "run_id", "mode"):
            if not isinstance(batch.get(key), str) or not 1 <= len(batch[key]) <= 256:
                raise ValueError(f"invalid {key}")
        if batch["mode"] not in ("stream", "replay"):
            raise ValueError("unknown measurement mode")
        samples = batch.get("samples")
        if not isinstance(samples, list) or len(samples) > 20_000:
            raise ValueError("invalid sample batch")
        for sample in samples:
            for key in ("seq", "generation", "skipped"):
                if type(sample.get(key)) is not int or sample[key] < 0:
                    raise ValueError(f"invalid sample {key}")
            for key in ("client_time_ms", "update_ms"):
                if type(sample.get(key)) not in (int, float) or not math.isfinite(sample[key]):
                    raise ValueError(f"invalid sample {key}")
            if sample["update_ms"] < 0:
                raise ValueError("negative update duration")
            for key in (
                "receive_age_ms",
                "conversion_ms",
                "draw_ms",
                "update_complete_ms",
                "image_upload_wait_ms",
            ):
                value = sample.get(key)
                if value is not None and (
                    type(value) not in (int, float)
                    or not math.isfinite(value)
                    or (key != "receive_age_ms" and value < 0)
                ):
                    raise ValueError(f"invalid sample {key}")
        # Validate the complete batch before any durable write.
        batch["received_at_ms"] = time.time_ns() / 1e6
        self._raw.write(json.dumps(batch, allow_nan=False) + "\n")
        return web.json_response({"accepted": len(samples)})

    async def controls(self, request):
        return web.FileResponse(Path(__file__).with_name("controls.html"))

    async def colormap(self, request):
        return web.json_response(COLORMAP.tolist())

    async def options(self, request):
        return web.Response()

    async def lifecycle(self, app):
        task = asyncio.create_task(self.producer())
        yield
        self.running = False
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        self._raw.close()
        self._source.close()

    def app(self):
        app = web.Application(middlewares=[cors_and_errors], client_max_size=32 * 1024 * 1024)
        app.add_routes(
            [
                web.get("/", self.controls),
                web.get("/ws", self.websocket),
                web.get("/api/config", self.get_config),
                web.post("/api/config", self.set_config),
                web.get("/api/health", self.health),
                web.get("/api/frame", self.frame),
                web.get("/api/replay", self.replay),
                web.post("/api/metrics", self.metrics),
                web.get("/api/colormap", self.colormap),
                web.options("/{tail:.*}", self.options),
            ]
        )
        app.cleanup_ctx.append(self.lifecycle)
        return app
