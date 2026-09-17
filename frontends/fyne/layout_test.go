package main

import (
	"math"
	"testing"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/canvas"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/layout"
)

func TestGridColumnsFollowSharedLayoutRule(t *testing.T) {
	for n, want := range map[int]int{0: 1, 1: 1, 2: 2, 3: 2, 4: 2, 5: 3, 6: 3, 7: 3, 9: 3, 10: 4, 16: 4, 17: 5, 32: 6} {
		if got := gridColumns(n); got != want {
			t.Fatalf("n=%d: columns %d != %d", n, got, want)
		}
	}
	for n := 1; n <= 32; n++ {
		objects := make([]fyne.CanvasObject, n)
		for i := range objects {
			objects[i] = canvas.NewRectangle(plotBackground)
		}
		columns := gridColumns(n)
		padded := padGrid(objects, columns)
		rows := (n + columns - 1) / columns
		if len(padded) != columns*rows || padded[0] != objects[0] || padded[n-1] != objects[n-1] {
			t.Fatalf("n=%d: padded %d objects for %d×%d", n, len(padded), columns, rows)
		}
		grid := container.New(layout.NewGridLayoutWithColumns(columns), padded...)
		grid.Resize(fyne.NewSize(float32(columns*100), float32(rows*50)))
		first := padded[0].Size()
		for _, o := range padded {
			// Fyne positions cells with float32 arithmetic; allow sub-pixel rounding.
			if s := o.Size(); math.Abs(float64(s.Width-first.Width)) > 0.01 || math.Abs(float64(s.Height-first.Height)) > 0.01 {
				t.Fatalf("n=%d: unequal cells %v %v", n, first, s)
			}
		}
	}
}

func TestVisiblePlotsAndTitles(t *testing.T) {
	c := Config{View: "both", WaveformPlots: 2, ImagePlots: 3}
	if w, i := visiblePlots(c); w != 2 || i != 3 {
		t.Fatal(w, i)
	}
	c.View = "waveform"
	if w, i := visiblePlots(c); w != 2 || i != 0 {
		t.Fatal(w, i)
	}
	c.View = "image"
	if w, i := visiblePlots(c); w != 0 || i != 3 {
		t.Fatal(w, i)
	}
	if plotTitle("Waveform", 0, 1) != "Waveform" || plotTitle("Image", 0, 1) != "Image" {
		t.Fatal("single plot titles are unnumbered")
	}
	if plotTitle("Waveform", 0, 2) != "Waveform 1" || plotTitle("Image", 2, 3) != "Image 3" {
		t.Fatal("numbered titles start at 1")
	}
}

func TestWorkloadAndSubtitleSuffixes(t *testing.T) {
	c := Config{Hz: 30, Points: 10000, Curves: 1, WaveformPlots: 1, Width: 512, Height: 512, ImagePlots: 1, WaveformMode: "replace", ImageMode: "scalar", View: "both"}
	if got := workloadText(c); got != "30 Hz · 10000 points / replace · 512×512 / scalar" {
		t.Fatal(got)
	}
	if got := waveformSubtitle(c); got != "10000 points · replace     x: 0 … 9999     y: -1.5 … 1.5" {
		t.Fatal(got)
	}
	c.Curves, c.WaveformPlots, c.ImagePlots = 3, 2, 3
	if got := workloadText(c); got != "30 Hz · 10000 points / replace · 2 plots × 3 curves · 512×512 / scalar · 3 plots" {
		t.Fatal(got)
	}
	if got := waveformSubtitle(c); got != "10000 points · replace · 3 curves     x: 0 … 9999     y: -1.5 … 1.5" {
		t.Fatal(got)
	}
	c.Curves, c.WaveformPlots = 4, 1
	if got := workloadText(c); got != "30 Hz · 10000 points / replace · 1 plot × 4 curves · 512×512 / scalar · 3 plots" {
		t.Fatal(got)
	}
	c.Curves, c.WaveformPlots, c.ImagePlots = 1, 4, 1
	if got := workloadText(c); got != "30 Hz · 10000 points / replace · 4 plots × 1 curve · 512×512 / scalar" {
		t.Fatal(got)
	}
	if got := imageSubtitle(c); got != "512×512 · scalar · nearest neighbour · levels 0 … 1" {
		t.Fatal(got)
	}
}

func TestBuildPlotsOrdersTitlesAndLaysOutRebuiltCards(t *testing.T) {
	plots := container.NewGridWithColumns(1)
	plots.Resize(fyne.NewSize(900, 600))
	c := Config{View: "both", WaveformPlots: 2, ImagePlots: 3, Curves: 2}
	waves, images := buildPlots(c, plots)
	if len(waves) != 2 || len(images) != 3 || len(plots.Objects) != 6 {
		t.Fatal("n=5 must occupy a padded 3×2 grid", len(waves), len(images), len(plots.Objects))
	}
	for i, want := range []string{"Waveform 1", "Waveform 2", "Image 1", "Image 2", "Image 3"} {
		card := append(waves, images...)[i]
		if card.title.Text != want || plots.Objects[i] != card.object {
			t.Fatalf("plot %d: %q, waveforms must precede images", i, card.title.Text)
		}
	}
	if waves[0].subtitle.Text != waveformSubtitle(c) || images[0].subtitle.Text != imageSubtitle(c) {
		t.Fatal("rebuilt cards must carry their subtitle immediately", waves[0].subtitle.Text, images[0].subtitle.Text)
	}
	slot := dataSlot(fyne.NewSize(1100, 820), 5, false)
	for _, card := range append(waves, images...) {
		card.dataLayout.size = slot
		card.object.Refresh()
	}
	first := waves[0].image.Size()
	if first.Width <= 0 || first.Height <= 0 {
		t.Fatal("rebuilt cards must be laid out before the first raster", first)
	}
	for _, card := range append(waves, images...) {
		if s := card.image.Size(); math.Abs(float64(s.Width-first.Width)) > 0.01 || math.Abs(float64(s.Height-first.Height)) > 0.01 {
			t.Fatal("unequal plot areas", first, s)
		}
	}
	c.View = "image"
	c.ImagePlots = 1
	waves, images = buildPlots(c, plots)
	if len(waves) != 0 || len(images) != 1 || len(plots.Objects) != 1 || images[0].title.Text != "Image" {
		t.Fatal("image-only single plot", len(waves), len(images), len(plots.Objects))
	}
	images[0].dataLayout.size = dataSlot(fyne.NewSize(1100, 820), 1, true)
	images[0].object.Refresh()
	if s := images[0].image.Size(); s.Width <= first.Width || s.Height <= first.Height {
		t.Fatal("single cell must use the whole grid", s)
	}
}

func TestMultiPlotLongSubtitlesFitRequestedViewport(t *testing.T) {
	c := Config{Hz: 30, View: "both", Points: 10000, WaveformMode: "append", WaveformPlots: 2, Curves: 3, ImagePlots: 3, Width: 256, Height: 256, ImageMode: "rgb"}
	plots := container.NewGridWithColumns(1)
	// Both frontends must honor 1100 pixels; allow the standard 24 pixel
	// padding without enlarging native windows or overflowing browser canvases.
	available := fyne.NewSize(1100-48, 500)
	plots.Resize(available)
	waves, images := buildPlots(c, plots)
	if minimum := plots.MinSize(); minimum.Width > available.Width {
		t.Fatalf("grid requires %.1f pixels, only %.1f available", minimum.Width, available.Width)
	}
	for _, card := range append(waves, images...) {
		if right := card.object.Position().X + card.object.Size().Width; right > available.Width+0.01 {
			t.Fatalf("plot card extends beyond requested viewport: %f", right)
		}
		if size := card.image.Size(); size.Width <= 0 || size.Height <= 0 {
			t.Fatal("wrapping consumed the plot data area", size)
		}
	}
}
