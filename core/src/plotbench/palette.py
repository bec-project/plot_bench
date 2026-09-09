"""Shared 256-entry blue/cyan/yellow color table, independent of plotting libraries."""

import numpy as np

_ANCHORS = np.array([[12, 18, 52], [37, 70, 145], [24, 165, 168], [150, 216, 100], [255, 236, 100]])
COLORMAP = (
    np.stack(
        [
            np.interp(np.linspace(0, 4, 256), np.arange(5), _ANCHORS[:, channel])
            for channel in range(3)
        ],
        axis=1,
    )
    .round()
    .astype(np.uint8)
)
COLORMAP.setflags(write=False)


def colorize(array):
    """Map finite scalar values in [0,1] to RGB, flooring the LUT index."""
    indices = (np.clip(array, 0, 1) * 255).astype(np.uint8)
    return COLORMAP[indices]
