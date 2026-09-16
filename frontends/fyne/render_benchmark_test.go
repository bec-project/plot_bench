package main

import (
	"encoding/binary"
	"image"
	"image/color"
	"math"
	"testing"
)

var convertedImage *image.RGBA

// A deterministic conversion-only fixture, not a source for frontend campaigns.
func BenchmarkColorImage4MP(b *testing.B) {
	c := Config{Width: 2048, Height: 2048, ImageMode: "scalar"}
	data := make([]byte, c.Width*c.Height*4)
	var palette [256]color.RGBA
	for i := range palette {
		palette[i] = color.RGBA{uint8(i), uint8(255 - i), uint8(i / 2), 255}
	}
	for i := 0; i < c.Width*c.Height; i++ {
		binary.LittleEndian.PutUint32(data[i*4:], math.Float32bits(float32(i%65536)/65535))
	}
	b.SetBytes(int64(len(data)))
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		convertedImage = colorImage(data, c, palette)
	}
}
