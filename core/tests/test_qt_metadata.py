from types import SimpleNamespace

from plotbench import qt_metadata


def properties(**values):
    return SimpleNamespace(**{name: lambda value=value: value for name, value in values.items()})


def make_screen(name="Retina", refresh_hz=120):
    return properties(
        name=name,
        manufacturer="Example",
        model="Display",
        refreshRate=refresh_hz,
        geometry=properties(x=-1512, y=0, width=1512, height=982),
        availableGeometry=properties(x=-1512, y=24, width=1512, height=934),
        devicePixelRatio=2.0,
        logicalDotsPerInchX=72.0,
        logicalDotsPerInchY=72.0,
        physicalDotsPerInchX=127.0,
        physicalDotsPerInchY=127.0,
        physicalSize=properties(width=302, height=196),
    )


def make_window(screen):
    return properties(
        screen=screen,
        geometry=properties(x=-1400, y=60, width=1100, height=820),
        devicePixelRatio=2.0,
    )


def test_window_display_records_reported_rate_coordinates_and_scaling(monkeypatch):
    monkeypatch.setattr(qt_metadata, "time", lambda: 1234.5)
    window = make_window(make_screen())
    # QWidget offers a fractional accessor; QWindow only offers devicePixelRatio.
    window.devicePixelRatioF = lambda: 1.5
    display = qt_metadata.qt_window_metadata(window)["display"]
    assert display["name"] == "Retina"
    assert display["refresh_hz"] == 120
    assert "not measured" in display["refresh_source"]
    assert display["geometry"] == [-1512, 0, 1512, 982]
    assert display["available_geometry"] == [-1512, 24, 1512, 934]
    assert display["window_geometry"] == [-1400, 60, 1100, 820]
    assert display["device_pixel_ratio"] == 2.0
    assert display["window_device_pixel_ratio"] == 1.5
    assert display["logical_dpi"] == [72.0, 72.0]
    assert display["physical_dpi"] == [127.0, 127.0]
    assert display["physical_size_mm"] == [302, 196]
    assert display["recorded_at_ms"] == 1234500


def test_refresh_observes_window_moving_to_another_display():
    window = make_window(make_screen())
    assert qt_metadata.qt_window_metadata(window)["display"]["refresh_hz"] == 120
    window.screen = lambda: make_screen("External", 60)
    display = qt_metadata.qt_window_metadata(window)["display"]
    assert display["name"] == "External"
    assert display["refresh_hz"] == 60
    assert display["window_device_pixel_ratio"] == 2.0


def test_renderer_environment_preserves_overrides_when_screen_unavailable(monkeypatch):
    monkeypatch.setenv("QSG_RENDER_LOOP", "basic")
    monkeypatch.setenv("QSG_RHI_BACKEND", "metal")
    monkeypatch.setenv("QT_SCALE_FACTOR", "1.5")
    monkeypatch.delenv("QT_QUICK_BACKEND", raising=False)
    window = make_window(None)
    metadata = qt_metadata.qt_window_metadata(window, platform_name="offscreen")
    assert metadata["display"] is None
    assert metadata["qt_platform_plugin"] == "offscreen"
    environment = metadata["renderer_environment"]
    assert environment["QSG_RENDER_LOOP"] == "basic"
    assert environment["QSG_RHI_BACKEND"] == "metal"
    assert environment["QT_SCALE_FACTOR"] == "1.5"
    assert environment["QT_QUICK_BACKEND"] is None
