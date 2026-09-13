---
name: interpret-results
description: Read a Plotbench results directory and explain it — which runs are comparable, what the numbers mean, what failed, and where the source or transport limited the rate — without over-claiming. Use when asked to summarize, compare or explain benchmark results, a report, or a results/ folder.
license: BSD-3-Clause
---

# Interpret benchmark results

Plotbench keeps every campaign under `results/<name>/`. Read the evidence before
concluding anything: the reports are designed to keep unlike things separate, and
the most common mistakes are ranking across them or misnaming the metric.

## What a results directory contains

- `report.html` — compact charts. `report-extended.html` — complete evidence:
  failures, source limitations and per-stage timings. Both work offline.
- `suite.json` — the exact suite that ran. `summary.json` and `summary.csv` — one
  row per run.
- `run-NNNN/` per run: `run.json` (status, frontend, backend, mode, repetition,
  config, provenance), `measurements.jsonl` (per-update samples), `source.jsonl`
  (source-side delivery, deadline misses, replaced frames), `resources.jsonl`,
  `host.json` (machine and display context), `frontend.log`, `server.log`.

Details are in `docs/reports.md`. To regenerate the HTML and summaries from the
raw files:
```sh
./scripts/plotbench report results/my-comparison
```
Add `--probe` for a receiver-only probe campaign.

## Steps

1. **Establish what ran.** From `suite.json` and `summary.json`, list every
   frontend × source × mode × workload × repetition and its status. Failed,
   interrupted and diagnostic runs stay in the report on purpose — say what
   they were.
2. **Group only like with like.** Compare runs that share the same source
   backend, delivery mode, workload, build and display/runtime context. Different
   sources or modes are separate result sets, never one ranking.
3. **Name the metric correctly.** The headline is **submitted updates per second**
   — frames the adapter accepted into its update path — not displayed FPS. Adapter
   timing boundaries differ, and CPU/API return times are not GPU completion or
   presentation times. Say so wherever a number could be misread.
4. **Check for source-side limits.** In `source.jsonl`, deadline misses and
   replaced (dropped) frames mean the source or transport capped the rate, not the
   renderer. A receiver-only probe isolates that
   (`./scripts/plotbench probe --suite scenarios/backend-probe.json`); replay mode
   removes live generation and transport from the timed window.
5. **State the caveats explicitly.** Short smoke runs are functional checks, not
   stable rankings. Headless and offscreen runs are diagnostics. Missing
   observations are missing, not zero. Only the OS/display combinations recorded
   in `docs/validation.md` are validated.
6. **Deliver.** The comparable groups with their numbers, what failed and why,
   the limits to comparison, and links to `report.html`, `report-extended.html`
   and the raw directory.
