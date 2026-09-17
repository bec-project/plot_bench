# Third-party licenses

Plotbench is licensed under the [BSD 3-Clause License](LICENSE). It depends on
third-party components under their own licenses, listed below with a link to each
project's authoritative license text. Dependencies are installed through their own
package managers; this repository does not redistribute a bundled Python, Qt, Rust
or browser runtime. The linked sources are authoritative — verify them before
redistributing binaries or applications.

> **Note on Qt Graphs.** The native **Qt Graphs** module used by the `qtgraphs`
> and `qtgraphs-cpp` adapters is available under **GPLv3 or a commercial Qt
> license**, not LGPL. The PySide binding's license options do not change the
> native module's terms. See the
> [Qt Graphs license information](https://doc.qt.io/qt-6/qtgraphs-index.html#licenses-and-attributions).

## Core (`plotbench-core`)

- numpy: BSD-3-Clause License, see [here](https://github.com/numpy/numpy/blob/main/LICENSE.txt)
- aiohttp: Apache License 2.0, see [here](https://github.com/aio-libs/aiohttp/blob/master/LICENSE.txt)
- websockets: BSD-3-Clause License, see [here](https://github.com/python-websockets/websockets/blob/main/LICENSE)
- psutil: BSD-3-Clause License, see [here](https://github.com/giampaolo/psutil/blob/master/LICENSE)
- textual (TUI extra): MIT License, see [here](https://github.com/Textualize/textual/blob/main/LICENSE)
- rich (via textual): MIT License, see [here](https://github.com/Textualize/rich/blob/master/LICENSE)
- playwright (browser extra): Apache License 2.0, see [here](https://github.com/microsoft/playwright-python/blob/main/LICENSE)

## Python frontends (PyQtGraph, Matplotlib, Qt Graphs)

- PySide6: LGPLv3 License (GPL/commercial options available), see [here](https://doc.qt.io/qtforpython/licenses.html)
- Qt Graphs: GPLv3 or commercial Qt license, see [here](https://doc.qt.io/qt-6/qtgraphs-index.html#licenses-and-attributions)
- qtpy: MIT License, see [here](https://github.com/spyder-ide/qtpy/blob/master/LICENSE.txt)
- pyqtgraph: MIT License, see [here](https://github.com/pyqtgraph/pyqtgraph/blob/master/LICENSE.txt)
- matplotlib: Matplotlib License (PSF-based, BSD-compatible), see [here](https://github.com/matplotlib/matplotlib/blob/main/LICENSE/LICENSE)

## Rust source and Iced frontend

- iced / iced_runtime: MIT License, see [here](https://github.com/iced-rs/iced/blob/master/LICENSE)
- tokio / tokio-stream: MIT License, see [here](https://github.com/tokio-rs/tokio/blob/master/LICENSE)
- axum: MIT License, see [here](https://github.com/tokio-rs/axum/blob/main/axum/LICENSE)
- tower-http: MIT License, see [here](https://github.com/tower-rs/tower-http/blob/main/tower-http/LICENSE)
- bytes: MIT License, see [here](https://github.com/tokio-rs/bytes/blob/master/LICENSE)
- serde / serde_json: MIT OR Apache-2.0 License, see [here](https://github.com/serde-rs/serde/blob/master/LICENSE-MIT)
- clap: MIT OR Apache-2.0 License, see [here](https://github.com/clap-rs/clap/blob/master/LICENSE-MIT)
- anyhow: MIT OR Apache-2.0 License, see [here](https://github.com/dtolnay/anyhow/blob/master/LICENSE-MIT)
- futures-util: MIT OR Apache-2.0 License, see [here](https://github.com/rust-lang/futures-rs/blob/master/LICENSE-MIT)
- reqwest: MIT OR Apache-2.0 License, see [here](https://github.com/seanmonstar/reqwest/blob/master/LICENSE-MIT)
- tungstenite: MIT OR Apache-2.0 License, see [here](https://github.com/snapview/tungstenite-rs/blob/master/LICENSE-MIT)
- png: MIT OR Apache-2.0 License, see [here](https://github.com/image-rs/image-png/blob/master/LICENSE-MIT)
- url: MIT OR Apache-2.0 License, see [here](https://github.com/servo/rust-url/blob/main/LICENSE-MIT)

## Web UI (Plotly frontend, matrix editor / source controls, results website)

- plotly.js: MIT License, see [here](https://github.com/plotly/plotly.js/blob/master/LICENSE)
- react / react-dom: MIT License, see [here](https://github.com/facebook/react/blob/main/LICENSE)
- ajv: MIT License, see [here](https://github.com/ajv-validator/ajv/blob/master/LICENSE)
- ajv-formats: MIT License, see [here](https://github.com/ajv-validator/ajv-formats/blob/master/LICENSE)
- preact: MIT License, see [here](https://github.com/preactjs/preact/blob/main/LICENSE)
- @preact/preset-vite: MIT License, see [here](https://github.com/preactjs/preset-vite/blob/main/LICENSE)
- vite: MIT License, see [here](https://github.com/vitejs/vite/blob/main/LICENSE)
- vite-plugin-singlefile: MIT License, see [here](https://github.com/richardtallent/vite-plugin-singlefile/blob/main/LICENSE)
- tsx: MIT License, see [here](https://github.com/privatenumber/tsx/blob/master/LICENSE)
- prettier: MIT License, see [here](https://github.com/prettier/prettier/blob/main/LICENSE)
- typescript: Apache License 2.0, see [here](https://github.com/microsoft/TypeScript/blob/main/LICENSE.txt)
- type definitions (`@types/*`, DefinitelyTyped): MIT License, see [here](https://github.com/DefinitelyTyped/DefinitelyTyped/blob/master/LICENSE)

## Development and testing

- pytest: MIT License, see [here](https://github.com/pytest-dev/pytest/blob/main/LICENSE)
- ruff: MIT License, see [here](https://github.com/astral-sh/ruff/blob/main/LICENSE)
- black: MIT License, see [here](https://github.com/psf/black/blob/main/LICENSE)
- isort: MIT License, see [here](https://github.com/PyCQA/isort/blob/main/LICENSE)

## Go / Fyne frontends (native and WebAssembly)

- Fyne: BSD-3-Clause, [license and bundled asset notices](https://github.com/fyne-io/fyne/blob/v2.8.1/LICENSE).
- Gorilla WebSocket: BSD-2-Clause, [license](https://github.com/gorilla/websocket/blob/v1.5.3/LICENSE).
- Go runtime: BSD-3-Clause, [license](https://go.dev/LICENSE).
- OpenGL Go bindings: MIT, [license](https://github.com/go-gl/gl/blob/master/LICENSE).
- GLFW Go bindings and GLFW: BSD-style and zlib/libpng, [notices](https://github.com/go-gl/glfw/blob/master/LICENSE).

The complete module graph is pinned in `frontends/fyne/go.mod` and checked by
`go.sum`. Fyne includes fonts and other assets with separate notices in its
[AUTHORS and license directory](https://github.com/fyne-io/fyne/tree/v2.8.1).
Redistributed Go binaries incorporate dependencies; retain their applicable notices.
The `fyne-wasm` frontend builds from the same locked module graph and includes the
Go toolchain's `wasm_exec.js` browser runtime under the Go BSD-3-Clause license.
Browser transport uses the browser WebSocket API rather than Gorilla WebSocket.
Its controlled browser uses the core's Playwright dependency listed above.

## Java / JFreeChart frontend

- JFreeChart 1.5.6: LGPL-2.1-or-later; [upstream license](https://github.com/jfree/jfreechart/blob/v1.5.6/licence-LGPL.txt).
- Jackson core, databind and annotations 2.18.3: Apache-2.0; [Jackson licensing](https://github.com/FasterXML/jackson/blob/master/LICENSE).
- JUnit Platform Console Standalone 1.12.2 (tests only): EPL-2.0; [JUnit license](https://github.com/junit-team/junit5/blob/r5.12.2/LICENSE.md).

Exact artifact URLs and SHA-256 digests are in
`frontends/jfreechart/dependencies.lock.json`. Runtime dependencies are distributed
as separate, unmodified JARs in `build/lib`, preserving their embedded licenses and
notices and allowing replacement. The JDK is supplied by the user, not bundled.
