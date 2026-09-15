# Submit a baseline campaign

This directory is the reviewed public collection. It holds complete campaigns of
the official baseline suite, [`scenarios/baseline.json`](../../scenarios/baseline.json),
and nothing else: seven sections at 60 Hz from the Rust source in streaming mode,
three 30-second repetitions after a 5-second warmup, for any subset of the nine
frontends. Add one `<campaign-id>.json` file through a pull request; never copy an
entire raw `results/` directory here. The website and its command-line exporter
produce the same version 1 format, defined by
[`submission.schema.json`](../submission.schema.json).

1. Run the baseline unmodified, following the
   [benchmark procedure](../../AGENTS.md#running-a-requested-benchmark): a visible
   native or Wayland desktop, a fixed refresh rate and display scale for the whole
   campaign, the display recorded with `--display-context`, and only
   `--frontends` narrowing the suite. Keep all attempts and preserve the suite and
   raw data.
   ```sh
   ./scripts/plotbench run --baseline --frontends pyqtgraph matplotlib --output results/baseline \
     --display-context "internal display, 120 Hz fixed, 2x scale, window centered"
   ```
2. Export it. Open **Contribute** on the website and select that campaign's
   `summary.json`, or use the [CLI export](../README.md#contribute-results):
   ```sh
   npm --prefix website run export -- --input ../results/baseline/summary.json
   ```
   Review the proposed campaign ID and public host alias, or replace them. The
   proposed ID is `<cpu>-<os>-<yyyymmdd>-plotbench-baseline`; a second campaign
   on the same host and day needs a suffix, because IDs and file names must be
   unique.
3. Inspect every public field. The exporter omits raw logs, command lines, local
   paths, hostnames, display names and environment values. Free-text fields such
   as notes, hardware labels, renderer descriptions and version strings still
   require review. Use a friendly alias, not a hostname, username or serial number.
4. Add the JSON here as `<campaign-id>.json` (rename it if your browser appended a
   number), run validation and open a pull request describing the hardware,
   operating conditions and retained evidence. Include failures and source-limited
   sections; do not cherry-pick the fastest runs.
   ```sh
   npm --prefix website ci
   npm --prefix website run validate
   npm --prefix website test
   ```

## What is rejected

The exporter and CI check the campaign's structure, not its file name, so an
edited copy of the baseline saved from the matrix editor is refused like any
other suite. The exporter first refuses a summary that is not structurally the
baseline (cooldown, repetition count, mode and backend lists, case list, completion
status, sections, repetitions, timings, frontends or run counts) with a message
starting "Only campaigns of the official baseline suite can be published". A
campaign that is baseline-shaped but classified smoke or diagnostic, or whose runs
lack a clean recorded commit, is refused by the same submission check that CI runs
on this directory, so both the exporter and CI report it with a message starting
"Not a baseline campaign". Rejected:

- any suite other than the baseline, including a baseline run with a changed
  rate, workload, seed, source backend or delivery mode;
- a baseline run with `--limit`, `--repetitions`, `--duration`, `--warmup` or
  `--cooldown` overrides (the `--baseline` flag refuses them; opening the file
  with `--suite` allows them for local experiments, which then cannot be
  published);
- an interrupted campaign, or any frontend missing a section or a repetition
  (every included frontend needs all seven sections with repetitions 1, 2 and 3,
  and the planned run count must be 21 per frontend);
- a smoke or diagnostic classification: headless runs, an unknown display
  context, or a display protocol other than native/Wayland. X11 stays diagnostic
  under the repository's current qualification scope, so X11 hosts cannot publish
  until that scope changes;
- runs with an unknown source commit or a dirty checkout: records on the site
  show their commit, so it must be recorded and clean.

Failed runs are kept and published; a failure is evidence, not a reason for
rejection. Two things need attention while measuring:

- **Fixed refresh rate and scale.** A run's context fingerprint includes the
  recorded refresh rate and display scale. An adaptive refresh rate (ProMotion
  and similar) that changes between repetitions splits them into different
  contexts, the campaign then has fewer than three repetitions per context, is
  classified as smoke and is rejected. Fix both for the whole campaign.
- **Crashes before metadata.** A frontend that crashes before reporting its
  metadata can record a different fingerprint from its other repetitions, with
  the same smoke classification as a result. Do not patch runs into the
  campaign: re-run that frontend alone with
  `./scripts/plotbench run --baseline --frontends pyqtgraph` (its own ID) as a
  separate campaign, and keep the failed campaign locally as evidence.

Cooldown, the campaign repetition count, the mode and backend lists and the case
list are verified by the exporter only, because the published format does not
carry them; CI re-verifies everything the document does contain. This is one
reason maintainer review remains part of publication.

## Identity and evidence

- Keep a stable public **host ID** for the same physical hardware; choose a new
  alias after a material hardware change. Software upgrades are separate campaigns
  with their own OS, versions and context. Host cards show the latest snapshot and
  the sections it covers; each run retains its acquisition snapshot. Aliases are
  contributor supplied, not authenticated machine identities; maintainers should
  resolve collisions.
- Give each acquisition a new **campaign ID**, using lowercase letters, digits
  and hyphens, at most 80 characters. The filename must match. The input fingerprint
  detects accidental resubmission under another name; it is not an authenticity
  guarantee. Do not change measurements to bypass duplicate checks.
- The exporter reads acquisition provenance, not the later report-generation
  provenance. It hashes build/runtime/display context so private metadata need not
  be published. A context hash is a separation key, not a certification of equality
  between independently configured hosts.
- Existing documents describe recorded acquisitions. Add new measurements as new
  documents; explain any correction to an existing record in the pull request.
- Preserve failed runs and missing values (`null`, never invented zeroes). The
  recorded/planned count and completion status expose incomplete campaigns. The
  grouped UI calculates a median of compatible campaign medians, with equal
  campaign weights. It does not calculate statistical significance. See
  [repeated measurements](../README.md#repeated-measurements) for grouping rules,
  spread, failure handling and the individual-run view.
- Optional `links.report`, `links.extended_report` and `links.raw_data` may contain
  public HTTPS URLs for separately hosted evidence. Review those files for private
  information too. Missing links are explicit. The submission does not contain raw
  per-frame data or confidence intervals.

## Classification and comparison

Classification is computed, not chosen by the contributor, and only **benchmark**
campaigns are published:

- **Diagnostic:** any run is headless, has an unknown display context, or uses a
  protocol other than native/Wayland. X11 remains diagnostic under the repository's
  current qualification scope. This does not qualify a new platform for support.
- **Benchmark:** every exact frontend/backend/mode/workload/context/timing group
  has at least three distinct repetitions, each measuring for at least 10 seconds,
  and no run meets the diagnostic condition. The baseline's 3 × 30 s recipe meets
  this when refresh rate and scale stay fixed.
- **Smoke:** all other recorded campaigns. Short checks demonstrate operation;
  they do not establish sustained performance rankings and are not published.

Passing the gate does not prove adequate statistical power, a controlled desktop,
or source-independent rendering capacity. Failed observations remain flagged.
Compare the same section on the same rendering path and display/runtime
conditions; different hosts are the variable being examined, not an excuse to
pool different experiments. See [measurement methodology](../../docs/methodology.md).

The [Winners page](../README.md#winners-across-hosts) keeps one board per section
and selects the best configuration per frontend across hosts, prioritizing
throughput, then lower memory and CPU for close update rates. It retains the
original host, source commit and display scale behind every record; source
revisions and scales stay separate groups on the same board. The
[Overall page](../README.md#overall-placement) adds the seven section placements
of each frontend and never averages a measurement. Both are best-observed record
views, not controlled comparisons.

## Validation boundaries

CI accepts only regular JSON files up to 5 MiB, rejects unknown fields and duplicate
IDs/input fingerprints, checks required data, classification and the baseline
structure, and builds the site. All campaign files in this directory are
published. The exporter accepts a single original campaign with its manifest;
export merged extensions and diagnostic bundles as their original separate
campaign summaries to avoid attributing runs to the wrong host. A missing manifest
must be recovered from retained evidence rather than fabricated. The browser/CLI
input cap is 25 MiB.

Validation cannot establish that submitted measurements are honest, complete or
comparable. Maintainer review remains the publication boundary. Submissions follow
the repository's [contribution terms](../../CONTRIBUTING.md).
