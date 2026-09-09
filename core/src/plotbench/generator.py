"""Stateless deterministic input generation; consumers never synthesize input."""

import numpy as np

from .config import Config
from .protocol import encode_frame


def generate_arrays(config: Config, seq: int):
    if type(seq) is not int or seq < 0:
        raise ValueError("sequence must be a nonnegative integer")
    arrays = {}
    phase = seq * 0.13 + (config.seed % 10000) * 0.001
    if config.view != "image":
        if config.waveform_mode == "append":
            # Evaluate absolute sample positions in float64 so overlapping windows match exactly.
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


def make_packet(config, seq):
    arrays = generate_arrays(config, seq)
    return encode_frame(
        dict(seq=seq, generation=config.generation, config=config.to_dict()),
        arrays,
        stamp_emitted_at=True,
    )
