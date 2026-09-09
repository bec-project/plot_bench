import struct

import numpy as np
import pytest

from plotbench.config import Config
from plotbench.generator import generate_arrays, make_packet
from plotbench.protocol import decode_frame, decode_replay, encode_frame


def test_timestamp_follows_payload_copy_without_later_payload_mutation(monkeypatch):
    array = np.array([1, 2, 3], dtype=np.float32)

    def after_payload():
        array[:] = 99
        return 123_000_000

    monkeypatch.setattr("plotbench.protocol.time.time_ns", after_payload)
    packet = encode_frame({"seq": 1, "generation": 0}, {"waveform": array}, stamp_emitted_at=True)
    assert packet.readonly
    frame = decode_frame(packet)
    np.testing.assert_array_equal(frame.arrays["waveform"], [1, 2, 3])
    assert frame.header["emitted_at_ms"] == 123
    assert not frame.arrays["waveform"].flags.writeable
    header_size = struct.unpack_from("<I", packet)[0]
    assert ((header_size + 7) & ~3) + 12 == len(packet)


def test_packet_buffer_is_accepted_by_http_payload_without_a_server():
    import asyncio
    from types import SimpleNamespace

    from aiohttp import web

    packet = make_packet(Config(view="waveform", points=8, append_count=1), 0)
    response = web.Response(body=packet, content_type="application/octet-stream")
    written = []

    async def write(data):
        written.append(bytes(data))

    assert response.body.size == len(packet)
    asyncio.run(response.body.write(SimpleNamespace(write=write)))
    assert b"".join(written) == bytes(packet)


def test_oversized_header_is_rejected_without_truncating_payload():
    with pytest.raises(ValueError, match="header exceeds"):
        encode_frame(
            {"seq": 0, "generation": 0, "extra": "x" * 4096},
            {"waveform": np.zeros(2, dtype=np.float32)},
        )


@pytest.mark.parametrize("points", [8, 32768])
def test_readonly_packet_passes_actual_websocket_writer_without_a_socket(points):
    import asyncio
    from types import SimpleNamespace

    from aiohttp import WSMsgType
    from aiohttp._websocket.writer import WebSocketWriter

    packet = make_packet(Config(view="waveform", points=points, append_count=1), 0)
    writes = []

    async def send():
        transport = SimpleNamespace(
            is_closing=lambda: False, write=lambda data: writes.append(bytes(data))
        )
        writer = WebSocketWriter(SimpleNamespace(_paused=False), transport)
        await writer.send_frame(packet, WSMsgType.BINARY)

    asyncio.run(send())
    wire = b"".join(writes)
    length_code = wire[1] & 127
    payload_offset = 10 if length_code == 127 else 4 if length_code == 126 else 2
    assert wire[payload_offset:] == bytes(packet)
    assert decode_frame(wire[payload_offset:]).arrays["waveform"].size == points


@pytest.mark.parametrize("view", ["waveform", "image", "both"])
@pytest.mark.parametrize("image_mode", ["rgb", "scalar"])
def test_binary_roundtrip_preserves_every_value(view, image_mode):
    config = Config(points=13, append_count=3, width=5, height=7, view=view, image_mode=image_mode)
    frame = decode_frame(make_packet(config, 7))
    assert frame.seq == 7
    for name, expected in generate_arrays(config, 7).items():
        np.testing.assert_array_equal(frame.arrays[name], expected)
        assert not frame.arrays[name].flags.writeable


def test_append_windows_preserve_overlap_and_advance_exactly():
    config = Config(points=100, append_count=13, view="waveform", waveform_mode="append")
    before = generate_arrays(config, 41)["waveform"]
    after = generate_arrays(config, 42)["waveform"]
    np.testing.assert_array_equal(before[13:], after[:-13])
    assert not np.array_equal(before, after)


def test_replay_container_and_corruption():
    packets = [
        make_packet(Config(points=7, append_count=1, width=3, height=2), i) for i in range(2)
    ]
    replay = struct.pack("<I", 2) + b"".join(struct.pack("<I", len(p)) + bytes(p) for p in packets)
    assert [f.seq for f in decode_replay(replay)] == [0, 1]
    with pytest.raises(ValueError):
        decode_replay(replay[:-1])
    with pytest.raises(ValueError):
        decode_frame(packets[0][:-1])
    with pytest.raises(ValueError):
        decode_frame(bytes(packets[0]) + b"unexpected")


@pytest.mark.parametrize(
    "changes",
    [
        {"hz": 121},
        {"hz": float("nan")},
        {"hz": True},
        {"points": 0},
        {"width": 1.1},
        {"append_count": 20000},
        {"view": "bad"},
        {"generation": 1},
    ],
)
def test_invalid_configuration_is_rejected(changes):
    with pytest.raises(ValueError):
        Config().updated(changes)


def test_config_updates_are_atomic_and_advance_generation():
    before = Config()
    after = before.updated({"hz": 120, "width": 2048})
    assert before.hz == 30
    assert after.generation == before.generation + 1
    assert after.payload_bytes == 10000 * 4 + 2048 * 512 * 4
