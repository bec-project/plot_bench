import type { ReactNode } from 'react';

export const format = (n: number | null | undefined, digits = 1) =>
  n == null ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: digits });
export const date = (value: string) =>
  new Date(value).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
export function Badge({ children, tone = 'muted' }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
