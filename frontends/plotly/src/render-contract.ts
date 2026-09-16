/** data-area-v2; keep in sync with core/plotbench/render_contract.py. */
export function dataSlot(width: number, height: number, count: number, image = false): [number, number] {
  const columns = Math.ceil(Math.sqrt(count));
  const rows = Math.ceil(count / columns);
  const [horizontal, vertical] = image ? (count > 1 ? [16, 16] : [96, 100]) : [100, 120];
  return [Math.max(1, Math.floor((width - 48 - 16 * (columns - 1)) / columns - horizontal)),
    Math.max(1, Math.floor((height - 220 - 16 * (rows - 1)) / rows - vertical))];
}
