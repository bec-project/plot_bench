"""Exercise telemetry and source counters directly without binding a server."""

import asyncio
import io
import itertools
import json
from types import SimpleNamespace

import pytest

from plotbench.config import Config
from plotbench.server import Server


@pytest.mark.parametrize(
    "field", ["conversion_ms", "draw_ms", "update_complete_ms", "image_upload_wait_ms"]
)
@pytest.mark.parametrize("invalid", [-1, True, float("inf"), float("nan")])
def test_invalid_optional_timings_reject_whole_batch(field, invalid):
    sample = dict(seq=0, generation=0, skipped=0, client_time_ms=1, update_ms=0.1)
    batch = dict(
        frontend="test",
        run_id="test",
        mode="stream",
        samples=[sample, dict(sample, **{field: invalid})],
    )
    output = io.StringIO()

    async def read():
        return batch

    with pytest.raises(ValueError, match=field):
        asyncio.run(Server.metrics(SimpleNamespace(_raw=output), SimpleNamespace(json=read)))
    assert output.getvalue() == ""


def test_completion_metrics_and_negative_receive_age_are_preserved():
    sample = dict(
        seq=0,
        generation=0,
        skipped=0,
        client_time_ms=1,
        update_ms=0.1,
        update_complete_ms=2,
        image_upload_wait_ms=1.9,
        draw_ms=None,
        receive_age_ms=-0.2,
    )
    batch = dict(frontend="test", run_id="test", mode="stream", samples=[sample])
    output = io.StringIO()

    async def read():
        return batch

    response = asyncio.run(Server.metrics(SimpleNamespace(_raw=output), SimpleNamespace(json=read)))
    assert response.status == 200
    assert json.loads(output.getvalue())["samples"][0] == sample


def test_source_persists_missed_deadline_and_ack_counters(monkeypatch):
    source = SimpleNamespace(
        config=Config(view="waveform", points=8, append_count=1, hz=60),
        running=True,
        clients={asyncio.Queue(maxsize=1)},
        generated=0,
        deadline_misses=0,
        mailbox_drops=0,
        acknowledged=7,
        error=None,
    )

    class Output(io.StringIO):
        def write(self, value):
            result = super().write(value)
            if self.getvalue().count("\n") == 2:
                source.running = False
            return result

    source._source = Output()
    clock = itertools.count(0, 0.1)
    monkeypatch.setattr("plotbench.server.time.perf_counter", lambda: next(clock))
    monkeypatch.setattr("plotbench.server.make_packet", lambda *args: b"packet")
    asyncio.run(Server.producer(source))
    rows = [json.loads(line) for line in source._source.getvalue().splitlines()]
    assert len(rows) == 2 and rows[0]["deadline_misses_total"] == 0
    assert rows[1]["deadline_misses_total"] > 0
    assert all(row["clients"] == 1 and row["acknowledgements_total"] == 7 for row in rows)
