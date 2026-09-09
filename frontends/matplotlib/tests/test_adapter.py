from types import SimpleNamespace

import matplotlib
import numpy as np
import pytest
from plotbench.config import Config
from plotbench.palette import colorize
from qtpy.QtWidgets import QApplication

from plotbench_matplotlib.app import PlotCanvas


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def canvas(qapp):
    matplotlib.rcParams.update({"path.simplify": False, "agg.path.chunksize": 0})
    canvas = PlotCanvas()
    canvas.resize(800, 600)
    yield canvas
    canvas.close()


@pytest.mark.parametrize("waveform_mode", ["replace", "append"])
def test_authoritative_window_reuses_artist_without_decimation(canvas, waveform_mode):
    config = Config(
        points=100, append_count=10, view="waveform", waveform_mode=waveform_mode
    ).to_dict()
    canvas.apply_config(config)
    original_artist = canvas.line
    for seq in (0, 4):
        waveform = np.linspace(-1, 1, 100, dtype=np.float32) + seq / 100
        canvas.update_frame(SimpleNamespace(arrays={"waveform": waveform}))
        np.testing.assert_array_equal(canvas.line.get_ydata(), waveform)
        assert len(canvas.line.get_path().vertices) == 100
    assert canvas.line is original_artist
    assert not canvas.line.get_path().should_simplify


def test_image_switch_and_resize_rebuild_background(canvas):
    original_artist = canvas.image_artist
    for image_mode, shape in [("scalar", (4, 5)), ("rgb", (6, 7, 3)), ("scalar", (3, 2))]:
        config = Config(
            width=shape[1], height=shape[0], view="image", image_mode=image_mode
        ).to_dict()
        canvas.apply_config(config)
        assert canvas.background is None
        image = np.ones(shape, dtype=np.uint8 if image_mode == "rgb" else np.float32)
        canvas.update_frame(SimpleNamespace(arrays={"image": image}))
        assert canvas.background is not None
        expected = image if image_mode == "rgb" else np.full(shape, 255, dtype=np.uint8)
        np.testing.assert_array_equal(canvas.image_artist.get_array(), expected)
        assert not canvas.waveform_axis.get_visible()
        assert canvas.image_axis.get_visible()
    assert canvas.image_artist is original_artist
    canvas.invalidate_background()
    assert canvas.background is None


def test_native_image_lut_matches_protocol_at_every_index_boundary(canvas):
    boundaries = np.arange(256, dtype=np.float32) / 255
    values = np.concatenate(
        [
            np.array([-0.1, 0.5, 0.999, 1.1], dtype=np.float32),
            boundaries,
            np.nextafter(boundaries, np.float32(-np.inf)),
            np.nextafter(boundaries, np.float32(np.inf)),
        ]
    )[None, :]
    config = Config(width=values.shape[1], height=1, view="image", image_mode="scalar").to_dict()
    canvas.apply_config(config)
    canvas.update_frame(SimpleNamespace(arrays={"image": values}))
    actual = canvas.image_artist.to_rgba(canvas.image_artist.get_array(), bytes=True)[..., :3]
    np.testing.assert_array_equal(actual, colorize(values))
