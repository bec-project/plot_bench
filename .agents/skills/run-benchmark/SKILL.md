---
name: run-benchmark
description: Run a Plotbench benchmark campaign from a natural-language request — translate it into a suite JSON, preflight the environment, dry-run and report the schedule, smoke-check, then run the sequential campaign and deliver the report links. Use when asked to benchmark, compare plotting frontends, measure update rates, or run a smoke, standard or custom suite.
license: BSD-3-Clause
---

# Run a benchmark campaign

Plotbench compares plotting frontends under one shared source. This is the
procedure for turning a request into a valid, reproducible campaign. The rules it
enforces are in `AGENTS.md` ("Running a requested benchmark" and "Measurement
invariants"); read that file first if you have not.

## Steps

1. **Translate the request into a suite JSON.** Start from a bundled scenario in
   `scenarios/` or an example in `docs/suites.md`, and save the result under
   `scenarios_custom/` (git-ignored). Keep hardware-specific settings — display
   context, browser paths — out of the file. Fields and limits: `docs/suites.md`.
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
   Confirm every combination starts and completes. Screenshots are visual QA only
   and must be taken outside measured windows.

5. **Run the campaign** sequentially on a controlled, visible desktop, into a new
   output directory, recording the display you used:
   ```sh
   ./scripts/plotbench run --suite scenarios_custom/my-suite.json \
     --output results/my-comparison \
     --display-context "internal display, 120 Hz, 2x scale, window centered"
   ```
   Watch the `[i/N]` progress with elapsed time, ETA and the pass/fail tally. If a
   run fails, stop and report; never switch to headless, software rendering or a
   different display protocol to get past it.

6. **Deliver.** Link `report.html` (compact), `report-extended.html` (complete
   evidence), `suite.json` and the raw result directory. State exactly which
   frontend × source × mode combinations ran, which failed, and what limits the
   comparison. The `interpret-results` skill covers how to read them.

## Never

- Pool sources, modes, builds or display contexts, or present one as another.
- Call submitted updates per second "FPS" — it is not the displayed frame rate.
- Reuse an output directory (existing campaigns are protected) or discard failed
  attempts; keep every raw file.
- Edit source, dependencies or rendering settings mid-campaign; rebuild changed
  compiled components before benchmarking them.
- Run a large sweep just to validate a documentation or config change — use
  `--dry-run` or a smoke run.
