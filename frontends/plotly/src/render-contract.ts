/** data-area-v1; keep in sync with core/plotbench/render_contract.py. */
export function dataSlot(width: number, height: number, count: number): [number, number] {
  const columns = Math.ceil(Math.sqrt(count));
  const rows = Math.ceil(count / columns);
  return [Math.max(1, Math.floor((width - 48 - 16 * (columns - 1)) / columns - 120)),
    Math.max(1, Math.floor((height - 340 - 16 * (rows - 1)) / rows - 140))];
}
