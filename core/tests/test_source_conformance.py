"""Both independently built source backends must satisfy the common wire contract."""

import json
import time
from urllib.error import HTTPError

import numpy as np
import pytest
from websockets.sync.client import connect

from plotbench.backends import ROOT
from plotbench.client import request
from plotbench.config import Config
from plotbench.generator import generate_arrays
from plotbench.palette import COLORMAP
from plotbench.protocol import decode_frame, decode_replay
from plotbench.runner import source_process


@pytest.fixture(scope="module", params=["python", "rust"])
def backend_source(request, tmp_path_factory):
    backend = request.param
    if (
        backend == "rust"
        and not (ROOT / "backends/rust/target/release/plotbench-source-rust").is_file()
    ):
        pytest.skip("build the Rust source with ./scripts/setup rust")
    output = tmp_path_factory.mktemp(f"conformance-{backend}")
    with source_process(output, Config(), backend=backend) as url:
        yield backend, url


def configure(url, **values):
    config = Config(hz=60, points=37, append_count=5, width=11, height=9, **values)
    fields = config.to_dict()
    fields.pop("generation")
    return Config(**json.loads(request(url + "/api/config", fields)))


@pytest.mark.parametrize(
    "waveform_mode,image_mode,view",
    [
        ("replace", "scalar", "both"),
        ("append", "rgb", "both"),
        ("replace", "rgb", "image"),
        ("replace", "scalar", "waveform"),
    ],
)
def test_source_frames_match_shared_numerical_contract(
    backend_source, waveform_mode, image_mode, view
):
    _, url = backend_source
    config = configure(url, waveform_mode=waveform_mode, image_mode=image_mode, view=view)
    for seq in (0, 13, 1000):
        frame = decode_frame(request(url + f"/api/frame?seq={seq}"))
        expected = generate_arrays(config, seq)
        assert frame.header["config"] == config.to_dict()
        assert frame.seq == seq
        assert set(frame.arrays) == set(expected)
        for name, array in frame.arrays.items():
            assert array.shape == expected[name].shape and array.dtype == expected[name].dtype
            if array.dtype == np.uint8:
                assert np.max(np.abs(array.astype(int) - expected[name].astype(int))) <= 1
            else:
                np.testing.assert_allclose(array, expected[name], atol=2e-6, rtol=0)


def test_config_patches_preserve_plot_selection_and_reject_invalid_fields(backend_source):
    backend, url = backend_source
    config = configure(url, view="waveform")
    updated = json.loads(request(url + "/api/config", {"hz": 120, "width": 16}))
    assert updated["view"] == "waveform"
    assert updated["points"] == config.points and updated["height"] == config.height
    assert updated["generation"] == config.generation + 1
    assert json.loads(request(url + "/api/health"))["backend"] == backend
    for patch in ({"hz": 121}, {"width": 0}, {"width": True}, {"view": "none"}, {"generation": 1}):
        with pytest.raises(HTTPError) as failure:
            request(url + "/api/config", patch)
        assert failure.value.code == 400
    assert json.loads(request(url + "/api/config")) == updated


def test_replay_palette_and_metrics_are_frontend_compatible(backend_source):
    _, url = backend_source
    config = configure(url, view="image", image_mode="rgb")
    frames = decode_replay(request(url + "/api/replay?count=2"))
    assert len(frames) == 2
    assert all(frame.header["config"] == config.to_dict() for frame in frames)
    assert all(set(frame.arrays) == {"image"} for frame in frames)
    np.testing.assert_array_equal(json.loads(request(url + "/api/colormap")), COLORMAP)
    body = dict(
        frontend="probe",
        run_id="conformance",
        mode="stream",
        metadata={},
        samples=[
            dict(
                seq=1,
                generation=config.generation,
                skipped=0,
                client_time_ms=time.time_ns() / 1e6,
                update_ms=0.1,
                receive_age_ms=None,
            )
        ],
    )
    assert json.loads(request(url + "/api/metrics", body)) == {"accepted": 1}
    body["samples"][0]["skipped"] = -1
    with pytest.raises(HTTPError) as failure:
        request(url + "/api/metrics", body)
    assert failure.value.code == 400


def test_websocket_ack_bounds_delivery_and_uses_latest_configuration(backend_source):
    _, url = backend_source
    configure(url, view="both")
    with connect(url.replace("http", "ws", 1) + "/ws", compression=None) as socket:
        first = decode_frame(socket.recv(timeout=3))
        with pytest.raises(TimeoutError):
            socket.recv(timeout=0.08)
        updated = json.loads(request(url + "/api/config", {"view": "waveform"}))
        socket.send(json.dumps({"ack": first.seq + 999, "generation": first.generation}))
        with pytest.raises(TimeoutError):
            socket.recv(timeout=0.08)
        socket.send(json.dumps({"ack": first.seq, "generation": first.generation}))
        latest = decode_frame(socket.recv(timeout=3))
        assert latest.generation == updated["generation"]
        assert set(latest.arrays) == {"waveform"}
        socket.send(json.dumps({"ack": latest.seq, "generation": latest.generation}))
