package main

import (
	"fyne.io/fyne/v2"
	"testing"
)

type retinaCanvas struct{ fyne.Canvas }

func (retinaCanvas) Scale() float32 { return 1 }
func (retinaCanvas) PixelCoordinateForPosition(p fyne.Position) (int, int) {
	return int(p.X * 2), int(p.Y * 2)
}
func TestPhysicalScaleIncludesRetinaTextureScaling(t *testing.T) {
	if physicalScale(retinaCanvas{}) != 2 {
		t.Fatal("used logical canvas scale instead of framebuffer scale")
	}
}
