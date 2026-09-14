# Community results website

A static React + TypeScript application for browsing Plotbench campaigns across
hosts and platforms. Its data lives in [`results/`](results/README.md): one
reviewed, versioned JSON document per acquisition campaign. The repository-root
`results/` remains ignored and holds private raw benchmark output.

The site shows individual runs, host histories, exact workload filters, source
backends, delivery modes, failures, and acquisition/build/display context. It does
not calculate a global score or pool different configurations. Submitted updates/s
are not displayed FPS. The initial eight observations come from a real, short
PyQtGraph/Matplotlib campaign and are labeled as smoke checks.

UI previews: [desktop](docs/results-desktop.png) · [mobile](docs/results-mobile.png).

## Develop and validate

Use the Node version in the repository's `.node-version`. From the repository root:

```sh
npm --prefix website ci
npm --prefix website test
npm --prefix website run format:check
npm --prefix website run validate
npm --prefix website run build
npm --prefix website run dev
```

Open the `/plot_bench/` URL printed by Vite. `dev` builds the catalogue on startup;
restart it after adding or editing result files. `build` regenerates the catalogue,
checks TypeScript, and emits `website/dist/`. Generated bundles and
`website/public/catalog.json` are ignored; CI rebuilds them from reviewed source.
No Rust, Python or plotting frontend is required to develop this website.

The automated tests cover schema validation, acquisition provenance, privacy
allowlisting, failed observations, duplicate submissions, workload identity,
classification and filesystem input handling. Browser smoke checks can also use
the repository's existing Python browser extra; see `tests/browser_smoke.py`.

With an installed Chromium/Chrome executable, run:

```sh
PLOTBENCH_TEST_BROWSER=/path/to/chromium \
  .envs/plotting-benchmark/bin/python -m pytest website/tests/browser_smoke.py
```

CI installs the pinned `tests/requirements.txt` into its own temporary environment
and runs this check with Chromium, retaining desktop/mobile screenshots as an
artifact. These are UI functional checks, never rendering performance measurements.

## Contribute results

The **Contribute** page reads a campaign's `summary.json` locally, produces an
allowlisted public document, and displays its exact contents for review. It sends
no file to a server. After review, download the document and open a GitHub pull
request adding it to `website/results/`. Contributors need GitHub access only for
that final step. CI validates the submission; maintainers review it before merge.

For an equivalent command-line export (npm runs the script inside `website/`):

```sh
npm --prefix website run export -- \
  --input ../results/my-comparison/summary.json \
  --output results/workstation-a-20260914.json \
  --id workstation-a-20260914 \
  --host-id workstation-a \
  --host-label 'My Linux workstation'
npm --prefix website run validate
```

The exporter refuses to overwrite an existing file. Read the
[submission requirements](results/README.md) before publishing. Preserve the
original raw evidence locally; the website's JSON is a compact public index, not
a replacement for the compact/extended reports or raw samples.

## GitHub Pages

`.github/workflows/results-pages.yml` tests and builds pull requests without
deployment credentials. A push to `main` deploys the reviewed catalogue and static
React bundle. In **Settings → Pages → Build and deployment**, select **GitHub
Actions** once. After merging, the project site is intended to be available at
`https://bec-project.github.io/plot_bench/`; creating the workflow alone does not
enable or publish Pages. A manual run from `main` can redeploy unchanged data.

The build uses the repository name as Vite's base path. Hash navigation preserves
filters and works on refresh without server-side routing. For a custom domain or
user/organization site served at `/`, set `PLOTBENCH_SITE_BASE` to `/` in the build
workflow. The site needs no server, database, tokens, or runtime external API.

This first version loads one generated catalogue, capped at 5 MiB per campaign.
As the collection grows, retain the submission contract while moving campaign
payloads to separate static files and keeping a small catalogue index. Large raw
reports can already be stored elsewhere and linked from submissions.
