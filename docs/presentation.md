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
3. Four performance indicators, in order: Submitted, Update time, Skipped, Receive
   age. Include units and show a dash for receive age in replay mode. Each value
   has a small muted parenthesized target line inside the existing metric card:
   target rate, one-period update budget, zero skipped frames, and an indicative
   one-period receive-age goal (N/A in replay). Targets follow the confirmed rate.
   Tooltips explain that these are guides and do not measure GPU/display deadlines.
4. Equal-width Waveform and Image cards in the combined view. A single selected
   plot fills the available width. Titles and workload subtitles sit above plots.
5. Footer: “Submitted updates · not displayed FPS” and a concise renderer note.

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

For presentation screenshots, use the smoke suite's replacement/scalar workload:
30 Hz, 10,000 waveform points, a 512 × 512 scalar image, and the combined view.
Capture only for visual QA, outside performance measurements.
