"""Matplotlib adapter with reusable artists and QtAgg blitting."""

import os
from pathlib import Path

os.environ["QT_API"] = "pyside6"
os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(__file__).resolve().parents[2] / ".cache/matplotlib")
)
