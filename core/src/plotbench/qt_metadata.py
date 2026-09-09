"""Read Qt window/display provenance without depending on a Qt binding."""

import os
from time import time

_RENDERER_ENVIRONMENT = (
    "QT_QPA_PLATFORM",
    "QT_OPENGL",
    "QT_QUICK_BACKEND",
    "QSG_RHI_BACKEND",
    "QSG_RENDER_LOOP",
    "QSG_RHI_PREFER_SOFTWARE_RENDERER",
    "QSG_RHI_DEBUG_LAYER",
    "QT_SCALE_FACTOR",
    "QT_SCREEN_SCALE_FACTORS",
    "QT_SCALE_FACTOR_ROUNDING_POLICY",
    "QT_ENABLE_HIGHDPI_SCALING",
    "QT_AUTO_SCREEN_SCALE_FACTOR",
    "QT_DEVICE_PIXEL_RATIO",
)


def _rect(rect):
    return [rect.x(), rect.y(), rect.width(), rect.height()]


def qt_window_metadata(window, *, platform_name=None):
    """Snapshot cheap QScreen properties at HUD cadence, including screen changes.

    ``window`` may be a QWidget or QWindow. Refresh rate is Qt's reported nominal
    rate, not an observed presentation rate. Environment values are overrides,
    not proof of which render loop/backend Qt ultimately selected.
    """
    metadata = {
        "display": None,
        "qt_platform_plugin": platform_name,
        "renderer_environment": {name: os.environ.get(name) for name in _RENDERER_ENVIRONMENT},
    }
    screen = window.screen()
    if screen is None:
        return metadata
    pixel_ratio = getattr(window, "devicePixelRatioF", window.devicePixelRatio)()
    physical_size = screen.physicalSize()
    metadata["display"] = {
        "name": screen.name(),
        "manufacturer": screen.manufacturer(),
        "model": screen.model(),
        "refresh_hz": screen.refreshRate(),
        "refresh_source": "QScreen.refreshRate; reported nominal rate, not measured presentation",
        "geometry": _rect(screen.geometry()),
        "available_geometry": _rect(screen.availableGeometry()),
        "window_geometry": (
            [None, None, window.geometry().width(), window.geometry().height()]
            if platform_name == "wayland"
            else _rect(window.geometry())
        ),
        "window_position_available": platform_name != "wayland",
        "geometry_units": "logical pixels; [x, y, width, height]",
        "device_pixel_ratio": screen.devicePixelRatio(),
        "window_device_pixel_ratio": pixel_ratio,
        "logical_dpi": [screen.logicalDotsPerInchX(), screen.logicalDotsPerInchY()],
        "physical_dpi": [screen.physicalDotsPerInchX(), screen.physicalDotsPerInchY()],
        "physical_size_mm": [physical_size.width(), physical_size.height()],
        "recorded_at_ms": time() * 1000,
    }
    return metadata
