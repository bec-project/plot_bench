# Configure a benchmark matrix

Use the same JSON file from the CLI, a script, or the browser editor. Start the
editor from the repository root:

```sh
./scripts/plotbench matrix
```

Save a suite with the file name `my-suite`, stop the editor with Ctrl+C, then
preview and run the saved file:

```sh
./scripts/plotbench run --suite scenarios_custom/my-suite.json --dry-run
./scripts/plotbench run --suite scenarios_custom/my-suite.json --dry-run --json
./scripts/plotbench run --suite scenarios_custom/my-suite.json --output results/my-comparison
```

The editor runs on loopback. Start from a bundled scenario (the gallery shows each
one's scope) or a blank suite, edit cases and Cartesian groups with a view-aware
form, select sources, frontends and modes, and preview the expanded matrix. **Save
to scenarios_custom** writes a validated suite into the git-ignored
`scenarios_custom/` folder (the file name is simplified to a safe slug); **Export
JSON** downloads it instead, for an agent or another machine. Either way the editor
only writes JSON — it never executes benchmarks or generates input data, and after
saving it shows `dry-run`, quick-check and full-run commands. A quick check uses
one repetition with a one-second warmup and three measured seconds for every
selected combination; it can still be large. Preview that command with `--dry-run`
and use a fresh `--output` directory for each attempt. `--suite`
opens a specific starting suite; `--no-open` prints the URL without opening a
browser. Stop the editor with Ctrl+C before formal measurements.

When `backends` is omitted, both `run` and `probe` select Rust only. Explicit
backend lists in imported or existing suite files remain honored; CLI `--backends`
overrides that list. Install the selected source with `./scripts/setup rust` for
Rust, or use the core's Python source with `--backends python`. To compare sources,
select `"backends": ["python", "rust"]` or `--backends python rust` explicitly.

## A small suite

```json
{
  "name": "Small waveform comparison",
  "frontends": ["pyqtgraph", "matplotlib"],
  "backends": ["python", "rust"],
  "modes": ["stream"],
  "warmup_seconds": 5,
  "measurement_seconds": 30,
  "cooldown_seconds": 2,
  "repetitions": 3,
  "order_seed": 42,
  "cases": [
    {
      "name": "waveform-10k-60hz",
      "config": {"view": "waveform", "points": 10000, "hz": 60}
    }
  ]
}
```

Install each selected component first. This example expands to 12 sequential runs.
Save it as `scenarios_custom/small-waveform.json`, then preview with
`./scripts/plotbench run --suite scenarios_custom/small-waveform.json --dry-run`.
Timing estimates include configured warmup, measurement and cooldown; startup and
replay preload add overhead. The dry-run output distinguishes these costs.

## Cartesian groups

A suite can contain `cases`, `case_groups`, or both. Each group combines every
value in each axis with its base configuration:

```json
{
  "name": "Image sizes",
  "frontends": ["pyqtgraph"],
  "backends": ["python"],
  "modes": ["stream"],
  "repetitions": 1,
  "case_groups": [
    {
      "name": "image",
      "base": {"view": "image", "hz": 60},
      "matrix": {"image_mode": ["scalar", "rgb"], "resolution": [256, 512]}
    }
  ]
}
```

`resolution` is a square-image shorthand for width and height. Individual configs
support rectangular images. Group matrix values override base values. When a
group sets waveform `points` but omits `append_count`, expansion uses one tenth
of the points, with a minimum of one. Case names must be unique after expansion.
Seeded job shuffling and expansion order are deterministic.
Do not combine a `resolution` matrix axis with `width` or `height` axes in the
same group; use explicit dimensions for rectangular combinations.

`curves`, `waveform_plots` and `image_plots` are ordinary axes too. This sweep
puts several waveform plots with several curves each into one window, the way a
beamline operator keeps several plots open, and expands to 2 × 2 × 2 = 8 cases:

```json
{
  "name": "Plots and curves per window",
  "frontends": ["pyqtgraph", "plotly"],
  "backends": ["rust"],
  "modes": ["stream"],
  "repetitions": 1,
  "case_groups": [
    {
      "name": "layout",
      "base": {"view": "both", "hz": 30, "points": 10000, "resolution": 256},
      "matrix": {"waveform_plots": [1, 4], "curves": [1, 3], "image_plots": [1, 2]}
    }
  ]
}
```

Case names list the axis values in matrix order (`layout-4-3-2` is four waveform
plots with three curves each and two image plots). Every plot and curve receives
distinct data in the same frame, so both transport and rendering scale with the
counts; see [methodology](methodology.md).

## Fields and limits

Workload fields: `hz`, `points`, `append_count`, `curves`, `waveform_plots`,
`width`, `height`, `image_plots`, `waveform_mode` (`replace`/`append`),
`image_mode` (`scalar`/`rgb`), `view` (`waveform`/`image`/`both`) and `seed`.
`generation` is source-managed; do not use it as an experiment axis. Unspecified
fields use the shared `Config` defaults (one waveform plot with one curve and one
image plot).

`curves` is the number of curves drawn in every waveform plot (1–64);
`waveform_plots` (1–16) and `image_plots` (1–16) are the numbers of waveform and
image plot widgets in the window. `view` still decides which kinds are shown:
`waveform_plots` is carried but ignored when `view` is `image`, and `image_plots`
when `view` is `waveform`. `points` is the window of every curve, so a frame holds
`waveform_plots × curves × points` waveform samples plus `image_plots` images.

Rate must be positive and at most 120 Hz. Dimensions and counts must be positive
integers; append count cannot exceed the window size. Limits are 10 million
waveform points per curve, 8192 pixels per image axis and 256 MiB per frame (all
plots and curves together). Invalid or empty matrices fail before launching
processes, with the field named in the error (for example
`cases[0].config: curves must be between 1 and 64`). These are input bounds, not
performance guarantees. A suite is limited to 10,000 expanded cases and 100,000 runs to prevent
accidental unbounded expansion. The editor table previews the first 250 jobs;
`--dry-run --json` contains the full schedule. Split larger campaigns into suites.
The editor rejects integers outside JavaScript's exact range (±9,007,199,254,740,991)
instead of rounding them. Use the CLI for JSON containing larger integer seeds.

CLI selections override suite selections:

```sh
./scripts/plotbench run --suite scenarios/smoke.json \
  --frontends pyqtgraph --backends python --modes stream \
  --duration 5 --warmup 1 --cooldown 0.5 --repetitions 1
```

`--limit` restricts expanded cases before frontend/backend/mode/repetition
multiplication. `--duration` means measured seconds; warmup is additional.
`display_context` can be supplied in JSON or overridden by `--display-context`.
Machine-specific browser paths belong in `--browser-executable`, not a shared
scenario. `--json` is used with `--dry-run` and emits the resolved plan without
starting services, building artifacts or creating result directories.

## The official baseline suite

`scenarios/baseline.json` ("Plotbench baseline") is the one suite the
[community results site](../website/README.md) publishes. It is an ordinary suite
file — explicit cases, every workload field written out — and its seven cases are
the site's seven sections. The case name is the section's slug, its URL key and
the `scenario` of every published run, so the names are never renamed:

| Section | Slug | View | Plots | Curves | Input |
|---|---|---|---|---|---|
| Waveform | `waveform` | waveform | 1 | 1 | 10,000 points |
| Multi-curve waveform | `multi-curve` | waveform | 1 | 10 | 10,000 points per curve |
| Multi-plot waveform | `multi-plot` | waveform | 2 | 5 | 10,000 points per curve |
| Scalar image | `scalar-image` | image | 1 | — | 512 × 512 scalar |
| RGB image | `rgb-image` | image | 1 | — | 512 × 512 RGB |
| Multiple scalar images | `multi-image` | image | 4 | — | 512 × 512 scalar each |
| Large scalar image | `large-image` | image | 1 | — | 2048 × 2048 scalar |

Fixed conditions for every section: 60 Hz target rate, the Rust source, streaming
delivery, waveform `replace` mode, `append_count` 1000, seed 42, 5 s warmup, 30 s
measurement, 3 repetitions, 2 s cooldown and `order_seed` 42. The suite lists all
nine frontends explicitly. Windows keep the frontends' default 1100 × 820 logical
size — that is not a suite field, so the plot areas recorded in each run's
metadata are the evidence of what was actually rendered.

Run it with `--baseline`, which selects the file and refuses the overrides that
would change what is measured (`--duration`, `--warmup`, `--cooldown`,
`--repetitions`, `--limit`, `--modes`, `--backends` and `--headless`). Besides
the preview flags `--dry-run` and `--json`, only `--frontends`, `--output`,
`--display-context` and `--browser-executable` may be combined with it (a
different `--suite` is refused too), so a campaign can cover any subset of the
frontends:

```sh
./scripts/plotbench run --baseline --dry-run
./scripts/plotbench run --baseline --frontends pyqtgraph matplotlib --output results/baseline \
  --display-context "internal display, 120 Hz fixed, 2x scale, window centered"
```

The full suite expands to 189 runs (7 sections × 9 frontends × 3 repetitions);
`--dry-run` prints the schedule and nominal time for the frontends you chose.
Opening the same file with `--suite scenarios/baseline.json` keeps every override
available for local experiments, but such campaigns, like edited copies saved from
the matrix editor into `scenarios_custom/`, cannot be published: the site checks
the campaign's structure, not its file name. A frontend that crashes before
reporting its metadata should be re-run alone as its own baseline campaign
rather than patched into the first one.

## Examples

`baseline.json` (the official seven-section comparison above), `smoke.json` (short
combined views, including one two-plot, two-curve, two-image case),
`isolated-smoke.json` (separate plots), `stress-smoke.json` (large functional
checks), `multi-plot-smoke.json` (short multi-plot and multi-curve checks),
`standard.json` (large sweep), `streaming-comparison.json` (focused streaming
comparison), `beamline-dashboard.json` (realistic operator windows with several
plots and curves each), `multi-plot-sweep.json` (curve, waveform-plot and
image-plot count sweep), and `backend-probe.json` (receiver-only Rust source probe;
select both backends explicitly for a source comparison). Always preview large
suites; for example:

```sh
./scripts/plotbench run --suite scenarios/baseline.json --dry-run
./scripts/plotbench run --suite scenarios/multi-plot-smoke.json --dry-run
./scripts/plotbench run --suite scenarios/beamline-dashboard.json --dry-run
./scripts/plotbench run --suite scenarios/multi-plot-sweep.json --dry-run
```
