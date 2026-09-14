"""Stateless deterministic input generation; consumers never synthesize input.

Protocol v2 generates distinct data for every waveform plot, every curve and every
image plot. Plot 0 / curve 0 reduce exactly to the protocol v1 formulas, so the
first plot of each kind is bit-identical to the single-plot generator. The Rust
source mirrors the f32/f64 discipline and the left-to-right expression order of
this module; keep both in step (see docs/protocol.md).
"""

import numpy as np

from .config import Config
from .protocol import encode_frame


def waveform_shift(plot, curve):
    """Phase offset (radians) of waveform plot `plot`, curve `curve`; zero for plot 0 / curve 0."""
    return plot * 0.29 + curve * 0.61


def waveform_harmonic(curve):
    """Replace-mode second-term frequency multiplier; 4.3 for curve 0."""
    return 4.3 + 0.37 * curve


def waveform_rate(curve):
    """Append-mode second-term frequency multiplier; 0.071 for curve 0."""
    return 0.071 + 0.0061 * curve


def image_phase(phase, plot):
    """Phase of image plot `plot`; identical to `phase` for plot 0."""
    return phase + plot * 0.47


def generate_arrays(config: Config, seq: int):
    if type(seq) is not int or seq < 0:
        raise ValueError("sequence must be a nonnegative integer")
    arrays = {}
    phase = seq * 0.13 + (config.seed % 10000) * 0.001
    if config.view != "image":
        waveform = np.empty((config.waveform_plots, config.curves, config.points), dtype=np.float32)
        if config.waveform_mode == "append":
            # Evaluate absolute sample positions in float64 so overlapping windows match exactly.
            x = np.arange(config.points, dtype=np.float64) + seq * config.append_count
            for plot in range(config.waveform_plots):
                for curve in range(config.curves):
                    shift, rate = waveform_shift(plot, curve), waveform_rate(curve)
                    waveform[plot, curve] = np.sin(
                        x * 0.017 + config.seed * 0.001 + shift
                    ) + 0.23 * np.sin(x * rate)
        else:
            # float32 samples with Python-float operands keep the arithmetic in float32.
            x = np.linspace(0, 12 * np.pi, config.points, dtype=np.float32)
            for plot in range(config.waveform_plots):
                for curve in range(config.curves):
                    total_shift = phase + waveform_shift(plot, curve)
                    harmonic = waveform_harmonic(curve)
                    waveform[plot, curve] = np.sin(x + total_shift) + 0.23 * np.sin(
                        x * harmonic - phase * 0.7
                    )
        arrays["waveform"] = waveform
    if config.view != "waveform":
        x = np.linspace(0, 4 * np.pi, config.width, dtype=np.float32)[None, :]
        y = np.linspace(0, 4 * np.pi, config.height, dtype=np.float32)[:, None]
        if config.image_mode == "scalar":
            image = np.empty((config.image_plots, config.height, config.width), dtype=np.float32)
        else:
            image = np.empty((config.image_plots, config.height, config.width, 3), dtype=np.uint8)
        for plot in range(config.image_plots):
            ph = image_phase(phase, plot)
            scalar = np.clip((np.sin(x + ph) + np.cos(y - ph * 0.7) + 2) * 0.25, 0, 1)
            if config.image_mode == "scalar":
                image[plot] = scalar
            else:
                image[plot, :, :, 0] = (scalar * 255).astype(np.uint8)
                image[plot, :, :, 1] = ((np.sin(x * 0.7 - ph) + 1) * 127.5).astype(np.uint8)
                image[plot, :, :, 2] = ((np.cos(y * 0.9 + ph) + 1) * 127.5).astype(np.uint8)
        arrays["image"] = image
    return arrays


def make_packet(config, seq):
    arrays = generate_arrays(config, seq)
    return encode_frame(
        dict(seq=seq, generation=config.generation, config=config.to_dict()),
        arrays,
        stamp_emitted_at=True,
    )
