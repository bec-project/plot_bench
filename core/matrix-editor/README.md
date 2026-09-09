# Matrix editor (Preact + Vite)

Source for the local suite editor that `./scripts/plotbench matrix` serves. The
editor builds, previews and saves benchmark suites; it never runs benchmarks.

## Runtime needs no Node

The built bundle is committed to `../src/plotbench/matrix_assets/`
(`index.html`, `editor.js`, `style.css`) and ships inside the `plotbench-core`
package, so `plotbench matrix` works with a `core`-only install and no Node
toolchain. Node is a **contributor** tool for rebuilding that bundle, not a
runtime dependency.

The build emits fixed asset names and no inline script or style, which keeps the
server's strict `script-src 'self'; style-src 'self'` Content-Security-Policy and
its three-file allow-list intact.

## Develop

```sh
npm ci
# Terminal A — the API the editor talks to:
../../scripts/plotbench matrix --port 8799 --no-open
# Terminal B — Vite dev server with HMR (proxies /api to port 8799):
npm run dev
```

`npm run typecheck` runs the strict TypeScript compiler (the production build uses
esbuild and does not type-check).

## Build and ship

After changing anything under `src/`, rebuild and commit the regenerated bundle:

```sh
npm run build          # writes ../src/plotbench/matrix_assets/{index.html,editor.js,style.css}
```

Review the change by loading `plotbench matrix` and, when the DOM changed, run the
opt-in browser QA:

```sh
PLOTBENCH_TEST_BROWSER=/path/to/chromium \
  ../../.envs/plotting-benchmark/bin/python -m pytest ../tests/test_matrix_browser.py
```

## Layout

- `src/app.tsx` — top-level editor: presets, execution setup, workloads, preview, save.
- `src/components/` — field controls, workload/group cards, preset gallery, preview table, launcher, raw-JSON editor.
- `src/config-fields.ts` — workload field metadata grouped by plot kind (the view-aware form).
- `src/api.ts`, `src/types.ts` — the loopback API client and the shared suite schema types.
