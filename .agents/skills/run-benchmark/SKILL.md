---
name: run-benchmark
description: Run a Plotbench benchmark campaign from a natural-language request — run the official baseline unmodified when the result must be publishable, otherwise translate the request into a suite JSON; preflight the environment, dry-run and report the schedule, smoke-check, run the sequential campaign, export a baseline campaign for the results site and deliver the report links. Use when asked to benchmark, compare plotting frontends, measure update rates, publish results, or run a smoke, baseline, standard or custom suite.
license: BSD-3-Clause
---

# Run a benchmark campaign

Plotbench compares plotting frontends under one shared source. This is the
procedure for turning a request into a valid, reproducible campaign. The rules it
enforces are in `AGENTS.md` ("Running a requested benchmark" and "Measurement
invariants"); read that file first if you have not.

## Steps

1. **Decide whether the result must be publishable.** If the user wants the
   campaign on the community results site, there is nothing to translate: the
   site publishes complete campaigns of the official baseline suite
   (`scenarios/baseline.json`: seven sections at 60 Hz, Rust source, streaming,
   3 × 30 s) and nothing else. Run it unmodified with `--baseline`, narrowing it
   only with `--frontends`; the flag refuses `--duration`, `--warmup`,
   `--cooldown`, `--repetitions`, `--limit`, `--modes`, `--backends` and
   `--headless`, and any of those would make the campaign unpublishable anyway.
   Skip to step 2 with that command. See "The official baseline suite" in
   `docs/suites.md`.

   Otherwise **translate the request into a suite JSON.** Start from a bundled
   scenario in `scenarios/` or an example in `docs/suites.md`, and save the
   result under `scenarios_custom/` (git-ignored). Keep hardware-specific
   settings — display context, browser paths — out of the file. Fields and
   limits: `docs/suites.md`.
   Besides rate, points, image size and modes, a workload can hold several plots
   per window: `waveform_plots` (1–16) waveform plots with `curves` (1–64) curves
   each and `image_plots` (1–16) image plots; all three work as group matrix axes.
   For "several plots/curves per window" requests start from
   `scenarios/multi-plot-smoke.json`, `scenarios/beamline-dashboard.json` or
   `scenarios/multi-plot-sweep.json`; the standard `scenarios/smoke.json` also
   contains one multi-plot case.
   The matrix editor (`./scripts/plotbench matrix`) writes the same JSON and shows
   the run count; stop it before any formal run.

2. **Preflight only the components the suite uses.** Substitute its frontends and
   backends:
   ```sh
   ./scripts/plotbench doctor --frontends pyqtgraph --backends rust
   ```
   If something is missing, install it with `./scripts/setup rust pyqtgraph`
   (see the `environment-doctor` skill), then run doctor again.

3. **Dry-run and report the schedule before measuring anything.**
   ```sh
   ./scripts/plotbench run --suite scenarios_custom/my-suite.json --dry-run
   ./scripts/plotbench run --suite scenarios_custom/my-suite.json --dry-run --json
   ./scripts/plotbench run --baseline --frontends pyqtgraph --dry-run
   ```
   Tell the user the number of runs and the nominal time, and that startup, replay
   preload and cooldown add to it. Ask for missing workload or time-budget details
   only if they materially change the experiment; existing authorization to run the
   chosen campaign stands.

4. **Smoke-check first.** One repetition, short windows, a fresh output directory:
   ```sh
   ./scripts/plotbench run --suite scenarios_custom/my-suite.json \
     --warmup 1 --duration 3 --repetitions 1 --output results/quick-check
   ```
   For a baseline campaign, open the same file with `--suite` so the shortened
   timings are allowed; this quick pass covers the seven sections but is a
   functional check only and can never be published:
   ```sh
   ./scripts/plotbench run --suite scenarios/baseline.json --frontends pyqtgraph \
     --warmup 1 --duration 3 --repetitions 1 --output results/baseline-quick-check
   ```
   Confirm every combination starts and completes. For multi-plot workloads,
   `scenarios/multi-plot-smoke.json` is the ready-made short check. Screenshots
   are visual QA only and must be taken outside measured windows.

5. **Run the campaign** sequentially on a controlled, visible desktop, into a new
   output directory, recording the display you used:
   ```sh
   ./scripts/plotbench run --suite scenarios_custom/my-suite.json \
     --output results/my-comparison \
     --display-context "internal display, 120 Hz, 2x scale, window centered"
   ./scripts/plotbench run --baseline --frontends pyqtgraph \
     --output results/baseline \
     --display-context "internal display, 120 Hz fixed, 2x scale, window centered"
   ```
   Watch the `[i/N]` progress with elapsed time, ETA and the pass/fail tally. If a
   run fails, stop and report; never switch to headless, software rendering or a
   different display protocol to get past it. For a baseline campaign, fix the
   refresh rate and display scale for the whole campaign (an adaptive refresh
   splits repetitions into different contexts and the campaign is rejected as
   smoke), keep failed runs (they are published as evidence), and if a frontend
   crashes before reporting its metadata, re-run that frontend alone as its own
   baseline campaign instead of patching the first one.

6. **Export a publishable campaign.** Only for `--baseline` campaigns: the
   exporter refuses everything else early with "Only campaigns of the official
   baseline suite can be published", and it also refuses interrupted campaigns,
   smoke/diagnostic classifications (headless, X11, unknown display) and runs
   with an unknown commit or a dirty checkout.
   ```sh
   npm --prefix website run export -- --input ../results/baseline/summary.json
   npm --prefix website run validate
   ```
   Review the printed public fields, then hand the user the JSON under
   `website/results/` to submit through a pull request
   (`website/results/README.md`). A second campaign on the same day needs a
   suffix on the proposed `<cpu>-<os>-<yyyymmdd>-plotbench-baseline` ID.

7. **Deliver.** Link `report.html` (compact), `report-extended.html` (complete
   evidence), `suite.json` and the raw result directory. State exactly which
   frontend × source × mode combinations ran, which failed, and what limits the
   comparison. The `interpret-results` skill covers how to read them.

## Never

- Pool sources, modes, builds or display contexts, or present one as another.
- Call submitted updates per second "FPS" — it is not the displayed frame rate.
  One update covers every plot and curve of a frame; do not multiply it by the
  plot count.
- Reuse an output directory (existing campaigns are protected) or discard failed
  attempts; keep every raw file.
- Edit source, dependencies or rendering settings mid-campaign; rebuild changed
  compiled components before benchmarking them.
- Run a large sweep just to validate a documentation or config change — use
  `--dry-run` or a smoke run.
