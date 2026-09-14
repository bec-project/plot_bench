"""The shared generator follows the documented formulas for every plot and curve."""

import numpy as np
import pytest

from plotbench.config import Config
from plotbench.generator import generate_arrays


def legacy_arrays(config, seq):
    """Protocol v1 single-plot, single-curve formulas, kept inline as the reference."""
    arrays = {}
    phase = seq * 0.13 + (config.seed % 10000) * 0.001
    if config.view != "image":
        if config.waveform_mode == "append":
            x = np.arange(config.points, dtype=np.float64) + seq * config.append_count
            y = np.sin(x * 0.017 + config.seed * 0.001) + 0.23 * np.sin(x * 0.071)
        else:
            x = np.linspace(0, 12 * np.pi, config.points, dtype=np.float32)
            y = np.sin(x + phase) + 0.23 * np.sin(x * 4.3 - phase * 0.7)
        arrays["waveform"] = y.astype(np.float32)
    if config.view != "waveform":
        x = np.linspace(0, 4 * np.pi, config.width, dtype=np.float32)[None, :]
        y = np.linspace(0, 4 * np.pi, config.height, dtype=np.float32)[:, None]
        scalar = np.clip((np.sin(x + phase) + np.cos(y - phase * 0.7) + 2) * 0.25, 0, 1)
        if config.image_mode == "scalar":
            arrays["image"] = scalar.astype(np.float32)
        else:
            image = np.empty((config.height, config.width, 3), dtype=np.uint8)
            image[:, :, 0] = (scalar * 255).astype(np.uint8)
            image[:, :, 1] = ((np.sin(x * 0.7 - phase) + 1) * 127.5).astype(np.uint8)
            image[:, :, 2] = ((np.cos(y * 0.9 + phase) + 1) * 127.5).astype(np.uint8)
            arrays["image"] = image
    return arrays


@pytest.mark.parametrize("waveform_mode", ["replace", "append"])
@pytest.mark.parametrize("image_mode", ["scalar", "rgb"])
@pytest.mark.parametrize("seed,seq", [(42, 0), (42, 37), (12345, 932), (10007, 10000)])
def test_first_plot_and_curve_are_bit_identical_to_protocol_v1(
    waveform_mode, image_mode, seed, seq
):
    config = Config(
        points=257,
        append_count=31,
        width=17,
        height=13,
        seed=seed,
        waveform_mode=waveform_mode,
        image_mode=image_mode,
    )
    expected = legacy_arrays(config, seq)
    for curves, waveform_plots, image_plots in ((1, 1, 1), (3, 2, 2), (5, 4, 3)):
        arrays = generate_arrays(
            config.updated(
                dict(curves=curves, waveform_plots=waveform_plots, image_plots=image_plots)
            ),
            seq,
        )
        assert arrays["waveform"].shape == (waveform_plots, curves, config.points)
        assert arrays["waveform"].dtype == np.float32
        np.testing.assert_array_equal(arrays["waveform"][0, 0], expected["waveform"])
        assert arrays["image"].shape == (image_plots, *expected["image"].shape)
        assert arrays["image"].dtype == expected["image"].dtype
        np.testing.assert_array_equal(arrays["image"][0], expected["image"])
