import type { ComponentChildren } from 'preact';
import { useEffect, useRef, useState } from 'preact/hooks';
import { ENUMS, MAX_SAFE, visibleGroups } from '../config-fields';
import type { ComponentStatus, Config, ConfigValue } from '../types';
import { InfoTip } from './infotip';

type Emitted = ConfigValue | undefined;

// Parse editor text into a stored value. Numbers that JavaScript cannot hold
// exactly are kept as their raw string so the schema rejects them instead of
// silently rounding — matching the CLI's larger-integer guarantee.
function parseNumeric(text: string, allowDecimal: boolean): { value: Emitted; error?: string } {
  const trimmed = text.trim();
  if (trimmed === '') return { value: undefined };
  const clean = allowDecimal ? /^-?\d*\.?\d+$/ : /^-?\d+$/;
  if (!clean.test(trimmed)) {
    return { value: text, error: allowDecimal ? 'Enter a number.' : 'Enter a whole number.' };
  }
  const n = Number(trimmed);
  if (!Number.isFinite(n)) return { value: text, error: 'Enter a finite number.' };
  if (Math.abs(n) > MAX_SAFE) {
    return {
      value: text,
      error: `Too large for the editor (±${MAX_SAFE.toLocaleString()}). Use the CLI for larger integers.`,
    };
  }
  return { value: n };
}

export function Field(props: {
  label: string;
  hint?: string;
  tip?: string;
  children: ComponentChildren;
  error?: string;
}) {
  // A div (not a label) so an in-caption InfoTip does not toggle the control; the
  // inputs carry their own aria-label for accessible naming.
  return (
    <div class="field">
      <span class="field-label">
        {props.label}
        {props.hint ? <span class="field-hint"> · {props.hint}</span> : null}
        {props.tip ? <InfoTip text={props.tip} /> : null}
      </span>
      {props.children}
      {props.error ? <span class="field-error">{props.error}</span> : null}
    </div>
  );
}

export function NumberField(props: {
  label: string;
  hint?: string;
  tip?: string;
  value: ConfigValue | undefined;
  placeholder?: string | number;
  allowDecimal?: boolean;
  onChange: (value: Emitted) => void;
}) {
  const [text, setText] = useState(props.value === undefined ? '' : String(props.value));
  const emitted = useRef<Emitted>(props.value);

  useEffect(() => {
    // Resync only when the value changed elsewhere (preset load, JSON apply).
    if (props.value !== emitted.current) {
      setText(props.value === undefined ? '' : String(props.value));
      emitted.current = props.value;
    }
  }, [props.value]);

  const parsed = parseNumeric(text, props.allowDecimal ?? false);
  return (
    <Field label={props.label} hint={props.hint} tip={props.tip} error={parsed.error}>
      <input
        type="text"
        inputMode={props.allowDecimal ? 'decimal' : 'numeric'}
        value={text}
        placeholder={props.placeholder === undefined ? 'Optional' : String(props.placeholder)}
        aria-label={props.label}
        aria-invalid={parsed.error ? 'true' : undefined}
        onInput={(event) => {
          const next = (event.target as HTMLInputElement).value;
          setText(next);
          const result = parseNumeric(next, props.allowDecimal ?? false);
          emitted.current = result.value;
          props.onChange(result.value);
        }}
      />
    </Field>
  );
}

export function SelectField(props: {
  label: string;
  hint?: string;
  tip?: string;
  value: ConfigValue | undefined;
  options: string[];
  defaultLabel: string;
  onChange: (value: Emitted) => void;
}) {
  return (
    <Field label={props.label} hint={props.hint} tip={props.tip}>
      <select
        value={props.value === undefined ? '' : String(props.value)}
        aria-label={props.label}
        onChange={(event) => {
          const next = (event.target as HTMLSelectElement).value;
          props.onChange(next === '' ? undefined : next);
        }}
      >
        <option value="">{props.defaultLabel}</option>
        {props.options.map((option) => (
          <option value={option}>{option}</option>
        ))}
      </select>
    </Field>
  );
}

export function TextField(props: {
  label: string;
  hint?: string;
  value: string;
  placeholder?: string;
  onInput: (value: string) => void;
}) {
  return (
    <Field label={props.label} hint={props.hint}>
      <input
        type="text"
        value={props.value}
        placeholder={props.placeholder}
        aria-label={props.label}
        onInput={(event) => props.onInput((event.target as HTMLInputElement).value)}
      />
    </Field>
  );
}

export function ChipGroup(props: {
  legend: string;
  options: string[];
  selected: string[];
  disabled?: boolean;
  legendTip?: string;
  tips?: Record<string, string>;
  status?: Record<string, ComponentStatus>;
  onToggle: (value: string, checked: boolean) => void;
}) {
  return (
    <fieldset class="chip-group" disabled={props.disabled}>
      <legend>
        {props.legend}
        {props.legendTip ? <InfoTip text={props.legendTip} /> : null}
      </legend>
      <div class="chips">
        {props.options.map((option) => {
          const checked = props.selected.includes(option);
          const status = props.status?.[option];
          const missing = status ? !status.installed : false;
          const title = [
            props.tips?.[option],
            status
              ? status.installed
                ? 'Installed.'
                : `Not installed — ./scripts/setup ${status.setup}`
              : undefined,
          ]
            .filter(Boolean)
            .join(' ');
          return (
            <label
              class={`chip${checked ? ' chip-on' : ''}${missing ? ' chip-missing' : ''}`}
              title={title || undefined}
            >
              <input
                type="checkbox"
                value={option}
                checked={checked}
                onChange={(event) => props.onToggle(option, (event.target as HTMLInputElement).checked)}
              />
              {status ? (
                <span
                  class={`dot ${status.installed ? 'dot-ok' : 'dot-missing'}`}
                  aria-hidden="true"
                />
              ) : null}
              {option}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

// View-aware grouped workload fields: only the controls relevant to the plot
// kind are rendered, each group in its own labelled block of even rows.
export function ConfigFields(props: {
  config: Config;
  defaults: Record<string, ConfigValue>;
  includeResolution?: boolean;
  onChange: (config: Config) => void;
}) {
  const view = String(props.config.view ?? props.defaults.view);
  const groups = visibleGroups(view, props.includeResolution);

  const set = (key: string, value: Emitted) => {
    const next: Config = { ...props.config };
    if (value === undefined) delete next[key];
    else next[key] = value;
    props.onChange(next);
  };

  return (
    <div class="config-groups">
      {groups.map((group) => (
        <fieldset class="config-group">
          <legend>{group.title}</legend>
          <div class="field-grid">
            {group.fields.map((spec) => {
              const value = props.config[spec.key];
              const fallback = props.defaults[spec.key];
              if (spec.kind === 'enum') {
                return (
                  <SelectField
                    label={spec.label}
                    hint={spec.hint}
                    tip={spec.tip}
                    value={value}
                    options={ENUMS[spec.key]}
                    defaultLabel={`Default (${fallback})`}
                    onChange={(next) => set(spec.key, next)}
                  />
                );
              }
              return (
                <NumberField
                  label={spec.label}
                  hint={spec.hint}
                  tip={spec.tip}
                  value={value}
                  allowDecimal={spec.kind === 'rate'}
                  placeholder={fallback}
                  onChange={(next) => set(spec.key, next)}
                />
              );
            })}
          </div>
        </fieldset>
      ))}
    </div>
  );
}
