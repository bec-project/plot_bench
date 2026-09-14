import json
import struct

import numpy as np
import pytest

from plotbench.config import Config
from plotbench.generator import generate_arrays, make_packet
from plotbench.palette import CURVE_COLORS
from plotbench.protocol import VERSION, decode_frame, decode_replay, encode_frame


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
@pytest.mark.parametrize("waveform_mode", ["replace", "append"])
@pytest.mark.parametrize("curves,waveform_plots,image_plots", [(1, 1, 1), (3, 2, 4)])
def test_binary_roundtrip_preserves_every_value_and_protocol_v2_shapes(
    view, image_mode, waveform_mode, curves, waveform_plots, image_plots
):
    config = Config(
        points=13,
        append_count=3,
        curves=curves,
        waveform_plots=waveform_plots,
        width=5,
        height=7,
        image_plots=image_plots,
        waveform_mode=waveform_mode,
        image_mode=image_mode,
        view=view,
    )
    packet = make_packet(config, 7)
    frame = decode_frame(packet)
    assert frame.seq == 7
    assert frame.header["version"] == VERSION == 2
    assert frame.header["config"] == config.to_dict()
    expected = generate_arrays(config, 7)
    assert (
        set(frame.arrays)
        == set(expected)
        == {"waveform": {"waveform"}, "image": {"image"}, "both": {"waveform", "image"}}[view]
    )
    for name, array in expected.items():
        np.testing.assert_array_equal(frame.arrays[name], array)
        assert not frame.arrays[name].flags.writeable
    if view != "image":
        waveform = frame.arrays["waveform"]
        assert waveform.shape == (waveform_plots, curves, 13) and waveform.dtype == np.float32
        # Every plot and curve carries distinct data.
        flat = waveform.reshape(waveform_plots * curves, 13)
        assert len({row.tobytes() for row in flat}) == waveform_plots * curves
    if view != "waveform":
        image = frame.arrays["image"]
        if image_mode == "scalar":
            assert image.shape == (image_plots, 7, 5) and image.dtype == np.float32
        else:
            assert image.shape == (image_plots, 7, 5, 3) and image.dtype == np.uint8
        assert len({image[p].tobytes() for p in range(image_plots)}) == image_plots
    # Row-major layout: plot p, curve c is the contiguous slice at (p * curves + c) * points.
    header_size = struct.unpack_from("<I", packet)[0]
    base = (header_size + 7) & ~3
    for descriptor in frame.header["arrays"]:
        raw = np.frombuffer(
            packet,
            dtype=np.float32 if descriptor["dtype"] == "float32" else np.uint8,
            count=descriptor["nbytes"] // (4 if descriptor["dtype"] == "float32" else 1),
            offset=base + descriptor["offset"],
        )
        if descriptor["name"] == "waveform":
            for p in range(waveform_plots):
                for c in range(curves):
                    start = (p * curves + c) * 13
                    np.testing.assert_array_equal(
                        raw[start : start + 13], expected["waveform"][p, c]
                    )
        else:
            block = 7 * 5 * (3 if image_mode == "rgb" else 1)
            for p in range(image_plots):
                np.testing.assert_array_equal(
                    raw[p * block : (p + 1) * block], expected["image"][p].ravel()
                )


def test_append_windows_preserve_overlap_and_advance_exactly_for_every_plot_and_curve():
    config = Config(
        points=100,
        append_count=13,
        curves=4,
        waveform_plots=3,
        view="waveform",
        waveform_mode="append",
    )
    before = generate_arrays(config, 41)["waveform"]
    after = generate_arrays(config, 42)["waveform"]
    assert before.shape == after.shape == (3, 4, 100)
    np.testing.assert_array_equal(before[:, :, 13:], after[:, :, :-13])
    for p in range(3):
        for c in range(4):
            assert not np.array_equal(before[p, c], after[p, c])
    # Curves differ within a plot and plots differ for the same curve index.
    assert not np.array_equal(before[0, 0], before[0, 1])
    assert not np.array_equal(before[0, 0], before[1, 0])


def test_generator_formulas_match_the_documented_definitions():
    config = Config(
        points=64,
        append_count=8,
        curves=3,
        waveform_plots=2,
        width=6,
        height=5,
        image_plots=3,
        image_mode="rgb",
    )
    seq = 9
    phase = seq * 0.13 + (config.seed % 10000) * 0.001
    arrays = generate_arrays(config, seq)
    x = np.linspace(0, 12 * np.pi, config.points, dtype=np.float32)
    for p in range(2):
        for c in range(3):
            total_shift = phase + (p * 0.29 + c * 0.61)
            harmonic = 4.3 + 0.37 * c
            expected = np.sin(x + total_shift) + 0.23 * np.sin(x * harmonic - phase * 0.7)
            np.testing.assert_array_equal(arrays["waveform"][p, c], expected.astype(np.float32))
    appended = generate_arrays(config.updated({"waveform_mode": "append"}), seq)["waveform"]
    xa = np.arange(config.points, dtype=np.float64) + seq * config.append_count
    for p in range(2):
        for c in range(3):
            shift, rate = p * 0.29 + c * 0.61, 0.071 + 0.0061 * c
            expected = np.sin(xa * 0.017 + config.seed * 0.001 + shift) + 0.23 * np.sin(xa * rate)
            np.testing.assert_array_equal(appended[p, c], expected.astype(np.float32))
    xi = np.linspace(0, 4 * np.pi, config.width, dtype=np.float32)[None, :]
    yi = np.linspace(0, 4 * np.pi, config.height, dtype=np.float32)[:, None]
    for p in range(3):
        ph = phase + p * 0.47
        scalar = np.clip((np.sin(xi + ph) + np.cos(yi - ph * 0.7) + 2) * 0.25, 0, 1)
        np.testing.assert_array_equal(arrays["image"][p, :, :, 0], (scalar * 255).astype(np.uint8))
        green = np.broadcast_to(((np.sin(xi * 0.7 - ph) + 1) * 127.5).astype(np.uint8), (5, 6))
        blue = np.broadcast_to(((np.cos(yi * 0.9 + ph) + 1) * 127.5).astype(np.uint8), (5, 6))
        np.testing.assert_array_equal(arrays["image"][p, :, :, 1], green)
        np.testing.assert_array_equal(arrays["image"][p, :, :, 2], blue)
        scalar_frame = generate_arrays(config.updated({"image_mode": "scalar"}), seq)["image"]
        np.testing.assert_array_equal(scalar_frame[p], scalar.astype(np.float32))


def test_decoder_rejects_protocol_v1_frames():
    packet = bytes(make_packet(Config(points=4, append_count=1, width=2, height=2), 0))
    assert b'"version":2' in packet
    with pytest.raises(ValueError, match="unsupported protocol version"):
        decode_frame(packet.replace(b'"version":2', b'"version":1', 1))
    with pytest.raises(ValueError, match="unsupported protocol version"):
        decode_frame(packet.replace(b'"version":2', b'"version":3', 1))


def rewrite_header(packet, transform):
    """Re-encode a packet with a modified JSON header and the same payload bytes."""
    header_size = struct.unpack_from("<I", packet)[0]
    header = json.loads(bytes(packet[4 : 4 + header_size]))
    base = (header_size + 7) & ~3
    raw_header = json.dumps(transform(header), separators=(",", ":")).encode()
    padded = (len(raw_header) + 7) & ~3
    return (
        struct.pack("<I", len(raw_header))
        + raw_header.ljust(padded - 4, b"\0")
        + bytes(packet[base:])
    )


@pytest.mark.parametrize(
    "shape,match",
    [
        ([2, 3, 4, 5, 6], "invalid shape"),
        ([], "invalid shape"),
        ([3, 1, 4], "does not match configuration"),
        ([12], "does not match configuration"),
        ([2, 6, 1], "does not match configuration"),
    ],
)
def test_decoder_rejects_shapes_that_do_not_match_the_configuration(shape, match):
    config = Config(points=4, append_count=1, curves=3, waveform_plots=1, view="waveform")
    packet = make_packet(config, 0)

    def transform(header):
        header["arrays"][0]["shape"] = shape
        return header

    with pytest.raises(ValueError, match=match):
        decode_frame(rewrite_header(packet, transform))
    assert decode_frame(rewrite_header(packet, lambda h: h)).arrays["waveform"].shape == (1, 3, 4)


def test_decoder_requires_the_plot_fields_when_a_configuration_is_present():
    packet = make_packet(Config(points=4, append_count=1, view="waveform"), 0)

    def drop_curves(header):
        del header["config"]["curves"]
        return header

    with pytest.raises(ValueError, match="plot fields"):
        decode_frame(rewrite_header(packet, drop_curves))


def test_four_dimensional_rgb_images_decode_as_views_per_plot():
    config = Config(points=4, append_count=1, width=3, height=2, image_plots=5, image_mode="rgb")
    frame = decode_frame(make_packet(config, 3))
    image = frame.arrays["image"]
    assert image.shape == (5, 2, 3, 3) and image.dtype == np.uint8
    for plot in range(5):
        view = image[plot]
        assert view.base is not None and view.flags.c_contiguous and not view.flags.writeable
    assert frame.arrays["waveform"].shape == (1, 1, 4)


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
        {"curves": 0},
        {"curves": 65},
        {"curves": True},
        {"curves": 2.0},
        {"waveform_plots": 0},
        {"waveform_plots": 17},
        {"waveform_plots": False},
        {"image_plots": 0},
        {"image_plots": 17},
        {"image_plots": "2"},
        {"unknown_plots": 1},
    ],
)
def test_invalid_configuration_is_rejected(changes):
    with pytest.raises(ValueError):
        Config().updated(changes)


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"curves": 0}, "curves must be between 1 and 64"),
        ({"curves": 65}, "curves must be between 1 and 64"),
        ({"curves": True}, "curves must be an integer"),
        ({"waveform_plots": 17}, "waveform_plots must be between 1 and 16"),
        ({"image_plots": 0}, "image_plots must be between 1 and 16"),
        ({"image_plots": 1.5}, "image_plots must be an integer"),
        ({"curves": 64, "waveform_plots": 16, "points": 10_000_000}, "a frame must fit in 256 MiB"),
        ({"image_plots": 16, "width": 8192, "height": 8192}, "a frame must fit in 256 MiB"),
    ],
)
def test_plot_field_validation_messages(changes, message):
    with pytest.raises(ValueError, match=message):
        Config().updated(changes)


def test_plot_fields_default_to_one_in_the_documented_order_and_bounds_are_inclusive():
    config = Config()
    assert (config.curves, config.waveform_plots, config.image_plots) == (1, 1, 1)
    assert list(config.to_dict()) == [
        "hz",
        "points",
        "append_count",
        "curves",
        "waveform_plots",
        "width",
        "height",
        "image_plots",
        "waveform_mode",
        "image_mode",
        "view",
        "seed",
        "generation",
    ]
    extreme = Config(
        points=1000,
        append_count=1,
        curves=64,
        waveform_plots=16,
        width=64,
        height=64,
        image_plots=16,
    )
    assert extreme.payload_bytes == 16 * 64 * 1000 * 4 + 16 * 64 * 64 * 4
    assert Config(curves=64, waveform_plots=16, image_plots=16, view="image").payload_bytes == (
        16 * 512 * 512 * 4
    )


def test_config_updates_are_atomic_and_advance_generation():
    before = Config()
    after = before.updated({"hz": 120, "width": 2048})
    assert before.hz == 30
    assert after.generation == before.generation + 1
    assert after.payload_bytes == 10000 * 4 + 2048 * 512 * 4


@pytest.mark.parametrize(
    "view,image_mode,expected",
    [
        ("both", "scalar", 2 * 3 * 100 * 4 + 4 * 8 * 6 * 4),
        ("both", "rgb", 2 * 3 * 100 * 4 + 4 * 8 * 6 * 3),
        ("waveform", "rgb", 2 * 3 * 100 * 4),
        ("image", "scalar", 4 * 8 * 6 * 4),
    ],
)
def test_payload_bytes_count_every_plot_and_curve(view, image_mode, expected):
    config = Config(
        points=100,
        append_count=1,
        curves=3,
        waveform_plots=2,
        width=8,
        height=6,
        image_plots=4,
        view=view,
        image_mode=image_mode,
    )
    assert config.payload_bytes == expected
    assert len(make_packet(config, 0)) >= expected


def test_curve_colours_are_eight_hex_strings_with_the_accent_first():
    assert isinstance(CURVE_COLORS, tuple) and len(CURVE_COLORS) == 8
    assert CURVE_COLORS[0] == "#64dccc"
    assert all(len(c) == 7 and c[0] == "#" and int(c[1:], 16) >= 0 for c in CURVE_COLORS)
    assert len(set(CURVE_COLORS)) == 8


@pytest.mark.parametrize(
    "transform,match",
    [
        (lambda h: h["arrays"][0].update(shape=[2, 2, 9]), "does not match configuration"),
        (lambda h: h["arrays"][0].update(shape=[2, 3]), "does not match configuration"),
        (lambda h: h["arrays"][0].update(shape=[2, 2, 3, 3, 1]), "invalid shape"),
        (lambda h: h["config"].update(image_mode="scalar"), "dtype uint8 does not match"),
        (lambda h: h["config"].update(view="waveform"), "not enabled by view"),
        (lambda h: h.update(config=[1]), "must be a JSON object"),
        (lambda h: h["config"].pop("image_plots"), "lacks the protocol v2 plot fields"),
    ],
)
def test_decoder_validates_image_descriptors_against_image_mode_and_view(transform, match):
    config = Config(width=3, height=2, image_plots=2, view="image", image_mode="rgb")
    packet = make_packet(config, 0)

    def apply(header):
        transform(header)
        return header

    with pytest.raises(ValueError, match=match):
        decode_frame(rewrite_header(packet, apply))
    assert decode_frame(rewrite_header(packet, lambda h: h)).arrays["image"].shape == (2, 2, 3, 3)


def test_decoder_rejects_a_scalar_image_declared_as_rgb_bytes():
    config = Config(width=3, height=2, image_plots=1, view="image", image_mode="scalar")
    packet = make_packet(config, 0)

    def transform(header):
        header["config"]["image_mode"] = "rgb"
        return header

    with pytest.raises(ValueError, match="dtype float32 does not match"):
        decode_frame(rewrite_header(packet, transform))
