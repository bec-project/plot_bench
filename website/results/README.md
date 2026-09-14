# Submit a benchmark campaign

This directory is the reviewed public collection. Add one `<campaign-id>.json`
file through a pull request; never copy an entire raw `results/` directory here.
The website and its command-line exporter produce the same version 1 format,
defined by [`submission.schema.json`](../submission.schema.json).

1. Run a campaign using the [benchmark procedure](../../AGENTS.md#running-a-requested-benchmark).
   Record display context, keep all attempts, and preserve the suite and raw data.
2. Open **Contribute** on the website, select that campaign's `summary.json`, and
   assign a unique campaign ID and a public host alias. Alternatively use the
   [CLI export](../README.md#contribute-results).
3. Inspect every public field. The exporter omits raw logs, command lines, local
   paths, hostnames, display names and environment values. Free-text fields such
   as notes, hardware labels, renderer descriptions and version strings still
   require review. Use a friendly alias, not a hostname, username or serial number.
4. Download and add the JSON here. Run validation and open a pull request describing
   the hardware, operating conditions, campaign scope and retained evidence.
   Include failures and source-limited cases; do not cherry-pick the fastest runs.

```sh
npm --prefix website ci
npm --prefix website run validate
npm --prefix website test
```

## Identity and evidence

- Keep a stable public **host ID** for the same physical hardware; choose a new
  alias after a material hardware change. Software upgrades are separate campaigns
  with their own OS, versions and context. Host cards show the latest snapshot;
  each run retains its acquisition snapshot. Aliases are contributor supplied,
  not authenticated machine identities; maintainers should resolve collisions.
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
  information too. Missing links are explicit; the initial seed has no public raw
  archive. The submission does not contain raw per-frame data or confidence intervals.

## Classification and comparison

Classification is computed, not chosen by the contributor:

- **Diagnostic:** any run is headless, has an unknown display context, or uses a
  protocol other than native/Wayland. X11 remains diagnostic under the repository's
  current qualification scope. This does not qualify a new platform for support.
- **Benchmark:** every exact frontend/backend/mode/workload/context/timing group
  has at least three distinct repetitions, each measuring for at least 10 seconds,
  and no run meets the diagnostic condition.
- **Smoke:** all other recorded campaigns. Short checks demonstrate operation;
  they do not establish sustained performance rankings.

These thresholds label collection entries; passing them does not prove adequate
statistical power, a controlled desktop, or source-independent rendering capacity.
Failed observations remain flagged in every category. Compare the same workload,
seed, source/build, delivery mode, durations, rendering path and display/runtime
conditions. Different hosts are the variable being examined, not an excuse to
pool different experiments. See [measurement methodology](../../docs/methodology.md).

## Validation boundaries

CI accepts only regular JSON files up to 5 MiB, rejects unknown fields and duplicate
IDs/input fingerprints, checks required data and classification, and builds the
site. All campaign files in this directory are published. The exporter accepts a
single original campaign with its manifest; export merged extensions and diagnostic
bundles as their original separate campaign summaries to avoid attributing runs to
the wrong host. A missing manifest must be recovered from retained evidence rather
than fabricated. The browser/CLI input cap is 25 MiB.

Validation cannot establish that submitted measurements are honest, complete or
comparable. Maintainer review remains the publication boundary. Submissions follow
the repository's [contribution terms](../../CONTRIBUTING.md).
