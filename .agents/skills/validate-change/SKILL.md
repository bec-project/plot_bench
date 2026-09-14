---
name: validate-change
description: Pick and run the right Plotbench checks for what you changed — core tests and Python formatting, offscreen-Qt frontend tests, Rust and C++ tests, web-UI typecheck and rebuild with the committed-bundle match, lockfile refresh, and the docs-example test — before committing. Use before any commit or pull request, or when asked whether a change broke anything.
license: BSD-3-Clause
---

# Validate a change

Run focused checks for the components you touched, from the repository root.
The complete lists and platform notes are in `docs/validation.md` and
`CONTRIBUTING.md`.

## Choose checks by what changed

| Changed | Run |
|---|---|
| `core/src/plotbench/` (source, runner, protocol, reports, matrix editor, TUI) | core tests and quality checks; protocol conformance if shared behavior changed |
| `frontends/<name>/` (Python adapter) | that adapter's offscreen tests |
| `backends/rust/` or `frontends/iced/` | `cargo test --locked` for that crate |
| `frontends/qtgraphs-cpp/` | `ctest` in its build directory |
| `core/webui/` | typecheck and rebuild; the committed bundles must come out unchanged |
| `website/` | unit tests, Prettier check, catalogue validation and the build; the browser smoke when a Chromium is selected |
| `scenarios/`, `docs/`, `README.md`, `AGENTS.md`, `.agents/skills/` | the docs-example test — it parses every documented command against the CLI |
| any `pyproject.toml`, `Cargo.toml` or `package.json` dependency change | re-lock with the tool, then the affected component's checks |

## Commands

Core (install once with `./scripts/setup core --dev`):
```sh
.envs/plotting-benchmark/bin/python -m pytest core/tests
.envs/plotting-benchmark/bin/python -m ruff check core
.envs/plotting-benchmark/bin/python -m black core --check
```

Python frontends, with offscreen Qt (swap in the adapter you changed):
```sh
QT_QPA_PLATFORM=offscreen .envs/plotting-benchmark-pyqtgraph/bin/python -m pytest frontends/pyqtgraph/tests
```

Rust and C++:
```sh
cargo test --locked --manifest-path backends/rust/Cargo.toml
cargo test --locked --manifest-path frontends/iced/Cargo.toml
ctest --test-dir frontends/qtgraphs-cpp/build --output-on-failure
```

Web UI — rebuild, then confirm the committed bundles are unchanged (an empty
`git status` means the source and the shipped pages match):
```sh
npm --prefix core/webui run typecheck
npm --prefix core/webui run build
git status --short core/src/plotbench/matrix_assets core/src/plotbench/controls.html
```

Results website — unit tests, formatting, catalogue validation, type checking and
build; nothing is committed from `website/dist`:
```sh
npm --prefix website test
npm --prefix website run format:check
npm --prefix website run validate
npm --prefix website run build
```

Lockfiles after a dependency change (also re-lock the Python frontends, which
depend on core):
```sh
uv lock --project core
uv lock --project frontends/pyqtgraph
```

Docs and skills — validates every documented `./scripts/plotbench` example and
npm script:
```sh
.envs/plotting-benchmark/bin/python -m pytest core/tests/test_documentation.py
```

## Rules

- Never regenerate numerical fixtures to make a failing implementation pass.
- Do not commit generated results, local paths, machine identifiers or logs.
- Commit regenerated web-UI bundles and lockfiles together with the source change
  that required them.
- A green offscreen or headless run establishes function only — not rendering
  performance and not platform support.
