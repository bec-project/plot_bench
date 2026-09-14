"""Real HTTP/WebSocket contract checks using an ephemeral local server."""

import asyncio
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from plotbench.config import Config
from plotbench.protocol import decode_frame, decode_replay
from plotbench.server import Server


def test_service_config_stream_replay_and_atomic_metrics(tmp_path):
    async def exercise():
        source = Server(Config(points=32, append_count=4, width=7, height=5, hz=120), tmp_path)
        async with TestClient(TestServer(source.app())) as client:
            response = await client.post("/api/config", json={"hz": 130})
            assert response.status == 400
            assert source.config.hz == 120
            response = await client.post(
                "/api/config", json={"image_mode": "rgb", "waveform_mode": "append"}
            )
            assert response.status == 200
            assert (await response.json())["generation"] == 1
            async with client.ws_connect("/ws") as ws:
                frame = decode_frame((await ws.receive(timeout=2)).data)
                assert frame.arrays["image"].shape == (1, 5, 7, 3)
                assert frame.header["version"] == 2
                assert frame.generation == 1
                with pytest.raises(TimeoutError):
                    await ws.receive(timeout=0.05)
                await ws.send_json({"ack": frame.seq, "generation": frame.generation})
                newer = decode_frame((await ws.receive(timeout=2)).data)
                assert newer.seq > frame.seq + 1
            response = await client.get("/api/replay?count=3")
            frames = decode_replay(await response.read())
            assert [frame.seq for frame in frames] == [0, 1, 2]
            sample = dict(
                seq=0,
                generation=1,
                skipped=0,
                client_time_ms=1000,
                update_ms=2,
                receive_age_ms=-0.1,
            )
            batch = dict(frontend="test", mode="stream", run_id="test", samples=[sample])
            response = await client.post("/api/metrics", json=batch)
            assert response.status == 200
            batch["samples"].append(dict(sample, update_ms=-2))
            response = await client.post("/api/metrics", json=batch)
            assert response.status == 400
            lines = (tmp_path / "measurements.jsonl").read_text().splitlines()
            assert len(lines) == 1
            assert json.loads(lines[0])["samples"][0]["receive_age_ms"] == -0.1

    asyncio.run(exercise())


@pytest.mark.parametrize("args", [["--duration", "nan"], ["--duration", "-1"], ["--width", "0"]])
def test_frontend_parser_rejects_invalid_timing_and_dimensions(args):
    from plotbench.client import frontend_parser

    with pytest.raises(SystemExit):
        frontend_parser("test").parse_args(args)
