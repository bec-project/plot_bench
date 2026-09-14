"""Validated, serializable workload configuration."""

import math
from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True)
class Config:
    hz: float = 30.0
    points: int = 10_000
    append_count: int = 1_000
    curves: int = 1
    waveform_plots: int = 1
    width: int = 512
    height: int = 512
    image_plots: int = 1
    waveform_mode: str = "replace"
    image_mode: str = "scalar"
    view: str = "both"
    seed: int = 42
    generation: int = 0

    def __post_init__(self):
        if isinstance(self.hz, bool) or not isinstance(self.hz, (float, int)):
            raise ValueError("hz must be a number")
        if not math.isfinite(self.hz) or not 0 < self.hz <= 120:
            raise ValueError("hz must be greater than zero and at most 120")
        for name in (
            "points",
            "append_count",
            "curves",
            "waveform_plots",
            "width",
            "height",
            "image_plots",
            "seed",
            "generation",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        for name, limit in (("curves", 64), ("waveform_plots", 16), ("image_plots", 16)):
            if not 1 <= getattr(self, name) <= limit:
                raise ValueError(f"{name} must be between 1 and {limit}")
        for name in ("points", "append_count", "width", "height", "seed", "generation"):
            if getattr(self, name) < (0 if name in ("seed", "generation") else 1):
                raise ValueError(f"{name} is out of range")
        if self.append_count > self.points:
            raise ValueError("append_count must not exceed points")
        for name, allowed in (
            ("waveform_mode", ("replace", "append")),
            ("image_mode", ("scalar", "rgb")),
            ("view", ("waveform", "image", "both")),
        ):
            if getattr(self, name) not in allowed:
                raise ValueError(f"{name} must be one of {allowed}")
        if self.points > 10_000_000 or max(self.width, self.height) > 8192:
            raise ValueError("maximum dimensions: 10M waveform samples and 8192 image pixels/axis")
        if self.payload_bytes > 256 * 1024 * 1024:
            raise ValueError("a frame must fit in 256 MiB")

    @property
    def payload_bytes(self):
        """Bytes of array payload per frame: every waveform plot and curve, every image plot."""
        wave = self.waveform_plots * self.curves * self.points * 4 if self.view != "image" else 0
        image = (
            self.image_plots * self.width * self.height * (4 if self.image_mode == "scalar" else 3)
        )
        return wave + (image if self.view != "waveform" else 0)

    def to_dict(self):
        return asdict(self)

    def updated(self, values):
        if not isinstance(values, dict):
            raise ValueError("configuration must be a JSON object")
        unknown = set(values) - (set(self.to_dict()) - {"generation"})
        if unknown:
            raise ValueError(f"unknown or read-only fields: {sorted(unknown)}")
        return replace(self, **values, generation=self.generation + 1)
