export function metricHints(hz: number | undefined, replay: boolean) {
  const valid = hz !== undefined && Number.isFinite(hz) && hz > 0;
  const rate = valid ? Number(hz.toFixed(1)).toString() : '—';
  const budget = valid ? (1000 / hz).toFixed(2) : '—';
  return {
    submitted: `(target ${rate}/s)`,
    update: `(budget ≤${budget} ms)`,
    skipped: '(target 0)',
    age: replay ? '(N/A in replay)' : `(goal <${budget} ms)`,
  };
}
