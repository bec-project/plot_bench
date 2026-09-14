package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"math"
	"net/url"
	"os"
	"os/signal"
	"runtime"
	"runtime/debug"
	"strings"
	"sync/atomic"
	"syscall"
	"time"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/canvas"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/layout"
	"fyne.io/fyne/v2/theme"
	"fyne.io/fyne/v2/widget"
)

type benchTheme struct{ fyne.Theme }

func (t benchTheme) Color(n fyne.ThemeColorName, v fyne.ThemeVariant) color.Color {
	switch n {
	case theme.ColorNameBackground:
		return color.RGBA{11, 20, 28, 255}
	case theme.ColorNameForeground:
		return color.RGBA{216, 230, 237, 255}
	case theme.ColorNamePrimary:
		return accent
	case theme.ColorNameInputBackground:
		return plotBackground
	}
	return t.Theme.Color(n, theme.VariantDark)
}

// plotCard is one plot widget: a bold title, the physical-pixel image and a subtitle.
type plotCard struct {
	image    *canvas.Image
	title    *widget.Label
	subtitle *widget.Label
	object   fyne.CanvasObject
}

func newPlotCard(title string, fill canvas.ImageFill) *plotCard {
	img := canvas.NewImageFromImage(image.NewRGBA(image.Rect(0, 0, 1, 1)))
	img.ScaleMode = canvas.ImageScalePixels
	img.FillMode = fill
	t := widget.NewLabelWithStyle(title, fyne.TextAlignLeading, fyne.TextStyle{Bold: true})
	s := widget.NewLabel("")
	return &plotCard{image: img, title: t, subtitle: s, object: container.NewBorder(t, s, nil, nil, container.NewStack(canvas.NewRectangle(plotBackground), img))}
}

// buildPlots replaces the grid's widgets with `waveform_plots` waveform cards
// followed by `image_plots` image cards (only the kinds enabled by view), arranged
// with the shared rule columns = ceil(sqrt(n)) and equal cells, trailing cells empty.
func buildPlots(c Config, plots *fyne.Container) (waveCards, imgCards []*plotCard) {
	waveforms, images := visiblePlots(c)
	objects := []fyne.CanvasObject{}
	for i := 0; i < waveforms; i++ {
		card := newPlotCard(plotTitle("Waveform", i, waveforms), canvas.ImageFillStretch)
		card.subtitle.SetText(waveformSubtitle(c))
		waveCards = append(waveCards, card)
		objects = append(objects, card.object)
	}
	for i := 0; i < images; i++ {
		card := newPlotCard(plotTitle("Image", i, images), canvas.ImageFillContain)
		card.subtitle.SetText(imageSubtitle(c))
		imgCards = append(imgCards, card)
		objects = append(objects, card.object)
	}
	columns := gridColumns(len(objects))
	plots.Objects = padGrid(objects, columns)
	plots.Layout = layout.NewGridLayoutWithColumns(columns)
	plots.Refresh()
	return waveCards, imgCards
}
func versions() map[string]string {
	v := map[string]string{"go": runtime.Version(), "fyne": "unknown"}
	if b, ok := debug.ReadBuildInfo(); ok {
		for _, d := range b.Deps {
			if d.Path == "fyne.io/fyne/v2" {
				v["fyne"] = d.Version
			}
		}
	}
	return v
}
func runtimeInfo() map[string]any {
	settings := map[string]string{}
	if b, ok := debug.ReadBuildInfo(); ok {
		for _, s := range b.Settings {
			settings[s.Key] = s.Value
		}
	}
	tags := "," + settings["-tags"] + ","
	profile := "development"
	if strings.Contains(tags, ",release,") {
		profile = "release"
	}
	return map[string]any{"versions": versions(), "display_protocol": displayProtocol, "graphics_api": "OpenGL via Fyne GLFW", "build_profile": profile, "graphics_build_settings": settings, "headless": strings.Contains(tags, ",ci,")}
}

func main() {
	base := flag.String("url", "http://127.0.0.1:8765", "source URL")
	mode := flag.String("mode", "stream", "stream or replay")
	runID := flag.String("run-id", "demo", "run identifier")
	duration := flag.Float64("duration", 0, "seconds after first submission; zero until closed")
	width := flag.Int("width", 1100, "logical window width")
	height := flag.Int("height", 820, "logical window height")
	info := flag.Bool("runtime-info", false, "print runtime identity without opening a window")
	screenshot := flag.String("screenshot", "", "demo-only screenshot path; captures after two seconds and closes")
	flag.Parse()
	if *info {
		_ = json.NewEncoder(os.Stdout).Encode(runtimeInfo())
		return
	}
	u, err := url.Parse(*base)
	if err != nil || u.Host == "" || (u.Scheme != "http" && u.Scheme != "https") || (*mode != "stream" && *mode != "replay") || !finite(*duration) || *duration < 0 || *width < 200 || *height < 200 || flag.NArg() != 0 || (*screenshot != "" && (*duration != 0 || *runID != "demo")) {
		fmt.Fprintln(os.Stderr, "invalid arguments (screenshots require an untimed demo)")
		os.Exit(2)
	}
	source := newSource(*base, *mode)
	a := app.NewWithID("org.plotbench.fyne")
	a.Settings().SetTheme(benchTheme{theme.DefaultTheme()})
	w := a.NewWindow("Plotbench · Fyne")
	w.Resize(fyne.NewSize(float32(*width), float32(*height)))
	w.CenterOnScreen()
	// Plot widgets are created from the first frame's configuration and rebuilt
	// whenever a generation change alters the visible plot set (see buildPlots).
	var waveCards, imgCards []*plotCard
	plots := container.NewGridWithColumns(1)
	status := widget.NewLabel("Connecting")
	workload := widget.NewLabel("Waiting for authoritative source frames")
	submitted := widget.NewLabel("Submitted\n— updates/s")
	update := widget.NewLabel("Update time\n— ms")
	skips := widget.NewLabel("Skipped\n—")
	age := widget.NewLabel("Receive age\n—")
	currentView := "both"
	var currentPlots [3]int // view-visible waveform plots, image plots, curves of the built widgets
	one := widget.NewCheck("1D", nil)
	two := widget.NewCheck("2D", nil)
	one.Checked = true
	two.Checked = true
	changing := false
	selectView := func() {
		if changing {
			return
		}
		view := "both"
		if !one.Checked && !two.Checked {
			changing = true
			one.SetChecked(currentView != "image")
			two.SetChecked(currentView != "waveform")
			changing = false
			return
		}
		if !one.Checked {
			view = "image"
		}
		if !two.Checked {
			view = "waveform"
		}
		source.requestView(view)
		changing = true
		one.SetChecked(currentView != "image")
		two.SetChecked(currentView != "waveform")
		changing = false
		one.Disable()
		two.Disable()
	}
	one.OnChanged = func(bool) { selectView() }
	two.OnChanged = func(bool) { selectView() }
	locked := *runID != "demo" || *duration > 0
	if locked {
		one.Disable()
		two.Disable()
	}
	controls := widget.NewButton("Source controls", func() { _ = a.OpenURL(u) })
	if locked {
		controls.Disable()
	}
	header := container.NewVBox(widget.NewLabelWithStyle("PLOTTING BENCHMARK · Fyne", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}), container.NewHBox(widget.NewLabel("Go · CPU raster / Fyne OpenGL · "+*mode), controls, status), workload, container.NewHBox(widget.NewLabel("PLOTS"), one, two), container.NewGridWithColumns(4, submitted, update, skips, age))
	footer := widget.NewLabel("Submitted updates · not displayed FPS\nCustom CPU waveform + RGBA conversion; Fyne canvas upload/paint deferred")
	w.SetContent(container.New(layout.NewCustomPaddedLayout(24, 24, 24, 24), container.NewBorder(header, footer, nil, nil, plots)))
	meta := runtimeInfo()
	meta["renderer"] = "Fyne canvas.Image per plot / custom CPU waveform raster per plot and curve"
	meta["measurement_stage"] = "CPU full-waveform rasterization of every plot and curve, source-image RGBA conversion of every image plot and Fyne canvas refresh submission; excludes deferred texture upload, OpenGL draw and presentation"
	meta["update_strategy"] = "authoritative full windows; every waveform sample of every curve; per-update CPU RGBA image per image plot; no GPU replay preload"
	meta["renderer_environment"] = map[string]string{"FYNE_SCALE": os.Getenv("FYNE_SCALE"), "LIBGL_ALWAYS_SOFTWARE": os.Getenv("LIBGL_ALWAYS_SOFTWARE"), "GALLIUM_DRIVER": os.Getenv("GALLIUM_DRIVER")}
	meta["display_protocol_requested"] = displayProtocol
	metrics := newMetrics(*base, *mode, *runID, meta)
	var first, lastHUD, lastStatus time.Time
	var count, hudCount, skippedTotal uint64
	var lastSample Sample
	reason := "user"
	var failure error
	stop := make(chan struct{})
	closed := false
	shutdown := func(why string) {
		if closed {
			return
		}
		closed = true
		reason = why
		close(stop)
		w.Close()
	}
	w.SetCloseIntercept(func() { shutdown("user") })
	source.start()
	var queued atomic.Bool
	tick := func() {
		defer queued.Store(false)
		if closed {
			return
		}
		source.mu.Lock()
		sourceErr := source.err
		state := source.status
		pending := source.pending
		viewError := source.viewError
		reconnects := source.reconnects
		replayCount, replayBytes := source.replayCount, source.replayBytes
		source.mu.Unlock()
		if sourceErr != nil {
			failure = sourceErr
			shutdown("error")
			return
		}
		f, skipped := source.take()
		if f != nil {
			c := f.Header.Config
			waveforms, images := visiblePlots(c)
			if wanted := [3]int{waveforms, images, c.Curves}; wanted != currentPlots || count == 0 {
				currentPlots = wanted
				waveCards, imgCards = buildPlots(c, plots)
			}
			if c.View != currentView || count == 0 {
				currentView = c.View
				changing = true
				one.SetChecked(c.View != "image")
				two.SetChecked(c.View != "waveform")
				changing = false
			}
			scale := physicalScale(w.Canvas())
			start := time.Now()
			conversion := 0.0
			for p, card := range waveCards {
				size := card.image.Size()
				card.image.Image = rasterWaveform(f.waveformPlot(p), int(math.Round(float64(size.Width*scale))), int(math.Round(float64(size.Height*scale))))
				card.image.Refresh()
			}
			for p, card := range imgCards {
				before := time.Now()
				card.image.Image = colorImage(f.imagePlot(p), c, source.palette)
				conversion += float64(time.Since(before)) / 1e6
				card.image.Refresh()
			}
			elapsed := float64(time.Since(start)) / 1e6
			now := time.Now()
			if first.IsZero() {
				first = now
				lastHUD = now
			}
			var receiveAge *float64
			if *mode == "stream" {
				v := float64(now.UnixNano())/1e6 - f.Header.Emitted
				receiveAge = &v
			}
			lastSample = Sample{Seq: f.Seq, Generation: f.Header.Generation, ClientTime: float64(now.UnixNano()) / 1e6, Update: elapsed, Conversion: conversion, ReceiveAge: receiveAge, Skipped: skipped}
			metrics.record(lastSample)
			count++
			skippedTotal += skipped
			if count == 1 || now.Sub(lastHUD) >= 500*time.Millisecond {
				period := 1000 / c.Hz
				rate := float64(count-hudCount) / math.Max(.001, now.Sub(lastHUD).Seconds())
				submitted.SetText(fmt.Sprintf("Submitted\n%.1f updates/s (%.0f target)", rate, c.Hz))
				update.SetText(fmt.Sprintf("Update time\n%.2f ms (%.1f budget)", elapsed, period))
				skips.SetText(fmt.Sprintf("Skipped\n%d (0 target)", skippedTotal))
				ageText := "N/A (replay)"
				if receiveAge != nil {
					ageText = fmt.Sprintf("%.1f ms (<%.1f guide)", *receiveAge, period)
				}
				age.SetText("Receive age\n" + ageText)
				workload.SetText(workloadText(c))
				for _, card := range waveCards {
					card.subtitle.SetText(waveformSubtitle(c))
				}
				for _, card := range imgCards {
					card.subtitle.SetText(imageSubtitle(c))
				}
				lastHUD = now
				hudCount = count
				size := w.Canvas().Size()
				// Physical data area of the FIRST plot of each kind; all grid cells are equal.
				viewports := map[string]any{"waveform": nil, "image": nil}
				if len(waveCards) > 0 {
					v := waveCards[0].image.Size()
					viewports["waveform"] = []float32{v.Width * scale, v.Height * scale}
				}
				if len(imgCards) > 0 {
					v := imgCards[0].image.Size()
					r := math.Min(float64(v.Width*scale)/float64(c.Width), float64(v.Height*scale)/float64(c.Height))
					viewports["image"] = []float64{float64(c.Width) * r, float64(c.Height) * r}
				}
				metrics.set(map[string]any{"config": c, "pixel_ratio": scale, "viewport_size": []float32{size.Width, size.Height}, "plot_viewports": viewports, "plot_counts": map[string]int{"waveform": waveforms, "image": images}, "curves": c.Curves, "display": nil, "receiver_connection_epoch": reconnects + 1, "replay_frames": replayCount, "replay_bytes": replayBytes})
			}
		}
		if time.Since(lastStatus) >= 500*time.Millisecond {
			lastStatus = time.Now()
			status.SetText(state)
			if viewError != "" {
				status.SetText(viewError)
			}
			if !locked {
				if pending {
					one.Disable()
					two.Disable()
				} else {
					one.Enable()
					two.Enable()
				}
			}
		}
		if !first.IsZero() && *duration > 0 && time.Since(first).Seconds() >= *duration {
			shutdown("duration")
		}
		if !first.IsZero() && *screenshot != "" && time.Since(first) > 2*time.Second {
			out, e := os.Create(*screenshot)
			if e == nil {
				e = png.Encode(out, w.Canvas().Capture())
				_ = out.Close()
			}
			if e != nil {
				failure = e
				shutdown("error")
			} else {
				shutdown("user")
			}
		}
	}
	workerDone := make(chan struct{})
	go func() {
		defer close(workerDone)
		t := time.NewTicker(time.Millisecond)
		defer t.Stop()
		for {
			select {
			case <-stop:
				return
			case <-t.C:
				if queued.CompareAndSwap(false, true) {
					fyne.Do(tick)
				}
			}
		}
	}()
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, os.Interrupt, syscall.SIGTERM)
	defer signal.Stop(signals)
	go func() {
		select {
		case <-stop:
			return
		case <-signals:
			fyne.Do(func() { shutdown("user") })
		}
	}()
	w.ShowAndRun()
	if !closed {
		close(stop)
	}
	<-workerDone
	source.close()
	active := 0.0
	if !first.IsZero() {
		active = time.Since(first).Seconds()
	}
	source.mu.Lock()
	reconnects := source.reconnects
	source.mu.Unlock()
	metrics.set(map[string]any{"termination_reason": reason, "active_seconds": active, "receiver_connection_epoch": reconnects + 1})
	if e := metrics.close(); e != nil {
		failure = e
	}
	if failure != nil {
		fmt.Fprintln(os.Stderr, failure)
		os.Exit(1)
	}
}
