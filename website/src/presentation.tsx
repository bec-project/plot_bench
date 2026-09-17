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

// Rounded status tag: the matrix editor's `.pill`, with tones that reuse its
// danger and install-hint colours.
export function Pill({
  children,
  tone,
}: {
  children: ReactNode;
  tone?: 'success' | 'amber' | 'danger' | 'info';
}) {
  return <span className={tone ? `pill pill-${tone}` : 'pill'}>{children}</span>;
}

// A captioned control like the matrix editor's Field: a div rather than a label
// so the caption never toggles the control; every input carries its own aria-label.
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="field">
      <span className="field-label">
        {label}
        {hint ? <span className="field-hint"> · {hint}</span> : null}
      </span>
      {children}
    </div>
  );
}

/** "59.8–60" for a range, or the single value when both ends agree. */
export function rateRange(minimum: number, maximum: number): string {
  return minimum === maximum ? format(maximum) : `${format(minimum)}–${format(maximum)}`;
}
