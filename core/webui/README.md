# Plotbench web UI (Preact + Vite)

The matrix editor and source controls share Preact components, TypeScript and CSS
in this directory. Preact is the UI framework here; the separate
[Plotly frontend](../../frontends/plotly/README.md) uses React.

- **Matrix editor** — `./scripts/plotbench matrix` previews and saves benchmark
  suites. It never starts a benchmark.
- **Source controls** — `./scripts/plotbench serve` serves a live workload form at
  the source URL. Python and Rust serve the same generated page.

Both pages edit the full protocol v2 workload: besides rate, points, modes and
image size, the Waveform group carries `waveform_plots` (1–16) and `curves`
(1–64) and the Image group carries `image_plots` (1–16). The source controls
offer a "Plot layout preset" next to the rate and resolution presets that fills
the three counts and the view together; the matrix editor accepts the three
fields as group axes and its schedule preview shows each run's layout in a
`Plots` column (`2×3 wf · 3 img`).

The preset gallery pins the official baseline first: `/api/presets` marks the
bundled `scenarios/baseline.json` with `official: true` (derived from its location,
so a copy saved to `scenarios_custom/` is never official) and lists it before the
other bundled files. The editor renders that one preset in an `.official-box` above
the saved-suite box with an `official` badge and the note that it is the only suite
published on the community results site; the run command panel keeps pointing at
`scenarios/baseline.json` only while the loaded suite is unedited. Editing the
baseline in the editor is allowed, but the result is a custom, unpublishable suite.

## Source and generated files

| File | Purpose |
|---|---|
| `core/webui/index.html`, `core/webui/controls.html` | Vite entry points that mount the Preact apps |
| `core/webui/src/` | Editable components, styles and API calls |
| `core/src/plotbench/matrix_assets/` | Generated matrix `index.html`, `editor.js` and `style.css` |
| `core/src/plotbench/controls.html` | Generated single-file source controls, with JS and CSS inlined |

The HTML entry points and generated pages are required parts of the Preact build,
not a second, hand-written UI. Edit `core/webui/`, rebuild, and commit the generated
output with the source change. Do not edit the generated files directly.

Both built pages ship with the core package, so users need no Node toolchain to
run them. The matrix server allows only its three static assets under a
`script-src 'self'` content security policy. Source servers serve one HTML file at
`/` and provide no additional UI asset routes. The offline benchmark reports and
[demo gallery](../../docs/demo-gallery.html) are separate HTML documents.

## Develop

Run all commands from the **repository root**. Install Node/npm compatible with
[`package.json`](package.json) (the repository pin is in
[`.node-version`](../../.node-version)), then install the core and locked UI tools:

```sh
./scripts/setup core --dev
npm ci --prefix core/webui --cache "$PWD/.cache/npm" --no-audit --no-fund
```

For the matrix editor, start the API server in terminal A:

```sh
./scripts/plotbench matrix --port 8799 --no-open
```

In terminal B, start Vite and open [the development page](http://127.0.0.1:5273):

```sh
npm --prefix core/webui run dev
```

Vite proxies `/api` to the editor on port 8799. The editor server's own URL serves
the last production build. The proxy preserves Host and Origin together so the
editor's same-origin validation works in development. Stop both processes before
formal benchmarks.

For source controls, start a Python source (no Rust build needed):

```sh
./scripts/plotbench serve --backend python
```

Open [the source page](http://127.0.0.1:8765), rebuild the controls after editing,
and reload. For Rust, first run `./scripts/setup rust`, then
`./scripts/plotbench serve --backend rust`. Stop the other source before reusing
its port.

## Build and validate

```sh
npm --prefix core/webui test
npm --prefix core/webui run typecheck
npm --prefix core/webui run build
```

The Node test checks development proxy headers; type checking is separate from
the Vite build. To rebuild just one page, use
`npm --prefix core/webui run build:matrix` or
`npm --prefix core/webui run build:controls`.

The core's `--dev` dependencies include Playwright. For browser QA, set
`PLOTBENCH_TEST_BROWSER` to an installed Chromium executable:

```sh
PLOTBENCH_TEST_BROWSER=/path/to/chromium \
  .envs/plotting-benchmark/bin/python -m pytest \
  core/tests/test_matrix_browser.py core/tests/test_source_controls.py
```

Without that variable, the browser interaction tests skip; the static controls
packaging check still runs. See [validation](../../docs/validation.md) for installing
and selecting a repo-local Chromium. These tests are functional, headless checks.
CI type-checks and rebuilds both pages, rejects a diff against the committed bundles,
and runs both browser test files.

## Layout

- `src/main.tsx`, `src/controls.tsx` — Preact mount points.
- `src/app.tsx` — matrix presets, workloads, preview and save.
- `src/controls-app.tsx` — live source workload and activity.
- `src/components/` — shared fields, view selector, tooltips, preset gallery,
  preview table, launcher, raw-JSON editor and command lines.
- `src/config-fields.ts` — workload metadata and tooltips grouped by plot kind.
- `src/types.ts`, `src/api.ts` — API types and matrix requests.
- `vite.config.ts`, `vite.controls.config.ts` — matrix and single-file builds.
