# Plotbench web UI (Preact + Vite)

Source for the two local web pages, sharing one component set and style so they
look and behave the same:

- **Matrix editor** — `./scripts/plotbench matrix`. Builds, previews and saves
  benchmark suites. Served from `../src/plotbench/matrix_assets/`.
- **Source controls** — served at `/` by `./scripts/plotbench serve` (both the
  Python and Rust sources). Adjusts the live workload. Served as the single file
  `../src/plotbench/controls.html`.

## Runtime needs no Node

Both pages' built output is committed under the Python package, so they ship with
a `core`-only install and run with no Node toolchain. Node is a **contributor**
tool for rebuilding. The matrix editor is served as fixed-name assets under a
strict `script-src 'self'` CSP; the source controls page is served as one file at
`/` (neither source serves extra asset routes), so its JS and CSS are inlined.

## Develop

```sh
npm ci
# Matrix editor with HMR (proxies /api to a running editor on port 8799):
../../scripts/plotbench matrix --port 8799 --no-open   # terminal A
npm run dev                                             # terminal B
```

`npm run typecheck` runs the strict TypeScript compiler (the production build uses
esbuild and does not type-check). The source controls page talks to a running
source (`./scripts/plotbench serve`); iterate with `npm run build` and reload.

## Build and ship

After changing anything under `src/`, rebuild and commit the regenerated output:

```sh
npm run build            # matrix_assets/{index.html,editor.js,style.css} + controls.html
npm run build:matrix     # matrix editor only
npm run build:controls   # source controls only
```

Opt-in browser QA (needs a Chromium):

```sh
PLOTBENCH_TEST_BROWSER=/path/to/chromium \
  ../../.envs/plotting-benchmark/bin/python -m pytest \
  ../tests/test_matrix_browser.py ../tests/test_source_controls.py
```

## Layout

- `src/app.tsx` — matrix editor (presets, execution, workloads, preview, save).
- `src/controls-app.tsx` — source controls (live workload + activity).
- `src/components/` — shared field controls, view selector, tooltip, preset gallery,
  preview table, launcher, raw-JSON editor, command lines.
- `src/config-fields.ts` — workload field metadata grouped by plot kind, with tooltips.
- `src/types.ts` — the shared suite/config/health types.
- `vite.config.ts` builds the matrix editor; `vite.controls.config.ts` builds the
  single-file source controls page.
