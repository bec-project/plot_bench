package main

import "fyne.io/fyne/v2"

// Canvas.Scale excludes macOS framebuffer/texture scaling. The public pixel
// coordinate API includes both toolkit scale and texture scale, without captures.
func physicalScale(c fyne.Canvas) float32 {
	x, _ := c.PixelCoordinateForPosition(fyne.NewPos(1024, 1024))
	return float32(x) / 1024
}
