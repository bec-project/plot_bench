# Plotbench all-frontend baseline, 2026-09-16

This branch preserves a public **diagnostic evidence package** from the completed
189-run official baseline. All nine frontends ran the seven sections with three
repetitions each; 189 runs passed and none failed. Nine large-image comparison
groups were source limited.

The original acquisition recorded a **modified checkout** (`git.dirty: true`),
and JFreeChart used **XWayland** while the other frontends used native Wayland.
The original provenance is retained in `public-summary.json`. This package is
**not** an accepted `website/results/` submission and does not change the
historical checkout state.

- `report.html`: compact offline report.
- `summary.csv`: all 189 run-level metrics.
- `public-summary.json`: selected run metrics, comparison groups, campaign
  provenance, and SHA-256 of the unchanged local `summary.json`.
- `baseline.json`: official workload specification.

Raw per-update logs, extended report, local filesystem paths, and host identifiers
are retained outside this branch. Submitted updates per second are not displayed FPS.
Do not pool JFreeChart's XWayland path with native Wayland results.
