# Community results website

A static React + TypeScript application that publishes campaigns of the official
Plotbench baseline suite from different hosts. Its data lives in
[`results/`](results/README.md): one reviewed, versioned JSON document per
campaign. The repository-root `results/` remains ignored and holds private raw
benchmark output.

The site publishes one suite only, [`scenarios/baseline.json`](../scenarios/baseline.json):
seven sections — waveform, multi-curve waveform, multi-plot waveform, scalar image,
RGB image, multiple scalar images and a large scalar image — all at 60 Hz from the
Rust source in streaming mode, measured as three 30-second repetitions after a
5-second warmup. A campaign is accepted only when every frontend it contains has
all seven sections with repetitions 1–3 at those durations; any subset of the
nine frontends is fine, and failed runs are kept. The site derives the sections
from the suite file at build time, so there is exactly one definition of them.

Every page keeps unlike things apart: no measurement is pooled across hosts or
sections, source revisions and display scales stay separate groups, and submitted
updates per second are not displayed FPS. The collection starts empty; the browser
tests use a private fixture, so an empty collection still builds and deploys.

Pages: **Results** (every run, per section, with host and frontend filters),
**Winners** (one record board per section), **Overall** (the section placements
added up), **Suite** (the seven sections and the run command), **Hosts** and
**Contribute**.

UI previews: [results, desktop](docs/results-desktop.png) ·
[results, mobile](docs/results-mobile.png) ·
[winners, desktop](docs/winners-desktop.png) ·
[winners, mobile](docs/winners-mobile.png) ·
[overall, desktop](docs/overall-desktop.png).

The site opens on the Winners page; Results, Overall, Hosts, Suite and
Contribute are one click away in the top navigation.

## Winners across hosts

Each section board pairs its facts with a bar chart drawn from the same records
as the ranking: one horizontal bar per frontend record at its campaign-weighted
median submitted updates/s, a whisker for the observed range of the valid
repetition rates behind that record, and a dashed line at the paced target. A
record that merges equally ranked groups (same rate band, tied resources) spans
its lowest to highest group median, the same range its record row prints. The
chart adds no statistic and shows submitted updates, not displayed FPS.

The Winners page keeps one board per baseline section, in suite order. A board
ranks configurations by throughput first, then memory and CPU when update rates
are close, and keeps the best record per frontend across all submitted hosts. It
uses campaign-weighted medians, not the fastest individual repetition.

A board's identity is the section (its slug and exact workload, including seed
and target rate), the source backend, the delivery mode, the measurement and
warmup durations and the benchmark classification. Hardware, frontend versions,
source revision and display settings may vary between the records on one board;
their original groups remain separate and inspectable, and every record shows
the source commit and the display scale it was measured at. A `scale=` filter
narrows a board to one display scale, because image sections rasterise
`width × height × scale²` device pixels. Groups whose display scale was not
recorded cannot compete. This is a record table of the best observed
configurations, not a controlled comparison establishing a host-independent
library winner. It calculates no cross-host mean.

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
60 Hz target cannot establish maximum rendering capacity; on such a board the
placings are decided by memory and CPU within the tolerance. Sections with only
one eligible frontend are explicitly marked as having one entrant.

Only benchmark-classified campaigns are published, so no smoke or diagnostic
campaign ever competes. Incomplete-context and no-valid-rate groups cannot win;
their excluded count is shown, and the Results page retains their observations.
The Iced adapter currently reports no library version strings, so its records
are excluded from every board until its adapter reports them. Source-limited
groups with valid observations remain eligible with visible flags and
attempted/successful counts, including any failed repetitions.

Section, close-rate tolerance, display scale and inclusive UTC date filters
persist in the URL. Each board links back to the winning host and expands into
campaign and run evidence; all frontend records can be expanded to inspect the
runners-up. Winners depend on the submitted coverage; more submissions or a
changed date filter may change the record holders.

## Overall placement

The Overall page turns the seven section boards into one table. For each
frontend, its **total** is the sum of the competition ranks it holds on the seven
section boards, exactly as those boards display them under the selected close-rate
tolerance, scale and date filters; the lowest total ranks first. Ties are broken
by the number of **section wins** (rank 1 placings, joint wins included);
frontends still tied share a competition rank (1, 1, 3). Only frontends with an
eligible record in all seven sections are ranked. The others are listed as
incomplete with the sections they are missing. They keep their places on the
section boards, so a complete frontend ranked below them on a board carries that
lower placement into its total.

This adds placements, never measurements: no update rate, memory or CPU value
is averaged or summed across sections or hosts. A placement on a paced section
that every entrant sustains at 60 Hz is decided by memory, then CPU, within the
tolerance, and counts the same as a placement on a section where throughput
separates the entrants. The records behind one frontend's total may come from
different hosts, source revisions and display scales; the frontend cell shows how
many hosts and revisions are involved, and each section column links to the board
where the record's host, commit, display scale and evidence are shown. It is a
summary of best-observed records, not a controlled comparison.

## Repeated measurements

**Grouped / Individual runs** changes the display without changing any submission
or raw record. Date filters select inclusive acquisition dates in UTC, before
aggregation. View mode and filters survive reloads and can be shared in the URL.

A group requires an exact match on public host ID and hardware/OS snapshot,
frontend, backend, delivery mode, every workload field (including seed, target
rate and the number of plots and curves), measurement/warmup duration, campaign classification, and the complete
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

Groups are ordered by section, then by median updates/s with the highest first;
the **Order** selector switches to latest acquisition or frontend name and the
choice persists in the URL as `sort`. The order changes what is shown first, not
what is grouped. No timing percentiles are pooled across runs. The grouped counts cover recorded
attempts; unrecorded planned cases are exposed at campaign level, not invented as
failures in a particular group. This is a display aggregation, not a file merge.

The Results page filters are the section rail, the host and frontend selectors,
the inclusive UTC date range and the grouped/individual layout. Together with the
Winners and Overall controls, the URL carries `section`, `host`, `frontend`, `sort`,
`from`, `to`, `layout`, `close` and `scale`; unknown keys or slugs fall back to
the unfiltered page, so old links keep working.

## Develop and validate

Use the Node version in the repository's `.node-version`. From the repository root:

```sh
npm ci --prefix website --cache "$PWD/.cache/npm" --no-audit --no-fund
npm --prefix website test
npm --prefix website run format:check
npm --prefix website run validate
npm --prefix website run build
npm --prefix website run dev
```

Open the `/plot_bench/` URL printed by Vite (port 5373). `dev` builds the catalogue on startup;
restart it after adding or editing result files. `build` regenerates the catalogue,
checks TypeScript, and emits `website/dist/`. Generated bundles and
`website/public/catalog.json` are ignored; CI rebuilds them from reviewed source.
No Rust, Python or plotting frontend is required to develop this website. The
site imports `scenarios/baseline.json` from the repository root, so run these
checks after editing that file too; the results workflow triggers on it.

The pages use the design tokens, type scale and control primitives of the matrix
editor and source controls; the shared block at the top of
[`src/style.css`](src/style.css) mirrors
[`core/webui/src/style.css`](../core/webui/src/style.css). Change a shared
primitive in both files, and keep site-specific rules below that block.

The automated tests cover schema validation, the baseline gate, acquisition
provenance, privacy allowlisting, failed observations, duplicate submissions,
workload identity, the per-section boards, the overall placement sum and
filesystem input handling. Browser checks can also use the repository's existing
Python browser extra; see `tests/browser_smoke.py`.

With an installed Chromium/Chrome executable, run:

```sh
PLOTBENCH_TEST_BROWSER=/path/to/chromium \
  .envs/plotting-benchmark/bin/python -m pytest website/tests/browser_smoke.py
```

CI installs the pinned `tests/requirements.txt` into its own temporary environment
and runs this check with Chromium, retaining desktop/mobile screenshots as an
artifact. These are UI functional checks, never rendering performance measurements.

## Contribute results

Only complete campaigns of the official baseline suite can be published. Run it
unmodified on a visible desktop with a fixed refresh rate and display scale,
narrowing it at most to the frontends you have installed:

```sh
./scripts/plotbench run --baseline --frontends pyqtgraph matplotlib --output results/baseline
```

The **Contribute** page reads that campaign's `summary.json` locally, produces an
allowlisted public document, and displays its exact contents for review. It sends
no file to a server. Choosing the file proposes the campaign ID
(`<cpu>-<os>-<yyyymmdd>-plotbench-baseline`; add a suffix for a second campaign
on the same day), public host alias, host label and operating-condition notes
from the summary's public fields only: CPU model, OS family, acquisition date,
suite name, run timings and display context. Hostnames, machine identifiers,
display names and paths are never used. The preview states the coverage
(7 of 7 sections, the number of frontends, 3 repetitions each). Review and adjust
the proposal (a button restores it), then download the document and open a GitHub
pull request adding it to `website/results/`. Contributors need GitHub access
only for that final step. CI validates the submission; maintainers review it
before merge.

The exporter first refuses a campaign whose summary is not structurally the
official baseline (cooldown, repetition count, mode and backend lists, case list,
completion status, sections, repetitions, timings, frontends or run counts) with a
message starting "Only campaigns of the official baseline suite can be published".
A campaign that is baseline-shaped but classified smoke or diagnostic, or whose
runs lack a clean recorded commit, is refused by the same submission check that CI
runs, so the exporter and CI both report it with a message starting "Not a
baseline campaign". Rejected: any other suite, a baseline campaign run
with `--limit`, `--repetitions`, timing, mode or backend overrides, an
interrupted campaign, a smoke or diagnostic classification (headless, X11 or an
unknown display context), and runs with an unknown commit or a dirty checkout.
Cooldown, the campaign repetition count, the mode and backend lists and the case
list are checked by the exporter only, because the published format does not
carry them.

For an equivalent command-line export (npm runs the script inside `website/`), only
`--input` is required; omitted fields use the same proposals and the file is written
to `results/<campaign-id>.json`:

```sh
npm --prefix website run export -- --input ../results/baseline/summary.json
npm --prefix website run export -- \
  --input ../results/baseline/summary.json \
  --output results/workstation-a-linux-20260915-plotbench-baseline.json \
  --id workstation-a-linux-20260915-plotbench-baseline \
  --host-id workstation-a \
  --host-label 'My Linux workstation'
npm --prefix website run validate
```

The exporter prints the values it used and refuses to overwrite an existing file. Read the
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
