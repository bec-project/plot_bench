"""Versioned data-area geometry, independent of toolkit chrome.

All dimensions passed to slot_size are logical window pixels. Adapters retain
native axes outside the slot; images fit inside it with square source pixels.
"""

import math

VERSION = "data-area-v1"


def slot_size(width, height, count):
    columns = math.ceil(math.sqrt(count))
    rows = math.ceil(count / columns)
    return (
        max(1, math.floor((width - 48 - 16 * (columns - 1)) / columns - 120)),
        max(1, math.floor((height - 340 - 16 * (rows - 1)) / rows - 140)),
    )


def image_size(slot, width, height):
    scale = min(slot[0] / width, slot[1] / height)
    return width * scale, height * scale


def geometry_errors(metadata, config):
    """Validate new-contract observations; historical runs keep their old meaning."""
    version = metadata.get("render_contract")
    if version is None:
        return []
    if version != VERSION:
        return [f"Unknown rendering contract: {version}"]
    window = metadata.get("viewport_size") or metadata.get("viewport", {}).get("logical")
    ratio = metadata.get("pixel_ratio")
    if (
        not isinstance(window, (list, tuple))
        or len(window) != 2
        or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in window)
        or type(ratio) not in (int, float)
        or not math.isfinite(ratio)
        or ratio <= 0
    ):
        return ["Missing or invalid window dimensions / pixel ratio"]
    counts = {
        "waveform": config["waveform_plots"] if config["view"] != "image" else 0,
        "image": config["image_plots"] if config["view"] != "waveform" else 0,
    }
    slot = slot_size(*window, sum(counts.values()))
    expected = {"waveform": slot, "image": image_size(slot, config["width"], config["height"])}
    errors = []
    if min(slot) < 32:
        errors.append(
            "Window too small for this plot count: data-area slots must be at least 32 logical pixels"
        )
    areas = metadata.get("plot_viewports_all", {})
    if not isinstance(areas, dict):
        return errors + ["Missing or invalid per-plot data areas"]
    for kind, count in counts.items():
        observed = areas.get(kind, [])
        if not isinstance(observed, list) or len(observed) != count:
            errors.append(f"{kind}: expected {count} measured data areas")
            continue
        for index, actual in enumerate(observed):
            target = [v * ratio for v in expected[kind]]
            if (
                not isinstance(actual, (list, tuple))
                or len(actual) != 2
                or any(
                    type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in actual
                )
                or any(abs(a - b) > 1.5 for a, b in zip(actual, target, strict=True))
            ):
                errors.append(
                    f"{kind} {index + 1}: observed {actual}, expected {target} physical pixels"
                )
    return errors
