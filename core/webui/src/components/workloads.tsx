import { ALL_AXES, ENUMS, MAX_SAFE } from '../config-fields';
import type { Case, CaseGroup, Config, ConfigValue } from '../types';
import { ConfigFields, Field } from './fields';
import { ViewSegmented } from './view-segmented';

function parseAxisValues(text: string, isEnum: boolean): ConfigValue[] {
  const parts = text
    .split(',')
    .map((value) => value.trim())
    .filter((value) => value !== '');
  if (isEnum) return parts;
  return parts.map((part) => {
    const n = Number(part);
    return Number.isFinite(n) && Math.abs(n) <= MAX_SAFE ? n : part;
  });
}

function AxesEditor(props: { group: CaseGroup; onChange: (group: CaseGroup) => void }) {
  const matrix = props.group.matrix;
  const used = Object.keys(matrix);
  const nextAxis = ALL_AXES.find((axis) => !used.includes(axis));

  const update = (matrixNext: Record<string, ConfigValue[]>) =>
    props.onChange({ ...props.group, matrix: matrixNext });

  const renameAxis = (from: string, to: string) => {
    const entries = Object.entries(matrix).map(([axis, values]) => [axis === from ? to : axis, values]);
    update(Object.fromEntries(entries));
  };

  return (
    <div class="axes">
      <div class="axes-head">
        <h4>Matrix axes</h4>
        <button
          type="button"
          class="btn-soft"
          disabled={!nextAxis}
          onClick={() => nextAxis && update({ ...matrix, [nextAxis]: [] })}
        >
          + Add axis
        </button>
      </div>
      {used.length === 0 ? (
        <p class="muted small">Add one or more axes; every combination becomes a workload.</p>
      ) : null}
      {used.map((key) => {
        const isEnum = Boolean(ENUMS[key]);
        return (
          <div class="axis-row">
            <Field label="Vary field">
              <select
                value={key}
                aria-label="Matrix field"
                onChange={(event) => renameAxis(key, (event.target as HTMLSelectElement).value)}
              >
                {ALL_AXES.map((axis) => (
                  <option value={axis} disabled={axis !== key && used.includes(axis)}>
                    {axis}
                  </option>
                ))}
                {ALL_AXES.includes(key) ? null : <option value={key}>{key}</option>}
              </select>
            </Field>
            <Field label="Values" hint="comma separated">
              <input
                type="text"
                value={(matrix[key] ?? []).join(', ')}
                aria-label={`Matrix ${key} values`}
                placeholder={isEnum ? ENUMS[key].join(', ') : 'e.g. 10000, 100000'}
                onInput={(event) =>
                  update({ ...matrix, [key]: parseAxisValues((event.target as HTMLInputElement).value, isEnum) })
                }
              />
            </Field>
            <button
              type="button"
              class="btn-remove"
              aria-label={`Remove ${key} axis`}
              onClick={() => {
                const rest = { ...matrix };
                delete rest[key];
                update(rest);
              }}
            >
              Remove
            </button>
          </div>
        );
      })}
    </div>
  );
}

export function WorkloadCard(props: {
  item: Case;
  defaults: Record<string, ConfigValue>;
  onChange: (item: Case) => void;
  onRemove: () => void;
}) {
  const view = String(props.item.config.view ?? props.defaults.view);
  return (
    <article class="card">
      <div class="card-head">
        <input
          type="text"
          class="card-name"
          value={props.item.name}
          aria-label="Workload name"
          placeholder="workload-name"
          onInput={(event) =>
            props.onChange({ ...props.item, name: (event.target as HTMLInputElement).value })
          }
        />
        <ViewSegmented
          value={view}
          onChange={(next) => props.onChange({ ...props.item, config: { ...props.item.config, view: next } })}
        />
        <button type="button" class="btn-remove" onClick={props.onRemove}>
          Remove
        </button>
      </div>
      <ConfigFields
        config={props.item.config}
        defaults={props.defaults}
        onChange={(config) => props.onChange({ ...props.item, config })}
      />
    </article>
  );
}

export function GroupCard(props: {
  group: CaseGroup;
  defaults: Record<string, ConfigValue>;
  onChange: (group: CaseGroup) => void;
  onRemove: () => void;
}) {
  const base: Config = props.group.base ?? {};
  const view = String(base.view ?? props.defaults.view);
  return (
    <article class="card">
      <div class="card-head">
        <input
          type="text"
          class="card-name"
          value={props.group.name}
          aria-label="Group name"
          placeholder="group-name"
          onInput={(event) =>
            props.onChange({ ...props.group, name: (event.target as HTMLInputElement).value })
          }
        />
        <ViewSegmented
          value={view}
          onChange={(next) => props.onChange({ ...props.group, base: { ...base, view: next } })}
        />
        <button type="button" class="btn-remove" onClick={props.onRemove}>
          Remove
        </button>
      </div>
      <div class="base-block">
        <p class="block-label">Base workload — axes below override these</p>
        <ConfigFields
          config={base}
          defaults={props.defaults}
          includeResolution
          onChange={(next) => props.onChange({ ...props.group, base: next })}
        />
      </div>
      <AxesEditor group={props.group} onChange={props.onChange} />
    </article>
  );
}
