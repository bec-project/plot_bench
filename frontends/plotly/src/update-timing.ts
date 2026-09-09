export interface AdapterTiming {
  update_ms: number;
  conversion_ms: number;
  draw_ms: number;
  update_complete_ms: number;
}

/** Keep synchronous submission separate from elapsed time through library completion. */
export async function submitUpdates(started: number, converted: number,
  submit: () => Promise<unknown>[]): Promise<AdapterTiming> {
  const promises = submit();
  const submitted = performance.now();
  await Promise.all(promises);
  const completed = performance.now();
  return {
    update_ms: submitted - started,
    conversion_ms: converted - started,
    draw_ms: submitted - converted,
    update_complete_ms: completed - started,
  };
}
