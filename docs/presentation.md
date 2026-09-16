# Presentation style

All demos use the same visual hierarchy while retaining their native rendering
implementation. The frontend name and renderer badge identify each implementation.

| Token | Value |
|---|---|
| Window background | `#0b141c` |
| Panel / plot background | `#111e28` |
| Panel border | `#253745` |
| Primary text | `#d8e6ed` |
| Secondary text | `#8fa7b6` |
| Accent / waveform | `#64dccc` |
| Error text | `#ffa7a7` |
| Default logical window | 1100 × 820 |
| Outer margin | 24 logical pixels |
| Panel gap | 14–18 logical pixels |

Use the platform sans-serif font for labels and a monospace face for numeric
indicators where practical. Panel corners and borders are subtle; avoid shadows,
animated decorations and gradients that add rendering work during measurements.
The image colormap remains the protocol's shared scientific color table.

## Layout

1. Header: “PLOTTING BENCHMARK”, frontend name, renderer / delivery-mode badges,
   connection state and a “Source controls” action.
2. Compact workload summary: target rate, waveform size and mode, image dimensions
   and mode, and a PLOTS control with checkable 1D / 2D buttons. Active buttons use
   the accent color; at least one plot stays enabled. Accessible names identify
   the waveform and image. Controls are locked during requests and recorded runs.
   When a workload has several plots or curves, the WAVEFORM item gains the suffix
   ` · 2 plots × 3 curves` (omitted when both counts are one) and the IMAGE item
   gains ` · 3 plots` when `image_plots` is greater than one, for example
   `10,000 · replace · 2 plots × 3 curves` and `256 × 256 · scalar · 3 plots`.
   Counts are pluralised grammatically: `1 plot × 3 curves`, `4 plots × 1 curve`,
   `3 plots` — never `1 plots` or `1 curves`. The report's workload labels follow
   the same rule.
3. Four performance indicators, in order: Submitted, Update time, Skipped, Receive
   age. Include units and show a dash for receive age in replay mode. Each value
   has a small muted parenthesized target line inside the existing metric card:
   target rate, one-period update budget, zero skipped frames, and an indicative
   one-period receive-age goal (N/A in replay). Targets follow the confirmed rate.
   Tooltips explain that these are guides and do not measure GPU/display deadlines.
4. A grid of plot cards, see [Plot grid](#plot-grid) below. With one waveform and
   one image plot this is the familiar pair of equal-width Waveform and Image
   cards; a single selected plot fills the available width. Titles and workload
   subtitles sit above plots.
5. Footer: “Submitted updates · not displayed FPS” and a concise renderer note.

## Plot grid

A workload may ask for `waveform_plots` waveform widgets (each drawing `curves`
curves) and `image_plots` image widgets. Every frontend arranges them with the same
language-neutral rule so that screenshots and physical plot areas stay comparable:

1. Order the visible plots waveform plots first (`Waveform 1..N`), then image plots
   (`Image 1..M`). `n = N + M` counts only the kinds enabled by the current view.
2. Use `columns = ceil(sqrt(n))` and `rows = ceil(n / columns)`, fill the grid
   row-major with equal cell sizes, and leave trailing cells empty. Hence n = 1 is
   1 × 1, n = 2 is two cards side by side as before, n = 3 and 4 are 2 × 2,
   n = 5 and 6 are 3 × 2 (three columns, two rows) and n = 9 is 3 × 3.
3. Title a plot `Waveform` or `Image` when it is the only one of its kind, else
   `Waveform 1`, `Waveform 2`, … and `Image 1`, `Image 2`, …. Subtitles keep the
   existing `points · mode` and `width × height · mode` forms; waveform plots add
   `· K curves` when `curves` is greater than one.
4. Rebuild the widget set when the source generation changes the counts. One
   update submission per frame covers all plots, and the recorded metadata keeps
   `plot_viewports` as the data area of the first plot of each kind and
   `plot_viewports_all` as the measured data areas of **every** plot, in plot order.
   It also records `plot_counts` and `curves`.

### Curve palette

Curve `c` of every waveform plot uses `CURVE_COLORS[c % 8]` from
`plotbench.palette`; curve 0 keeps the accent colour. Stroke width, antialiasing,
fixed axes (y in [-1.5, 1.5], x in [0, points − 1] for every curve of a plot), no
markers and no decimation are unchanged.

| Curve | Colour |
|---|---|
| 0 (and 8, 16, …) | `#64dccc` |
| 1 | `#f5c76e` |
| 2 | `#7aa6ff` |
| 3 | `#ff9d7a` |
| 4 | `#c39bff` |
| 5 | `#9be564` |
| 6 | `#ff7ab8` |
| 7 | `#6ee7ff` |

The source control page uses the same colors and typography. The native demos open
this page in a browser; Plotly also provides controls within its application.
The shared source page includes update-rate presets (1, 5, 10, 15, 24, 30, 60, 90,
and 120 Hz), square image sizes from 256 × 256 through 4096 × 4096, and video sizes
from VGA through 4K UHD. Presets populate the editable rate or width/height fields;
select **Apply workload** to publish the changes. Custom values remain available.
The dropdowns follow draft values and external source changes without resetting the
selected 1D/2D view or other unsaved edits. Both source backends serve this same page.
Toolkit-specific axis layout and font rasterization can differ. The data rectangle
follows the versioned contract below; this does not change measurement boundaries.

For presentation screenshots, use the official baseline's `waveform` section
(60 Hz, one curve of 10,000 points in replace mode) for waveform captures and its
`scalar-image` section (60 Hz, a 512 × 512 scalar image) for image captures; the
source controls can switch a running demo between the two workloads. Capture only
for visual QA, outside performance measurements.


## Data-area contract (`data-area-v1`)

Adapters derive a common data-area slot from the **actual logical window content
size**, independently of native header, title, axis and font measurements. With
window size `W × H`, `columns = ceil(sqrt(n))`, and `rows = ceil(n / columns)`:

```text
slot_width  = max(1, floor((W - 48  - 16 × (columns - 1)) / columns - 120))
slot_height = max(1, floor((H - 340 - 16 × (rows    - 1)) / rows    - 140))
```

The reserves leave space for the application controls, per-card captions and
native axes; they are layout budgets, not additional rendered data. Each waveform
uses the entire slot. Each image fits inside it with a uniform scale
`min(slot_width / image_width, slot_height / image_height)`; cropping and stretching
are forbidden. Axes must describe that fitted image rectangle, not its padding.
These rules apply equally to scalar and RGB images, including non-square inputs.

At the default 1100 × 820 window, one plot has a 932 × 340 logical-pixel slot;
two plots have 398 × 340 each; four have 398 × 92 each. A square image occupies
340 × 340 or 92 × 92 respectively. Multiply by the recorded device pixel ratio
for physical dimensions. Different display scales remain different comparison
contexts. Native chrome and glyph rasterization are not normalized.

Every adapter reports `render_contract: "data-area-v1"` and independently measured
`plot_viewports_all` in physical pixels, rather than echoing requested sizes.
Reports check **every measured-window batch and every plot**, accepting at most
1.5 physical pixels of rounding per dimension. Missing, non-finite, extra or
mismatched areas exclude the run with `render-contract-mismatch`; raw samples and
diagnostics remain available. A window whose slot is smaller than 32 logical
pixels in either dimension is too small for a comparable run. Such dense grids
need a larger window. Unversioned historical results remain labelled as legacy
fixed-window runs and are never pooled with v1 observations.

Rendering settings retain full authoritative data: fixed waveform ranges, a
one-physical-pixel stroke, no markers, no automatic decimation or downsampling,
nearest-neighbor image sampling, the shared 256-entry scalar LUT and fixed [0,1]
levels. Antialiasing is disabled where exposed by the renderer. Plotly `scattergl`
retains its renderer-default edge treatment: its public
[trace API](https://plotly.com/javascript/reference/scattergl/) exposes no AA-off
setting. Its metadata records this exception rather than claiming AA equivalence.
Texture allocation/reuse and CPU/GPU conversion choices remain adapter-specific.
GPU completion, presentation and submitted-update timing are unchanged.
