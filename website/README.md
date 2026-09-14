# Community results website

A static React + TypeScript application for browsing Plotbench campaigns across
hosts and platforms. Its data lives in [`results/`](results/README.md): one
reviewed, versioned JSON document per acquisition campaign. The repository-root
`results/` remains ignored and holds private raw benchmark output.

The site defaults to grouped results, with expandable campaigns and individual
runs, host histories, exact workload filters, source backends, delivery modes,
failures, and acquisition/build/display context. Compatible campaigns on the same
host receive equal weight through a median of campaign medians. It does not
calculate a global score or pool different configurations. Submitted updates/s
are not displayed FPS. The initial eight observations come from a real, short
PyQtGraph/Matplotlib campaign and are labeled as smoke checks.

UI previews: [desktop](docs/results-desktop.png) · [mobile](docs/results-mobile.png).

The **Winners** page shows the best observed frontend configurations across hosts.
Preview: [desktop](docs/winners-desktop.png) · [mobile](docs/winners-mobile.png).

## Winners across hosts

Each comparison case ranks configurations by throughput first, then memory and CPU
when update rates are close, and keeps the best record per frontend across all
submitted hosts. It uses campaign-weighted medians, not the fastest individual
repetition. Cases require the same exact workload and seed, source
backend, delivery mode, measurement/warmup durations, campaign classification and
recorded source hash/commit/dirty state. Hardware, frontend versions and display
settings may vary; their original groups remain separate and inspectable. This is
a record table of the best observed configurations, not a controlled comparison
establishing a host-independent library winner. It calculates no cross-host mean.

The **Close update rates** selector defaults to **within 2%**, with 0%, 1% and 5%
also available. The ranking builds bands from all eligible configurations before
selecting each frontend's best record. Starting with the fastest remaining grouped
median `R`, a band includes rates `r >= R × (1 - tolerance / 100)`. The next band
starts with the fastest remaining configuration outside it. This avoids chained
closeness: at 2%, 100 and 98 updates/s share a band, while 96 remains in the next
band even though it is close to 98. Earlier bands always rank ahead of later ones.
At 0%, only identical unrounded rates share a band.

Within a band, lower **median peak RSS** wins, followed by lower **median mean CPU**.
Resource medians use the same successful repetitions with valid rates as throughput:
first a median of per-run `rss_peak_mib` or `cpu_mean_percent` in each campaign,
then a median of campaign medians with equal campaign weights. Median peak RSS is
not the maximum memory observed across the group. CPU 100% is one logical CPU,
following the process-tree measurement contract. Failed repetitions and campaigns
without valid rates contribute no resource values.

Every rate-contributing repetition must have the metric for its group resource
summary to be available. Partial coverage becomes unavailable, not an artificially
favorable median of the remaining samples. Within a throughput band, recorded
memory ranks before unavailable memory. If memory is tied and known, recorded CPU
ranks before unavailable CPU. If memory is unavailable for both configurations,
CPU does not bypass that missing higher-priority measurement; they remain tied.
Memory and CPU compare at 0.1 MiB and 0.1 percentage-point precision respectively.

All configurations tied on the band's memory/CPU criteria are retained; their
actual update-rate range is shown rather than implying equal throughput. Competition
ranks follow 1, 1, 3 after a first-place tie. Original measurements remain available
in the evidence and downloads. This tolerance is a user-selectable ranking preference,
not a statistical equivalence or significance test. Paced runs that reach their
target cannot establish maximum rendering capacity. Cases with only one eligible
frontend are explicitly marked as having one entrant.

**Benchmarks** is the default collection; **Smoke checks** and **Diagnostics** are
separate selections and never compete against benchmark campaigns. The initial
seed has only smoke checks, so the benchmark winners view explains its empty state
and links to smoke records. Incomplete-context and no-valid-rate groups cannot
win; their excluded count is shown, and the Results page retains their observations.
Source-limited groups with valid observations remain eligible with visible flags
and attempted/successful counts, including any failed repetitions.

Workload, source, mode, collection, close-rate tolerance and inclusive UTC date filters persist in the
URL. The page paginates comparison cases and ties, links back to each winning
host, and expands into campaign and run evidence. All frontend records can be
expanded to inspect the runners-up. Winners depend on the submitted coverage;
more submissions or a changed date filter may change the record holders.

## Repeated measurements

**Grouped / Individual runs** changes the display without changing any submission
or raw record. Date filters select inclusive acquisition dates in UTC, before
aggregation. View mode and filters survive reloads and can be shared in the URL.

A group requires an exact match on public host ID and hardware/OS snapshot,
frontend, backend, delivery mode, every workload field (including seed and target
rate), measurement/warmup duration, campaign classification, and the complete
recorded context (including its fingerprint, source/build identity, versions,
rendering and display fields). Friendly host labels, scenario names and dates do
not define compatibility. Opaque context hashes are deliberately conservative:
any fingerprint change splits a group. Missing source identity, renderer, timing
boundary, versions or display/headless context leaves observations unmerged.

For each group, successful repetitions with observed rates produce one median
per campaign. The headline is the median of those campaign medians: a campaign
with 100 repetitions has the same weight as one with three. **Middle 50%** is
the 25th–75th percentile of campaign medians, using linear interpolation at
`(n - 1) × q`. It is a descriptive spread, not a confidence interval. With fewer
than two contributing campaigns, spread is shown as missing rather than zero.

Failed runs remain in successful/attempted counts and in the expandable evidence,
but never enter rate statistics. A campaign with no successful rates contributes
no median and still appears in the total campaign count. Source-limit flags are
retained; source-limited successful measurements remain included and visible.
Within each campaign, expansion shows the repetition median, observed min/max,
completion status, recorded/planned totals, notes and links to run details.

Smoke and diagnostic campaigns remain separate and retain their classification;
collecting many short runs does not promote them into sustained benchmarks.
Groups are ordered by latest acquisition, not by performance. No timing
percentiles are pooled across runs. The grouped counts cover recorded attempts;
unrecorded planned cases are exposed at campaign level, not invented as failures
in a particular group. This is a display aggregation, not a file merge.

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
