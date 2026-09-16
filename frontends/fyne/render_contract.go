package main

import (
	"fyne.io/fyne/v2"
	"math"
)

// data-area-v2. Dimensions are logical window pixels; native chrome is outside.
func dataSlot(window fyne.Size, count int, image bool) fyne.Size {
	columns := math.Ceil(math.Sqrt(float64(count)))
	rows := math.Ceil(float64(count) / columns)
	horizontal, vertical := 100.0, 120.0
	if image {
		horizontal, vertical = 96, 100
		if count > 1 {
			horizontal, vertical = 16, 16
		}
	}
	return fyne.NewSize(
		float32(math.Max(1, math.Floor((float64(window.Width)-48-16*(columns-1))/columns-horizontal))),
		float32(math.Max(1, math.Floor((float64(window.Height)-220-16*(rows-1))/rows-vertical))))
}

type dataAreaLayout struct{ size fyne.Size }

func (l *dataAreaLayout) MinSize(_ []fyne.CanvasObject) fyne.Size { return fyne.NewSize(1, 1) }
func (l *dataAreaLayout) Layout(objects []fyne.CanvasObject, available fyne.Size) {
	for _, object := range objects {
		object.Resize(l.size)
		object.Move(fyne.NewPos((available.Width-l.size.Width)/2, (available.Height-l.size.Height)/2))
	}
}
func allDataAreas(waves, images []*plotCard, config Config, scale float32) map[string]any {
	waveAreas := make([][]float64, 0, len(waves))
	imageAreas := make([][]float64, 0, len(images))
	for _, card := range waves {
		size := card.image.Size()
		waveAreas = append(waveAreas, []float64{float64(size.Width * scale), float64(size.Height * scale)})
	}
	for _, card := range images {
		size := card.image.Size()
		ratio := math.Min(float64(size.Width*scale)/float64(config.Width), float64(size.Height*scale)/float64(config.Height))
		imageAreas = append(imageAreas, []float64{float64(config.Width) * ratio, float64(config.Height) * ratio})
	}
	return map[string]any{"waveform": waveAreas, "image": imageAreas}
}
