# Project and dependency licenses

Plotbench's original code is licensed under the [BSD 3-Clause License](../LICENSE),
Copyright (c) 2026 Jan Wyzula. This license does not replace dependency licenses.
A per-component list of third-party components and their licenses is in
[THIRD-PARTY-LICENSES.md](../THIRD-PARTY-LICENSES.md).

Dependencies are independently installed through their package managers; the
repository does not redistribute a bundled Python/Qt/browser runtime. Consult the
installed dependency notices when distributing applications or binaries.

In particular, the native **Qt Graphs** module used by the Python and C++ adapters
is available under **GPLv3 or a commercial Qt license**, not LGPL. PySide binding
license alternatives do not change the native module's terms. See the official
[Qt Graphs license information](https://doc.qt.io/qt-6/qtgraphs-index.html#licenses-and-attributions).

Each adapter README identifies its rendering dependencies and implementation.
Keep these notices when adapting or packaging a frontend.
