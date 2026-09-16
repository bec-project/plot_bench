import copy

import pytest

from plotbench.config import Config
from plotbench.render_contract import VERSION, geometry_errors, image_size, slot_size


@pytest.mark.parametrize(
    "count,expected", [(1, (932, 340)), (2, (398, 340)), (4, (398, 92)), (6, (220, 92))]
)
def test_standard_window_slots(count, expected):
    assert slot_size(1100, 820, count) == expected


def observation(ratio=1):
    config = Config(view="image", image_plots=4, width=640, height=360).to_dict()
    area = image_size(slot_size(1100, 820, 4), 640, 360)
    metadata = {
        "render_contract": VERSION,
        "viewport_size": [1100, 820],
        "pixel_ratio": ratio,
        "plot_viewports_all": {
            "waveform": [],
            "image": [[v * ratio for v in area] for _ in range(4)],
        },
    }
    return metadata, config


@pytest.mark.parametrize("ratio", [1, 1.25, 2])
def test_accepts_each_physical_data_area_and_square_pixels(ratio):
    metadata, config = observation(ratio)
    assert geometry_errors(metadata, config) == []


@pytest.mark.parametrize("bad", [None, [0, 0], [float("nan"), 1], [100, 100], [1], [True, 1]])
def test_rejects_one_bad_cell_even_when_first_cell_matches(bad):
    metadata, config = observation()
    metadata["plot_viewports_all"]["image"][-1] = bad
    assert geometry_errors(metadata, config)


def test_missing_extra_and_unknown_observations_are_not_normalized():
    metadata, config = observation()
    missing = copy.deepcopy(metadata)
    missing["plot_viewports_all"]["image"].pop()
    assert geometry_errors(missing, config)
    assert geometry_errors({**metadata, "render_contract": "unknown"}, config)
    assert geometry_errors({**metadata, "pixel_ratio": None}, config)
    assert geometry_errors({}, config) == []  # Legacy fixed-window run, not v1 conformity.


def test_tolerance_is_physical_not_scaled_with_dpr():
    metadata, config = observation(2)
    metadata["plot_viewports_all"]["image"][1][0] += 1
    assert geometry_errors(metadata, config) == []
    metadata["plot_viewports_all"]["image"][1][0] += 1
    assert geometry_errors(metadata, config)
