// Section navigation and the small presentation helpers every page shares: the
// rail of seven sections, a section heading, list dividers, coverage chips, and
// the context words (commit, scale, refresh) that identify a record.
import type { ReactNode } from 'react';
import { SECTIONS, fixedConditions, type Section } from './baseline';
import { workloadLabel, type Run, type Workload } from './model';
import { Field, format } from './presentation';

export const shortCommit = (commit: string | null) =>
  commit ? commit.slice(0, 7) : 'commit not recorded';
export const scaleLabel = (ratio: number | null) =>
  ratio === null ? 'scale not recorded' : `${format(ratio, 2)}x`;
export const refreshLabel = (hz: number | null) =>
  hz === null ? 'refresh not recorded' : `${format(hz, 0)} Hz refresh`;
/** One line naming what separates records inside a section: revision and display. */
export function contextLine(context: Run['context']): string {
  return [
    `commit ${shortCommit(context.commit)}`,
    scaleLabel(context.pixel_ratio),
    refreshLabel(context.refresh_hz),
    context.display_protocol ?? 'protocol not recorded',
  ].join(' · ');
}
/** A compact workload description for tables: plots and curves, or image size and mode. */
export function layoutLabel(c: Workload): string {
  return c.view === 'image'
    ? `${c.image_plots} plot${c.image_plots === 1 ? '' : 's'} · ${c.width} × ${c.height} ${c.image_mode}`
    : `${c.waveform_plots} plot${c.waveform_plots === 1 ? '' : 's'} × ${c.curves} curve${c.curves === 1 ? '' : 's'} · ${c.points.toLocaleString()} points`;
}

export function SectionRail({
  counts,
  current,
  href,
  unit = 'group',
}: {
  /** Section slug → how many items the page shows for it; the sum feeds "All sections". */
  counts: ReadonlyMap<string, number>;
  current: Section | null;
  href: (slug: string | null) => string;
  unit?: string;
}) {
  const total = [...counts.values()].reduce((sum, n) => sum + n, 0);
  const plural = (n: number) => `${n} ${unit}${n === 1 ? '' : 's'}`;
  return (
    <nav className="section-rail" aria-label="Sections">
      <div className="section-rail-scroll">
        <a
          href={href(null)}
          className={current ? 'rail-link' : 'rail-link rail-on'}
          aria-current={current ? undefined : 'page'}
        >
          <span className="rail-title">All sections</span>
          <small>
            {total}
            <span className="sr-only"> {plural(total).split(' ')[1]}</span>
          </small>
        </a>
        {SECTIONS.map((s) => {
          const n = counts.get(s.slug) ?? 0,
            on = current?.slug === s.slug;
          return (
            <a
              key={s.slug}
              href={href(s.slug)}
              className={on ? 'rail-link rail-on' : 'rail-link'}
              aria-current={on ? 'page' : undefined}
            >
              <span className="rail-index">{s.index}</span>
              <span className="rail-title">{s.title}</span>
              <small>
                {n}
                <span className="sr-only"> {plural(n).split(' ')[1]}</span>
              </small>
            </a>
          );
        })}
      </div>
    </nav>
  );
}

export function SectionHead({ section, children }: { section: Section; children?: ReactNode }) {
  return (
    <header className="section-head">
      <p className="eyebrow">
        Section {section.index} of {SECTIONS.length}
      </p>
      <h2>{section.title}</h2>
      <p className="section-workload">{workloadLabel(section.config)}</p>
      <p className="muted small">{fixedConditions()}</p>
      {children}
    </header>
  );
}

export function SectionDivider({ section, href }: { section: Section; href?: string }) {
  return (
    <div className="section-divider">
      <span className="rail-index">{section.index}</span>
      <strong>{section.title}</strong>
      <small>{workloadLabel(section.config)}</small>
      {href && <a href={href}>Only this section</a>}
    </div>
  );
}

/** Seven chips, one per section, lit for the sections a host or collection covers. */
export function SectionCoverage({
  covered,
  href,
}: {
  covered: ReadonlySet<string>;
  href?: (slug: string) => string;
}) {
  const n = SECTIONS.filter((s) => covered.has(s.slug)).length;
  return (
    <ul className="coverage-chips" aria-label={`${n} of ${SECTIONS.length} sections covered`}>
      {SECTIONS.map((s) => {
        const on = covered.has(s.slug);
        const chip = (
          <>
            <span className="rail-index">{s.index}</span>
            <span>{s.title}</span>
          </>
        );
        return (
          <li key={s.slug} className={on ? 'chip chip-on' : 'chip'} title={s.title}>
            {on && href ? <a href={href(s.slug)}>{chip}</a> : chip}
          </li>
        );
      })}
    </ul>
  );
}

/** A labelled select whose empty option reads "All <plural>". */
export function Select({
  label,
  value,
  options,
  onChange,
  all,
}: {
  label: string;
  value: string;
  options: readonly (readonly [string, string])[];
  onChange: (v: string) => void;
  all: string;
}) {
  return (
    <Field label={label}>
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{all}</option>
        {options.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
    </Field>
  );
}

export function DateRange({
  filters,
  filter,
}: {
  filters: URLSearchParams;
  filter: (key: string, value: string) => void;
}) {
  return (
    <>
      <Field label="Acquired from (UTC)">
        <input
          aria-label="Acquired from (UTC)"
          type="date"
          value={filters.get('from') ?? ''}
          onChange={(e) => filter('from', e.target.value)}
        />
      </Field>
      <Field label="Acquired through (UTC)">
        <input
          aria-label="Acquired through (UTC)"
          type="date"
          value={filters.get('to') ?? ''}
          onChange={(e) => filter('to', e.target.value)}
        />
      </Field>
    </>
  );
}
