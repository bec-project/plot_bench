"""PyQtGraph plotting adapter; no generator or transport implementation lives here."""

import os

os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"
