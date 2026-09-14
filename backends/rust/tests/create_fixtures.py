"""Regenerate checked-in numerical fixtures using the shared Python source."""

import json
import platform
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "core" / "src"))
from plotbench.config import Config
from plotbench.generator import generate_arrays
from plotbench.palette import COLORMAP


def main():
    cases = []
    for waveform_mode in ("replace", "append"):
        for image_mode in ("scalar", "rgb"):
            for seq in (0, 37):
                cases.append((Config(points=257, append_count=31, width=17, height=13,
                                     waveform_mode=waveform_mode, image_mode=image_mode), seq))
    cases.extend([
        (Config(points=311, append_count=7, width=31, height=11), 10000),
        (Config(points=127, append_count=13, width=7, height=19, seed=12345,
                waveform_mode="append", image_mode="rgb"), 932),
        (Config(points=1, append_count=1, width=1, height=1), 0),
        (Config(points=1, append_count=1, width=1, height=1, image_mode="rgb"), 37),
    ])
    # Protocol v2: several waveform plots, several curves per plot and several image plots.
    # Plot 0 / curve 0 of every case reduces to the single-plot formulas above.
    for waveform_mode in ("replace", "append"):
        for image_mode in ("scalar", "rgb"):
            cases.append((Config(points=257, append_count=31, curves=3, waveform_plots=2,
                                 width=17, height=13, image_plots=2,
                                 waveform_mode=waveform_mode, image_mode=image_mode), 37))
    cases.extend([
        (Config(points=127, append_count=13, curves=4, waveform_plots=3, width=7, height=19,
                image_plots=3, seed=12345, waveform_mode="append", image_mode="rgb"), 932),
        (Config(points=311, append_count=7, curves=2, waveform_plots=1, width=31, height=11,
                image_plots=4, seed=777, waveform_mode="replace", image_mode="scalar"), 10000),
        (Config(points=61, append_count=61, curves=8, waveform_plots=4, seed=90001,
                waveform_mode="append", view="waveform"), 5),
        (Config(width=9, height=8, image_plots=3, seed=2024, image_mode="rgb", view="image"), 0),
        (Config(points=257, append_count=31, curves=1, waveform_plots=1, width=17, height=13,
                image_plots=1, waveform_mode="append", image_mode="rgb"), 0),
        (Config(points=1, append_count=1, curves=2, waveform_plots=2, width=1, height=1,
                image_plots=2, image_mode="rgb"), 37),
    ])
    data = dict(python=platform.python_version(), numpy=np.__version__,
                colormap=COLORMAP.tolist(), cases=[])
    for config, seq in cases:
        arrays = generate_arrays(config, seq)
        data["cases"].append(dict(
            config=config.to_dict(), seq=seq,
            arrays={name: dict(shape=list(array.shape), dtype=str(array.dtype),
                               values=array.ravel().tolist()) for name, array in arrays.items()},
        ))
    destination = Path(__file__).parent / "fixtures" / "generation.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, separators=(",", ":"), allow_nan=False) + "\n")
    print(f"Wrote {len(cases)} fixtures from Python {data['python']}, NumPy {data['numpy']}")


if __name__ == "__main__":
    main()
