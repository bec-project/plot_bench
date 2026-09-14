package main

import (
	"image"
	"image/color"
	"math"
)

var plotBackground = color.RGBA{17, 30, 40, 255}
var accent = color.RGBA{100, 220, 204, 255}

// curveColors is the shared CURVE_COLORS palette (docs/protocol.md): curve c of every
// waveform plot is stroked with curveColors[c % 8]; curve 0 keeps the accent colour.
var curveColors = [8]color.RGBA{
	accent,               // #64dccc
	{245, 199, 110, 255}, // #f5c76e
	{122, 166, 255, 255}, // #7aa6ff
	{255, 157, 122, 255}, // #ff9d7a
	{195, 155, 255, 255}, // #c39bff
	{155, 229, 100, 255}, // #9be564
	{255, 122, 184, 255}, // #ff7ab8
	{110, 231, 255, 255}, // #6ee7ff
}

func curveColor(c int) color.RGBA { return curveColors[c%len(curveColors)] }

// colorImage expands ONE image plot (its contiguous source block) to RGBA once per
// adopted update, before canvas submission.
func colorImage(data []byte, c Config, palette [256]color.RGBA) *image.RGBA {
	out := image.NewRGBA(image.Rect(0, 0, c.Width, c.Height))
	for i := 0; i < c.Width*c.Height; i++ {
		p := palette[0]
		if c.ImageMode == "rgb" {
			p = color.RGBA{data[i*3], data[i*3+1], data[i*3+2], 255}
		} else {
			v := scalar(data, i)
			if math.IsNaN(v) {
				v = 0
			}
			v = math.Max(0, math.Min(1, v))
			p = palette[int(math.Floor(v*255))]
		}
		j := i * 4
		out.Pix[j] = p.R
		out.Pix[j+1] = p.G
		out.Pix[j+2] = p.B
		out.Pix[j+3] = 255
	}
	return out
}

// rasterWaveform draws every curve of ONE waveform plot into a physical-pixel RGBA
// image. It visits every sample of every curve and rasterizes each segment using an
// opaque one-physical-pixel Bresenham stroke in the curve's colour; curves are drawn
// in index order, so later curves overdraw earlier ones. No decimation or AA.
func rasterWaveform(curves [][]byte, width, height int) *image.RGBA {
	width = max(1, width)
	height = max(1, height)
	out := image.NewRGBA(image.Rect(0, 0, width, height))
	for i := 0; i < len(out.Pix); i += 4 {
		copy(out.Pix[i:i+4], []byte{17, 30, 40, 255})
	}
	for c, data := range curves {
		rasterCurve(out, data, curveColor(c))
	}
	return out
}
func rasterCurve(out *image.RGBA, data []byte, stroke color.RGBA) {
	width, height := out.Bounds().Dx(), out.Bounds().Dy()
	n := len(data) / 4
	px, py := 0, 0
	valid := false
	for i := 0; i < n; i++ {
		v := scalar(data, i)
		if !finite(v) {
			valid = false
			continue
		}
		x := int(math.Round(float64(i) * float64(width-1) / float64(max(1, n-1))))
		y := int(math.Round((1.5 - math.Max(-1.5, math.Min(1.5, v))) / 3 * float64(height-1)))
		if valid {
			line(out, px, py, x, y, stroke)
		} else {
			out.SetRGBA(x, y, stroke)
		}
		px, py = x, y
		valid = true
	}
}
func line(out *image.RGBA, x0, y0, x1, y1 int, stroke color.RGBA) {
	dx := abs(x1 - x0)
	sx := -1
	if x0 < x1 {
		sx = 1
	}
	dy := -abs(y1 - y0)
	sy := -1
	if y0 < y1 {
		sy = 1
	}
	err := dx + dy
	for {
		out.SetRGBA(x0, y0, stroke)
		if x0 == x1 && y0 == y1 {
			break
		}
		e := 2 * err
		if e >= dy {
			err += dy
			x0 += sx
		}
		if e <= dx {
			err += dx
			y0 += sy
		}
	}
}
func abs(x int) int {
	if x < 0 {
		return -x
	}
	return x
}
