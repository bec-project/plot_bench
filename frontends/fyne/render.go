package main

import (
	"image"
	"image/color"
	"math"
)

var plotBackground = color.RGBA{17, 30, 40, 255}
var accent = color.RGBA{100, 220, 204, 255}

// colorImage expands source pixels once per adopted update, before canvas submission.
func colorImage(f *Frame, palette [256]color.RGBA) *image.RGBA {
	c := f.Header.Config
	out := image.NewRGBA(image.Rect(0, 0, c.Width, c.Height))
	data := f.Arrays["image"]
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

// rasterWaveform visits every sample and rasterizes each segment using an opaque
// one-physical-pixel Bresenham stroke. It performs no data decimation or AA.
func rasterWaveform(data []byte, width, height int) *image.RGBA {
	width = max(1, width)
	height = max(1, height)
	out := image.NewRGBA(image.Rect(0, 0, width, height))
	for i := 0; i < len(out.Pix); i += 4 {
		copy(out.Pix[i:i+4], []byte{17, 30, 40, 255})
	}
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
			line(out, px, py, x, y)
		} else {
			out.SetRGBA(x, y, accent)
		}
		px, py = x, y
		valid = true
	}
	return out
}
func line(out *image.RGBA, x0, y0, x1, y1 int) {
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
		out.SetRGBA(x0, y0, accent)
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
