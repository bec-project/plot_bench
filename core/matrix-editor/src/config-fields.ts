// Workload field metadata, grouped by the plot kind they belong to so the form
// only ever shows relevant controls. The flat suite schema is unchanged; this is
// purely a presentation grouping over the same Config keys.

export type FieldKind = 'number' | 'rate' | 'enum';

export interface FieldSpec {
  key: string;
  label: string;
  kind: FieldKind;
  hint?: string;
}

export const ENUMS: Record<string, string[]> = {
  view: ['waveform', 'image', 'both'],
  waveform_mode: ['replace', 'append'],
  image_mode: ['scalar', 'rgb'],
};

export const SHARED_FIELDS: FieldSpec[] = [
  { key: 'hz', label: 'Target rate', kind: 'rate', hint: 'Hz' },
  { key: 'seed', label: 'Data seed', kind: 'number' },
];

export const WAVEFORM_FIELDS: FieldSpec[] = [
  { key: 'points', label: 'Waveform points', kind: 'number' },
  { key: 'waveform_mode', label: 'Waveform mode', kind: 'enum' },
  { key: 'append_count', label: 'Append count', kind: 'number', hint: 'append mode' },
];

export const IMAGE_FIELDS: FieldSpec[] = [
  { key: 'width', label: 'Image width', kind: 'number', hint: 'px' },
  { key: 'height', label: 'Image height', kind: 'number', hint: 'px' },
  { key: 'image_mode', label: 'Image mode', kind: 'enum' },
];

// A square-image shorthand offered on group base configs only.
export const RESOLUTION_FIELD: FieldSpec = {
  key: 'resolution',
  label: 'Square resolution',
  kind: 'number',
  hint: 'px, sets width & height',
};

export const ALL_AXES: string[] = [
  'view',
  'hz',
  'points',
  'append_count',
  'waveform_mode',
  'width',
  'height',
  'image_mode',
  'seed',
  'resolution',
];

export function showsWaveform(view: string): boolean {
  return view === 'waveform' || view === 'both';
}

export function showsImage(view: string): boolean {
  return view === 'image' || view === 'both';
}

// The field groups visible for a workload with the given view.
export function visibleGroups(
  view: string,
  includeResolution = false
): Array<{ title: string; fields: FieldSpec[] }> {
  const groups: Array<{ title: string; fields: FieldSpec[] }> = [
    { title: 'Rate & seed', fields: SHARED_FIELDS },
  ];
  if (showsWaveform(view)) groups.push({ title: 'Waveform', fields: WAVEFORM_FIELDS });
  if (showsImage(view)) {
    const image = includeResolution ? [RESOLUTION_FIELD, ...IMAGE_FIELDS] : IMAGE_FIELDS;
    groups.push({ title: 'Image', fields: image });
  }
  return groups;
}

export const MAX_SAFE = Number.MAX_SAFE_INTEGER;

export function unsafeInteger(text: string): boolean {
  const n = Number(text);
  return text.trim() !== '' && Number.isFinite(n) && Math.abs(n) > MAX_SAFE;
}
