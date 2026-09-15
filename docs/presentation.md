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
   `plot_viewports` as the data area of the first plot of each kind (all cells are
   equal) and adds `plot_counts` and `curves`.

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
Toolkit-specific axis layout and font rasterization can differ. Actual plot areas
remain recorded in metadata; similar appearance does not imply identical raster
workload or change the documented measurement boundaries.

For presentation screenshots, use the official baseline's `waveform` section
(60 Hz, one curve of 10,000 points in replace mode) for waveform captures and its
`scalar-image` section (60 Hz, a 512 × 512 scalar image) for image captures; the
source controls can switch a running demo between the two workloads. Capture only
for visual QA, outside performance measurements.
