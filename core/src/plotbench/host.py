"""One-time host hardware and display snapshot, taken outside measured windows."""

import json
import platform
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import psutil

from .runtime import display_session

# Identifying serial numbers, vendor/product IDs and display IDs are deliberately excluded.
_DISPLAY_KEYS = (
    "_name",
    "_spdisplays_pixels",
    "_spdisplays_resolution",
    "spdisplays_resolution",
    "spdisplays_pixelresolution",
    "spdisplays_refresh_rate",
    "spdisplays_connection_type",
    "spdisplays_display_type",
    "spdisplays_main",
    "spdisplays_mirror",
    "spdisplays_online",
)
_GPU_KEYS = (
    "sppci_model",
    "spdisplays_vendor",
    "sppci_cores",
    "sppci_device_type",
    "spdisplays_metal",
    "spdisplays_mtlgpufamilysupport",
)


def command_output(args, timeout=10):
    try:
        return subprocess.check_output(args, text=True, timeout=timeout).strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def host_snapshot():
    """Describe the machine once; callers add their own component-specific fields."""
    host = dict(
        recorded_at=datetime.now(UTC).isoformat(),
        platform=platform.platform(),
        machine=platform.machine(),
        python=platform.python_version(),
        logical_cpus=psutil.cpu_count(),
        physical_cpus=psutil.cpu_count(logical=False),
        memory_bytes=psutil.virtual_memory().total,
    )
    if platform.system() == "Linux":
        host.update(linux_metadata())
        return host
    if platform.system() != "Darwin":
        return host
    host["os"] = dict(
        name="macOS",
        version=platform.mac_ver()[0] or None,
        build=command_output(["sw_vers", "-buildVersion"]),
    )
    host["model_identifier"] = command_output(["sysctl", "-n", "hw.model"])
    host["cpu_model"] = command_output(["sysctl", "-n", "machdep.cpu.brand_string"])
    raw = command_output(["system_profiler", "SPDisplaysDataType", "-json"])
    try:
        report = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        report = None
    if not isinstance(report, dict):
        host["display_metadata_error"] = "system_profiler SPDisplaysDataType unavailable"
        return host
    gpus = [gpu for gpu in report.get("SPDisplaysDataType", []) if isinstance(gpu, dict)]
    host["graphics"] = [{key: gpu[key] for key in _GPU_KEYS if key in gpu} for gpu in gpus]
    host["displays"] = [
        {key: display[key] for key in _DISPLAY_KEYS if key in display}
        for gpu in gpus
        for display in gpu.get("spdisplays_ndrvs", [])
        if isinstance(display, dict)
    ]
    return host


def linux_metadata():
    """Best-effort hardware data; never inspect hostname, serial numbers or EDID."""
    try:
        release = platform.freedesktop_os_release()
    except OSError:
        release = {}
    try:
        fields = dict(
            line.split(":", 1)
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if ":" in line
        )
        fields = {key.strip(): value.strip() for key, value in fields.items()}
        cpu_model = fields.get("model name") or fields.get("Hardware")
    except OSError:
        cpu_model = None
    graphics = []
    for line in (command_output(["lspci", "-mm"]) or "").splitlines():
        try:
            fields = shlex.split(line)
        except ValueError:
            continue
        if len(fields) >= 4 and any(kind in fields[1] for kind in ("VGA", "3D", "Display")):
            graphics.append({"model": fields[3], "vendor": fields[2]})
    return {
        "os": {
            "name": release.get("NAME", "Linux"),
            "version": release.get("VERSION_ID"),
            "build": platform.release(),
        },
        "cpu_model": cpu_model,
        "graphics": graphics,
        "displays": [],
        "display_session": display_session(),
        "display_metadata_error": "Compositor display configuration is not queried; use frontend display metadata and --display-context.",
    }
