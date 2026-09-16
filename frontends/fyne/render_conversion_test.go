package main

import (
	"encoding/binary"
	"image/color"
	"math"
	"math/rand"
	"testing"
)

func TestScalarConversionPreservesLUTBoundaries(t *testing.T) {
	values := []float32{0, float32(math.Copysign(0, -1)), 1, -1, 2, float32(math.Inf(1)), float32(math.Inf(-1)), float32(math.NaN()), math.SmallestNonzeroFloat32, math.MaxFloat32}
	// Include both sides of every LUT boundary, where a float32 multiply could
	// change the selected index compared with the existing float64 mapping.
	for i := 0; i <= 255; i++ {
		v := float32(float64(i) / 255)
		values = append(values, math.Nextafter32(v, float32(math.Inf(-1))), v, math.Nextafter32(v, float32(math.Inf(1))))
	}
	rng := rand.New(rand.NewSource(42))
	for i := 0; i < 100000; i++ {
		values = append(values, math.Float32frombits(rng.Uint32()), rng.Float32())
	}
	var palette [256]color.RGBA
	for i := range palette {
		palette[i] = color.RGBA{uint8(i), uint8(255 - i), uint8(i ^ 91), uint8(i)}
	}
	data := make([]byte, len(values)*4)
	for i, v := range values {
		binary.LittleEndian.PutUint32(data[i*4:], math.Float32bits(v))
	}
	got := colorImage(data, Config{Width: len(values), Height: 1, ImageMode: "scalar"}, palette)
	for i, v := range values {
		value := float64(v)
		if math.IsNaN(value) {
			value = 0
		}
		index := int(math.Floor(math.Max(0, math.Min(1, value)) * 255))
		want := palette[index]
		want.A = 255
		if got.RGBAAt(i, 0) != want {
			t.Fatalf("value %g bits %08x: got %v want %v", v, math.Float32bits(v), got.RGBAAt(i, 0), want)
		}
	}
}

func TestRGBConversionPreservesBytesAndOwnership(t *testing.T) {
	const width, height = 65, 33
	data := make([]byte, width*height*3)
	rand.New(rand.NewSource(42)).Read(data)
	got := colorImage(data, Config{Width: width, Height: height, ImageMode: "rgb"}, [256]color.RGBA{})
	for i := 0; i < width*height; i++ {
		want := color.RGBA{data[3*i], data[3*i+1], data[3*i+2], 255}
		if got.RGBAAt(i%width, i/width) != want {
			t.Fatalf("pixel %d differs", i)
		}
	}
	first := got.RGBAAt(0, 0)
	for i := range data {
		data[i] = 0
	}
	next := colorImage(data, Config{Width: width, Height: height, ImageMode: "rgb"}, [256]color.RGBA{})
	if got.RGBAAt(0, 0) != first || next.RGBAAt(0, 0) != (color.RGBA{0, 0, 0, 255}) {
		t.Fatal("frames share mutable storage")
	}
}
