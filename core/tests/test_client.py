import struct
import time

from plotbench.client import FrameSource, MetricsSink
from plotbench.config import Config
from plotbench.generator import make_packet
from plotbench.protocol import decode_frame


def test_replay_has_no_network_work_after_preload(monkeypatch):
    packets = [
        make_packet(Config(hz=120, view="waveform", points=10, append_count=1), n) for n in range(2)
    ]
    payload = struct.pack("<I", 2) + b"".join(struct.pack("<I", len(p)) + bytes(p) for p in packets)
    calls = []

    def fake_request(url, **kwargs):
        calls.append(url)
        return payload

    monkeypatch.setattr("plotbench.client.request", fake_request)
    source = FrameSource("http://127.0.0.1:8765", "replay")
    source.start()
    try:
        deadline = time.monotonic() + 1.2
        seen = set()
        while time.monotonic() < deadline:
            frame = source.take_latest()
            if frame:
                seen.add(frame.seq)
            time.sleep(0.005)
        assert len(seen) > 10
        assert len(calls) == 1
    finally:
        source.close()


def test_final_metadata_is_sent_without_pending_samples(monkeypatch):
    batches = []
    monkeypatch.setattr(
        "plotbench.client.request", lambda url, data, **kwargs: batches.append(data)
    )
    sink = MetricsSink("http://localhost", "test", "stream", "test", expected_duration=1)
    frame = decode_frame(make_packet(Config(view="waveform"), 0))
    sink.record(frame, 1)
    sink._flush()
    sink.mark_stopped("duration")
    sink.mark_stopped("user")
    sink.close()
    assert batches[-1]["samples"] == []
    assert batches[-1]["metadata"]["termination_reason"] == "duration"
    assert not sink._thread.is_alive()


def test_recovered_stream_keeps_a_persistent_connection_epoch(monkeypatch):
    source = FrameSource("http://localhost", "stream")

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def recv(self, **kwargs):
            raise OSError("connection closed")

    monkeypatch.setattr("plotbench.client.connect", lambda *args, **kwargs: Connection())
    for expected in (1, 2):
        try:
            source._stream()
        except OSError:
            pass
        assert source.metadata["receiver_connection_epoch"] == expected
