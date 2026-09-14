package main

import (
	"fmt"
	"image/color"
	"math"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/canvas"
)

// visiblePlots returns the waveform and image widget counts enabled by the view.
func visiblePlots(c Config) (waveforms, images int) {
	if c.View != "image" {
		waveforms = c.WaveformPlots
	}
	if c.View != "waveform" {
		images = c.ImagePlots
	}
	return waveforms, images
}

// gridColumns implements the shared layout rule: columns = ceil(sqrt(n)), rows =
// ceil(n / columns), filled row-major with equal cells (n=2 → 2×1, n=3 → 2×2, n=5 → 3×2).
func gridColumns(n int) int {
	return max(1, int(math.Ceil(math.Sqrt(float64(n)))))
}

// padGrid appends empty placeholders so the grid has a whole number of rows and
// trailing cells stay empty but equally sized.
func padGrid(objects []fyne.CanvasObject, columns int) []fyne.CanvasObject {
	for len(objects)%columns != 0 {
		objects = append(objects, canvas.NewRectangle(color.Transparent))
	}
	return objects
}

// plotTitle is `Waveform` / `Image` for a single widget of that kind, else numbered from 1.
func plotTitle(kind string, index, count int) string {
	if count == 1 {
		return kind
	}
	return fmt.Sprintf("%s %d", kind, index+1)
}

// waveformSubtitle keeps the fixed-range legend and adds `· K curves` when curves > 1.
func waveformSubtitle(c Config) string {
	curves := ""
	if c.Curves > 1 {
		curves = fmt.Sprintf(" · %d curves", c.Curves)
	}
	return fmt.Sprintf("%d points · %s%s     x: 0 … %d     y: −1.5 … 1.5", c.Points, c.WaveformMode, curves, c.Points-1)
}

func imageSubtitle(c Config) string {
	return fmt.Sprintf("%d×%d · %s · nearest neighbour · levels 0 … 1", c.Width, c.Height, c.ImageMode)
}

// plural renders `1 plot` / `4 plots`, `1 curve` / `3 curves`.
func plural(n int, noun string) string {
	if n == 1 {
		return fmt.Sprintf("%d %s", n, noun)
	}
	return fmt.Sprintf("%d %ss", n, noun)
}

// workloadText is the HUD workload strip: `2 plots × 3 curves` (pluralised
// grammatically, e.g. `1 plot × 3 curves`, `4 plots × 1 curve`) follows the waveform
// item when either exceeds 1 and `3 plots` follows the image item when image_plots > 1.
func workloadText(c Config) string {
	wave := fmt.Sprintf("%d points / %s", c.Points, c.WaveformMode)
	if c.WaveformPlots > 1 || c.Curves > 1 {
		wave += " · " + plural(c.WaveformPlots, "plot") + " × " + plural(c.Curves, "curve")
	}
	img := fmt.Sprintf("%d×%d / %s", c.Width, c.Height, c.ImageMode)
	if c.ImagePlots > 1 {
		img += " · " + plural(c.ImagePlots, "plot")
	}
	return fmt.Sprintf("%.0f Hz · %s · %s", c.Hz, wave, img)
}
