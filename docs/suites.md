# Configure a benchmark matrix

Use the same JSON file from the CLI, a script, or the browser editor:

```sh
./scripts/plotbench matrix --suite scenarios/smoke.json
./scripts/plotbench run --suite my-suite.json --dry-run
./scripts/plotbench run --suite my-suite.json --dry-run --json
./scripts/plotbench run --suite my-suite.json --output results/my-comparison
```

The editor runs on loopback, imports/edits cases and Cartesian groups, previews the
expanded matrix and downloads validated JSON. It does not execute benchmarks or
generate input data. `--no-open` prints its URL without opening a browser. Stop it
with Ctrl+C before formal measurements.

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

## Fields and limits

Workload fields: `hz`, `points`, `append_count`, `width`, `height`,
`waveform_mode` (`replace`/`append`), `image_mode` (`scalar`/`rgb`), `view`
(`waveform`/`image`/`both`) and `seed`. `generation` is source-managed; do not use it
as an experiment axis. Unspecified fields use the shared `Config` defaults.

Rate must be positive and at most 120 Hz. Dimensions and counts must be positive
integers; append count cannot exceed the window size. Limits are 10 million
waveform points, 8192 pixels per image axis and 256 MiB per frame. Invalid or empty
matrices fail before launching processes. These are input bounds, not performance
guarantees. A suite is limited to 10,000 expanded cases and 100,000 runs to prevent
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

Examples: `smoke.json` (short combined views), `isolated-smoke.json` (separate
plots), `stress-smoke.json` (large functional checks), `standard.json` (large sweep),
`streaming-comparison.json` (focused streaming comparison), and
`backend-probe.json` (receiver-only source comparison). Always preview large suites.
