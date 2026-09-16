package main

import (
	"encoding/binary"
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
	dst := out.Pix
	// Select the input representation once per image, not once per pixel.
	if c.ImageMode == "rgb" {
		for i, j := 0, 0; j < len(dst); i, j = i+3, j+4 {
			rgb := data[i : i+3]
			binary.LittleEndian.PutUint32(dst[j:j+4], uint32(rgb[0])|uint32(rgb[1])<<8|uint32(rgb[2])<<16|0xff000000)
		}
		return out
	}
	// Prepack opaque colours so each pixel is written with a single 32-bit store.
	// Encoding/binary keeps the byte layout portable without unsafe alignment casts.
	var packed [256]uint32
	for i, p := range palette {
		packed[i] = uint32(p.R) | uint32(p.G)<<8 | uint32(p.B)<<16 | 0xff000000
	}
	for j := 0; j < len(dst); j += 4 {
		v := float64(math.Float32frombits(binary.LittleEndian.Uint32(data[j : j+4])))
		index := 0
		if v >= 1 {
			index = 255
		} else if v > 0 {
			index = int(v * 255)
		}
		// Negative values and NaN select zero. For positive finite values below one,
		// truncation equals floor. Keep float64 multiplication to preserve the exact
		// existing LUT boundaries for float32 source values.
		binary.LittleEndian.PutUint32(dst[j:j+4], packed[index])
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
