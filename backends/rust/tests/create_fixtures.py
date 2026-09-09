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
