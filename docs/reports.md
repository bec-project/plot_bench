# Reports and retained evidence

A frontend campaign produces two linked offline HTML files:

- `report.html`: compact charts with scenario/backend/mode selectors, acquisition
  context and failure/source-limitation indicators.
- `report-extended.html`: the full campaign, per-run tables, adapter timing stages,
  coverage, diagnostic attempts, provenance and links to raw data.

Both use the same collected statistics. Inline SVG, styles and scripts require no
CDN or network connection. The compact file omits verbose evidence rather than
embedding it in hidden tables. CSV and JSON exports remain available separately.

To regenerate existing results, replace these example paths with the result
directories printed by your completed `run` or `probe` command:

```sh
./scripts/plotbench report results/my-comparison
./scripts/plotbench report results/source-probe --probe
```

Regeneration does not overwrite raw measurements. Source-only probes also produce
a compact chart overview and an extended report with detailed tabular evidence. See
[methodology](methodology.md) before comparing results.

## Directory contents

`suite.json` records the selected input suite, resolved choices, planned jobs,
acquisition interval, completion status, declared display context and a host
snapshot. `summary.json` and `summary.csv` hold calculated summaries.

Each `run-NNNN/` contains workload/run metadata, source/build identity, raw frontend
JSONL samples, source timings, process-tree resource samples and process logs.
Preserve the whole directory to retain reproducibility. Reports regenerated on
another machine use the recorded acquisition hardware and dates; unavailable
legacy fields remain "Not recorded".

Source/build identities and runtime/display contexts remain separate comparison
groups. Failed or absent attempts remain visible. Smoke measurements and
headless/software-rendered diagnostics must not become performance rankings.

## Diagnostic campaigns

An optional `diagnostics.json` beside the main suite references separate result
directories with relative paths:

```json
{
  "replay": "../replay",
  "stability": "../stability",
  "source_probe": "../source-probe",
  "replacement:after-fix": {"path": "../retry", "note": "Retested after a harness fix."}
}
```

Regenerating the main report links or embeds the diagnostic evidence. Each attempt
retains its own dates, duration, identity and status. A replacement does not erase
the original failure. Labels after `:` distinguish multiple attempts of one kind.
Notes record relevant operating conditions, not instructions to the report reader.

An `extension:LABEL` entry can add another frontend campaign to an existing
comparison. Only runs matching scenario, configuration, source backend, delivery
mode and durations are included, under their own frontend/context identity.
Mismatching runs are explicitly excluded. For example:

```json
{"extension:qtgraphs-cpp": {"path": "../qtgraphs-cpp"}}
```

Stability evidence shows submission counts by one-second bin and measured RSS.
Missing RSS remains a gap; zero submission bins remain zero. Source probes,
replay, stability and replacement runs are never pooled into the main comparison.

## Sharing

Share both HTML files for navigation and the full result directory for raw links.
Before sharing results, review operator notes, command paths, log contents and
display metadata for information you do not intend to publish. Generated results
are ignored by Git and are not included in the source repository.

The only route onto the [community results site](../website/README.md) is a
complete campaign of the official baseline suite: run
`./scripts/plotbench run --baseline` (narrowed at most with `--frontends`), export
its `summary.json` with the site's **Contribute** page or
`npm --prefix website run export`, and open a pull request adding the JSON to
`website/results/`. The exporter refuses campaigns of any other suite, shortened
or partial baseline campaigns and smoke or diagnostic classifications before it
writes a file; see the [submission requirements](../website/results/README.md).
Reports of other campaigns are shared as files, not published on the site.

For JFreeChart, `conversion_ms` includes float32-to-double waveform copies and
scalar/RGB-to-ARGB image conversion. `draw_ms` includes axis/dataset updates and
synchronous JFreeChart drawing to reusable Java2D rasters; it is inside `update_ms`.
Swing subsequently blits those rasters. Neither timer establishes GPU completion
or screen presentation. JDK/JVM identity, compiler, library versions and JVM
arguments are recorded, so different Java configurations remain separate contexts.
Short functional smoke runs do not establish steady-state JVM performance; allow
explicit JIT warmup and retain repetitions when making performance comparisons.
