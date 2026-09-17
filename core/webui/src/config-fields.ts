// Workload field metadata, grouped by the plot kind they belong to so the form
// only ever shows relevant controls. The flat suite schema is unchanged; this is
// purely a presentation grouping over the same Config keys.

export type FieldKind = 'number' | 'rate' | 'enum';

export interface FieldSpec {
  key: string;
  label: string;
  kind: FieldKind;
  hint?: string;
  tip?: string;
}

export const ENUMS: Record<string, string[]> = {
  view: ['waveform', 'image', 'both'],
  waveform_mode: ['replace', 'append'],
  image_mode: ['scalar', 'rgb'],
};

// Short explanations surfaced as tooltips on options and section legends.
export const VIEW_TIP =
  'Which plot(s) this workload drives: a 1-D waveform, a 2-D image, or both together.';

export const OPTION_TIPS: Record<string, string> = {
  // frontends
  pyqtgraph: 'PyQtGraph — Qt, CPU raster rendering.',
  'pyqtgraph-gl': 'PyQtGraph with its OpenGL backend.',
  matplotlib: 'Matplotlib on the Qt Agg canvas.',
  qtgraphs: 'Qt Graphs (QML/Quick) renderer.',
  'qtgraphs-cpp': 'Qt Graphs via the native C++ SDK.',
  iced: 'Iced — native Rust GUI on wgpu.',
  jfreechart: 'JFreeChart — Java/Swing, synchronous Java2D charts and image annotation (macOS or Linux XWayland).',
  fyne: 'Fyne — Go GUI with custom CPU waveform rasterization and RGBA canvas images.',
  'fyne-wasm': 'Fyne WebAssembly — custom CPU waveform rasterization and RGBA canvas images displayed with browser WebGL.',
  plotly: 'Plotly.js in a controlled browser.',
  // backends
  python: 'The built-in Python source. Always available with a core install.',
  rust: 'The faster native Rust source. Needs ./scripts/setup rust.',
  // modes
  stream: 'Live frames delivered as the source produces them.',
  replay: 'A recording is preloaded, then played back at a fixed rate.',
  // enum config values
  replace: 'Each frame redraws the whole curve.',
  append: 'Each frame appends new samples to a rolling window.',
  scalar: 'Single-channel intensity image.',
  rgb: 'Three-channel colour image.',
};

export const GROUP_TIPS = {
  frontends: 'The plotting implementations to benchmark. Each renders the same frames independently.',
  backends: 'Where frames are generated — the Python source or the faster Rust source.',
  modes: 'How frames reach the renderer: live streaming, or replay of a preloaded recording.',
  kind: 'Frontend benchmark drives a renderer; Source receiver probe measures the source and delivery only, with no plotting.',
} as const;

export const SHARED_FIELDS: FieldSpec[] = [
  {
    key: 'hz',
    label: 'Target rate',
    kind: 'rate',
    hint: 'Hz',
    tip: 'Frames per second the source generates and submits. Capped at 120 Hz.',
  },
  {
    key: 'seed',
    label: 'Data seed',
    kind: 'number',
    tip: 'Seed for the deterministic data generator; the same seed reproduces identical frames.',
  },
];

export const WAVEFORM_FIELDS: FieldSpec[] = [
  {
    key: 'points',
    label: 'Waveform points',
    kind: 'number',
    tip: 'Number of samples in each waveform frame.',
  },
  {
    key: 'waveform_mode',
    label: 'Waveform mode',
    kind: 'enum',
    tip: 'replace redraws the whole curve each frame; append adds to a rolling window.',
  },
  {
    key: 'append_count',
    label: 'Append count',
    kind: 'number',
    hint: 'append mode',
    tip: 'In append mode, how many new samples are added per frame.',
  },
  {
    key: 'waveform_plots',
    label: 'Waveform plots',
    kind: 'number',
    tip: 'Number of waveform plot widgets in the window, each with its own data. Between 1 and 16.',
  },
  {
    key: 'curves',
    label: 'Curves per plot',
    kind: 'number',
    tip: 'Curves drawn in every waveform plot, each with distinct data. Between 1 and 64.',
  },
];

export const IMAGE_FIELDS: FieldSpec[] = [
  { key: 'width', label: 'Image width', kind: 'number', hint: 'px', tip: 'Image width in pixels.' },
  { key: 'height', label: 'Image height', kind: 'number', hint: 'px', tip: 'Image height in pixels.' },
  {
    key: 'image_mode',
    label: 'Image mode',
    kind: 'enum',
    tip: 'scalar sends a single intensity channel; rgb sends three colour channels.',
  },
  {
    key: 'image_plots',
    label: 'Image plots',
    kind: 'number',
    tip: 'Number of image plot widgets in the window, each with its own data. Between 1 and 16.',
  },
];

// A square-image shorthand offered on group base configs only.
export const RESOLUTION_FIELD: FieldSpec = {
  key: 'resolution',
  label: 'Square resolution',
  kind: 'number',
  hint: 'px',
  tip: 'Shorthand that sets both width and height to the same square size.',
};

export const ALL_AXES: string[] = [
  'view',
  'hz',
  'points',
  'append_count',
  'curves',
  'waveform_plots',
  'waveform_mode',
  'width',
  'height',
  'image_plots',
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
