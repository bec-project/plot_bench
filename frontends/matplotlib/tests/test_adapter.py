from types import SimpleNamespace

import matplotlib
import numpy as np
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from plotbench.config import Config
from plotbench.palette import CURVE_COLORS, colorize
from qtpy.QtWidgets import QApplication

from plotbench_matplotlib.app import PlotCanvas, plot_grid


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


def frame(**arrays):
    return SimpleNamespace(arrays=arrays)


def all_lines(canvas):
    return [line for plot_lines in canvas.lines for line in plot_lines]


@pytest.mark.parametrize("waveform_mode", ["replace", "append"])
def test_authoritative_window_reuses_artist_without_decimation(canvas, waveform_mode):
    config = Config(
        points=100, append_count=10, view="waveform", waveform_mode=waveform_mode
    ).to_dict()
    canvas.apply_config(config)
    original_artist = canvas.line
    for seq in (0, 4):
        waveform = (np.linspace(-1, 1, 100, dtype=np.float32) + seq / 100).reshape(1, 1, 100)
        canvas.update_frame(frame(waveform=waveform))
        np.testing.assert_array_equal(canvas.line.get_ydata(), waveform[0, 0])
        assert len(canvas.line.get_path().vertices) == 100
    assert canvas.line is original_artist
    assert not canvas.line.get_path().should_simplify
    assert canvas.image_axes == [] and canvas.image_axis is None


def test_image_switch_and_resize_rebuild_background(canvas):
    canvas.apply_config(Config(view="image").to_dict())
    original_artist = canvas.image_artist
    for image_mode, shape in [("scalar", (4, 5)), ("rgb", (6, 7, 3)), ("scalar", (3, 2))]:
        config = Config(
            width=shape[1], height=shape[0], view="image", image_mode=image_mode
        ).to_dict()
        canvas.apply_config(config)
        assert canvas.background is None
        image = np.ones((1, *shape), dtype=np.uint8 if image_mode == "rgb" else np.float32)
        canvas.update_frame(frame(image=image))
        assert canvas.background is not None
        expected = image[0] if image_mode == "rgb" else np.full(shape, 255, dtype=np.uint8)
        np.testing.assert_array_equal(canvas.image_artist.get_array(), expected)
        assert canvas.waveform_axes == [] and canvas.waveform_axis is None
        assert canvas.image_axis is canvas.image_axes[0]
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
    )[None, None, :]
    config = Config(width=values.shape[2], height=1, view="image", image_mode="scalar").to_dict()
    canvas.apply_config(config)
    canvas.update_frame(frame(image=values))
    actual = canvas.image_artist.to_rgba(canvas.image_artist.get_array(), bytes=True)[..., :3]
    np.testing.assert_array_equal(actual, colorize(values[0]))


@pytest.mark.parametrize("waveform_mode", ["replace", "append"])
def test_every_curve_of_every_plot_receives_its_own_slice(canvas, waveform_mode):
    config = Config(
        points=50,
        append_count=5,
        curves=10,
        waveform_plots=3,
        view="waveform",
        waveform_mode=waveform_mode,
    ).to_dict()
    canvas.apply_config(config)
    assert len(canvas.waveform_axes) == 3 and canvas.image_axes == []
    assert [len(plot_lines) for plot_lines in canvas.lines] == [10, 10, 10]
    assert canvas.waveform_axis is canvas.waveform_axes[0]
    assert canvas.line is canvas.lines[0][0]
    rng = np.random.default_rng(7)
    for _ in range(2):
        waveform = rng.uniform(-1, 1, (3, 10, 50)).astype(np.float32)
        canvas.update_frame(frame(waveform=waveform))
        for plot, plot_lines in enumerate(canvas.lines):
            for curve, line in enumerate(plot_lines):
                np.testing.assert_array_equal(line.get_ydata(), waveform[plot, curve])
                np.testing.assert_array_equal(line.get_xdata(), np.arange(50))
                assert line.get_color() == CURVE_COLORS[curve % 8]
                assert line.get_animated() and not line.get_antialiased()
                assert len(line.get_path().vertices) == 50
    for axis in canvas.waveform_axes:
        assert axis.get_xlim() == (0, 49)
        assert axis.get_ylim() == (-1.5, 1.5)
        assert len(axis.lines) == 10
    assert canvas.lines[0][0].get_color() == "#64dccc"
    assert canvas.lines[2][9].get_color() == "#f5c76e"


@pytest.mark.parametrize(
    "image_mode, shape", [("scalar", (3, 4, 5)), ("rgb", (4, 6, 7, 3)), ("scalar", (1, 3, 2))]
)
def test_every_image_plot_shows_its_own_block(canvas, image_mode, shape):
    config = Config(
        width=shape[2], height=shape[1], image_plots=shape[0], view="image", image_mode=image_mode
    ).to_dict()
    canvas.apply_config(config)
    assert len(canvas.image_axes) == shape[0] and canvas.waveform_axes == []
    rng = np.random.default_rng(3)
    if image_mode == "rgb":
        image = rng.integers(0, 256, shape, dtype=np.uint8)
        expected = image
    else:
        image = rng.uniform(0, 1, shape).astype(np.float32)
        expected = (np.clip(image, 0, 1) * 255).astype(np.uint8)
    conversion_ms = canvas.update_frame(frame(image=image))
    assert (conversion_ms > 0) == (image_mode == "scalar")
    for plot, artist in enumerate(canvas.image_artists):
        np.testing.assert_array_equal(artist.get_array(), expected[plot])
        assert tuple(artist.get_extent()) == (-0.5, shape[2] - 0.5, shape[1] - 0.5, -0.5)
        assert artist.get_animated()
    for axis in canvas.image_axes:
        assert axis.get_xlim() == (-0.5, shape[2] - 0.5)
        assert axis.get_ylim() == (shape[1] - 0.5, -0.5)


def test_both_kinds_update_in_one_frame_and_blit_every_artist(canvas, monkeypatch):
    calls = {"draw": 0, "blit": 0}
    original_draw, original_blit = FigureCanvasQTAgg.draw, FigureCanvasQTAgg.blit

    def counting_draw(self, *args, **kwargs):
        calls["draw"] += 1
        return original_draw(self, *args, **kwargs)

    def counting_blit(self, *args, **kwargs):
        calls["blit"] += 1
        return original_blit(self, *args, **kwargs)

    monkeypatch.setattr(FigureCanvasQTAgg, "draw", counting_draw)
    monkeypatch.setattr(FigureCanvasQTAgg, "blit", counting_blit)
    config = Config(
        points=20, append_count=2, curves=2, waveform_plots=2, width=4, height=3, image_plots=3
    ).to_dict()
    canvas.apply_config(config)
    waveform = np.arange(2 * 2 * 20, dtype=np.float32).reshape(2, 2, 20) / 100
    image = np.linspace(0, 1, 3 * 3 * 4, dtype=np.float32).reshape(3, 3, 4)
    canvas.update_frame(frame(waveform=waveform, image=image))
    assert canvas.background is not None
    # The first frame draws once to capture the background; later frames only blit.
    assert calls == {"draw": 1, "blit": 1}
    for count in range(2, 5):
        canvas.update_frame(frame(waveform=waveform, image=image))
        assert calls == {"draw": 1, "blit": count}
    assert all(artist.get_visible() for artist in canvas.animated_artists)
    assert len(canvas.animated_artists) == 2 * 2 + 3
    for plot in range(2):
        for curve in range(2):
            np.testing.assert_array_equal(
                canvas.lines[plot][curve].get_ydata(), waveform[plot, curve]
            )
    for plot in range(3):
        np.testing.assert_array_equal(
            canvas.image_artists[plot].get_array(), (image[plot] * 255).astype(np.uint8)
        )
    assert [card[1].get_text() for card in canvas.cards] == [
        "Waveform 1",
        "Waveform 2",
        "Image 1",
        "Image 2",
        "Image 3",
    ]
    assert canvas.cards[0][2].get_text() == "20 points · replace · 2 curves"
    assert canvas.cards[2][2].get_text() == "4 × 3 · scalar colormap"


def test_plot_set_is_rebuilt_only_when_counts_change(canvas):
    canvas.apply_config(
        Config(points=30, append_count=3, curves=3, waveform_plots=2, image_plots=2).to_dict()
    )
    axes = list(canvas.waveform_axes + canvas.image_axes)
    lines, images = all_lines(canvas), list(canvas.image_artists)
    assert len(axes) == 4 and len(lines) == 6 and len(images) == 2
    canvas.apply_config(
        Config(
            points=40,
            append_count=3,
            curves=3,
            waveform_plots=2,
            image_plots=2,
            width=7,
            waveform_mode="append",
        ).to_dict()
    )
    assert canvas.waveform_axes + canvas.image_axes == axes
    assert all_lines(canvas) == lines and canvas.image_artists == images
    assert canvas.cards[0][2].get_text() == "40 points · append · 3 curves"
    canvas.update_frame(
        frame(
            waveform=np.zeros((2, 3, 40), dtype=np.float32),
            image=np.zeros((2, 512, 7), dtype=np.float32),
        )
    )
    assert canvas.line.get_xdata().size == 40
    canvas.apply_config(
        Config(points=40, append_count=3, curves=4, waveform_plots=2, image_plots=2).to_dict()
    )
    assert canvas.waveform_axes + canvas.image_axes != axes
    assert not set(axes) & set(canvas.figure.axes)
    assert not set(lines) & set(all_lines(canvas))
    assert [len(plot_lines) for plot_lines in canvas.lines] == [4, 4]
    canvas.apply_config(
        Config(points=40, append_count=3, curves=4, waveform_plots=3, view="waveform").to_dict()
    )
    assert len(canvas.waveform_axes) == 3 and canvas.image_axes == []
    assert canvas.image_artist is None and canvas.image_axis is None
    assert len(canvas.figure.axes) == 3
    assert len(canvas.figure.texts) == 6 and len(canvas.figure.artists) == 3
    assert [card[1].get_text() for card in canvas.cards] == [
        "Waveform 1",
        "Waveform 2",
        "Waveform 3",
    ]
    assert canvas.background is None
    canvas.update_frame(frame(waveform=np.zeros((3, 4, 40), dtype=np.float32)))
    assert canvas.background is not None
    canvas.apply_config(Config(points=40, append_count=3, view="image").to_dict())
    assert [card[1].get_text() for card in canvas.cards] == ["Image"]
    assert canvas.cards[0][2].get_text() == "512 × 512 · scalar colormap"


@pytest.mark.parametrize(
    "arrays",
    [
        {"waveform": np.zeros((1, 2, 30), dtype=np.float32)},
        {"waveform": np.zeros((3, 2, 30), dtype=np.float32)},
        {"waveform": np.zeros((2, 2, 31), dtype=np.float32)},
        {"waveform": np.zeros((2, 2, 30, 1), dtype=np.float32)},
        {"image": np.zeros((2, 5, 4), dtype=np.float32)},
        {"image": np.zeros((5, 4), dtype=np.float32)},
        {"image": np.zeros((3, 4, 5), dtype=np.float32)},
        {"image": np.zeros((3, 5, 5), dtype=np.float32)},
        {"image": np.zeros((3, 4, 4, 3), dtype=np.uint8)},
        {"image": np.zeros((3, 5, 3, 3), dtype=np.uint8)},
    ],
)
def test_unexpected_shapes_are_rejected(canvas, arrays):
    canvas.apply_config(
        Config(
            points=30, append_count=3, curves=2, waveform_plots=2, width=4, height=5, image_plots=3
        ).to_dict()
    )
    with pytest.raises(ValueError):
        canvas.update_frame(frame(**arrays))


@pytest.mark.parametrize(
    "count, expected",
    [
        (0, (0, 0)),
        (1, (1, 1)),
        (2, (2, 1)),
        (3, (2, 2)),
        (4, (2, 2)),
        (5, (3, 2)),
        (6, (3, 2)),
        (7, (3, 3)),
        (9, (3, 3)),
        (10, (4, 3)),
        (16, (4, 4)),
        (17, (5, 4)),
        (32, (6, 6)),
    ],
)
def test_plot_grid_follows_shared_layout_rule(count, expected):
    assert plot_grid(count) == expected


@pytest.mark.parametrize(
    "view, waveform_plots, image_plots, columns, rows",
    [("both", 1, 1, 2, 1), ("both", 2, 1, 2, 2), ("waveform", 5, 1, 3, 2), ("image", 1, 9, 3, 3)],
)
def test_layout_places_cards_row_major_on_equal_cells(
    canvas, view, waveform_plots, image_plots, columns, rows
):
    canvas.apply_config(
        Config(view=view, waveform_plots=waveform_plots, image_plots=image_plots).to_dict()
    )
    axes = canvas.waveform_axes + canvas.image_axes
    # Image axes keep aspect='equal', so compare the requested (pre-aspect) boxes.
    positions = [axis.get_position(original=True).bounds for axis in axes]
    widths = {round(bounds[2], 6) for bounds in positions}
    heights = {round(bounds[3], 6) for bounds in positions}
    assert len(widths) == 1 and len(heights) == 1
    x0 = sorted({round(bounds[0], 6) for bounds in positions})
    y0 = sorted({round(bounds[1], 6) for bounds in positions}, reverse=True)
    assert len(x0) == columns and len(y0) == rows
    for index, bounds in enumerate(positions):
        assert round(bounds[0], 6) == x0[index % columns]
        assert round(bounds[1], 6) == y0[index // columns]
    panels = [card[0].get_bbox().bounds for card in canvas.cards]
    assert len({round(panel[2], 6) for panel in panels}) == 1
    assert len({round(panel[3], 6) for panel in panels}) == 1
    assert all(0 <= panel[0] and panel[0] + panel[2] <= 1 for panel in panels)
    assert all(0 <= panel[1] and panel[1] + panel[3] <= 1 for panel in panels)
    for (panel, heading, subtitle), bounds in zip(canvas.cards, positions, strict=True):
        assert heading.get_position()[1] > subtitle.get_position()[1] > bounds[1] + bounds[3]
        assert abs(heading.get_position()[0] - panel.get_x()) < 0.03
    if rows == 1 and columns == 2:
        # Two plots keep today's side-by-side split of the full height.
        assert all(abs(panel[3] - 0.994) < 1e-9 for panel in panels)


@pytest.mark.parametrize(
    "view,plots,width,height",
    [("waveform", 2, 512, 512), ("image", 1, 640, 360), ("image", 4, 32, 64)],
)
def test_render_contract_data_rectangles(canvas, qapp, view, plots, width, height):
    from plotbench.render_contract import VERSION, geometry_errors

    from plotbench_matplotlib.app import axis_viewport

    canvas.resize(1100, 820)
    canvas.show()
    qapp.processEvents()
    config = Config(
        view=view, waveform_plots=plots, image_plots=plots, width=width, height=height
    ).to_dict()
    canvas.apply_config(config)
    canvas.draw()
    metadata = {
        "render_contract": VERSION,
        "viewport_size": [1100, 820],
        "pixel_ratio": canvas.devicePixelRatioF(),
        "plot_viewports_all": {
            "waveform": [axis_viewport(a) for a in canvas.waveform_axes],
            "image": [axis_viewport(a) for a in canvas.image_axes],
        },
    }
    assert geometry_errors(metadata, config) == []
