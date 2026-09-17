package main

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"image"
	"image/color"
	"math"
	"math/rand/v2"
	"strings"
	"testing"
)

func renderPalette() [256]color.RGBA {
	var palette [256]color.RGBA
	for i := range palette {
		// Distinct RGB channels detect wrong LUT indices; input alpha is ignored.
		palette[i] = color.RGBA{uint8(i), uint8(i*37 + 19), uint8(255 - i), uint8(i)}
	}
	return palette
}

func renderScalarBytes(values []float32) []byte {
	data := make([]byte, 0, len(values)*4)
	for _, value := range values {
		data = binary.LittleEndian.AppendUint32(data, math.Float32bits(value))
	}
	return data
}

// The previous allocating implementation is kept as a behavioral oracle and a
// microbenchmark reference, including its float64 clamp/multiply/floor sequence.
func referenceColorImage(data []byte, c Config, palette [256]color.RGBA) *image.RGBA {
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

// renderPalette encodes its index in R. SIMD may choose a neighboring index,
// but every RGB component must still come from the same complete LUT entry.
func assertScalarRaster(t *testing.T, got, want *image.RGBA, palette *[256]color.RGBA) {
	t.Helper()
	tolerance := 0
	if strings.HasPrefix(imageConversionKernel(), "simd") {
		tolerance = 1
	}
	for y := 0; y < want.Rect.Dy(); y++ {
		for x := 0; x < want.Rect.Dx(); x++ {
			p, expected := got.RGBAAt(x, y), want.RGBAAt(x, y)
			entry := palette[p.R]
			entry.A = 255
			if abs(int(p.R)-int(expected.R)) > tolerance || p != entry {
				t.Fatalf("%s pixel (%d,%d): got %v, want %v (LUT tolerance %d)", imageConversionKernel(), x, y, p, expected, tolerance)
			}
		}
	}
}

func assertDefaultScalarExact(t *testing.T, data []byte, c Config, palette *[256]color.RGBA, want *image.RGBA) {
	t.Helper()
	got := image.NewRGBA(want.Rect)
	colorScalarFloat64(got.Pix, data, palette)
	if !bytes.Equal(got.Pix, want.Pix) {
		t.Fatal("scalar reference kernel differs from the previous exact conversion")
	}
}

func TestColorImagePreservesScalarLUTBoundaries(t *testing.T) {
	palette := renderPalette()
	values := []float32{
		float32(math.NaN()), float32(math.Inf(-1)), float32(math.Inf(1)),
		float32(math.Copysign(0, -1)), 0, -1, 1, 2,
		-math.MaxFloat32, math.MaxFloat32, -math.SmallestNonzeroFloat32, math.SmallestNonzeroFloat32,
	}
	for index := 0; index < 256; index++ {
		boundary := float32(float64(index) / 255)
		values = append(values,
			math.Nextafter32(boundary, float32(math.Inf(-1))),
			boundary,
			math.Nextafter32(boundary, float32(math.Inf(1))),
		)
	}
	data := renderScalarBytes(values)
	c := Config{Width: len(values), Height: 1, ImageMode: "scalar"}
	got := colorImage(nil, data, c, &palette)
	want := referenceColorImage(data, c, palette)
	assertDefaultScalarExact(t, data, c, &palette, want)
	assertScalarRaster(t, got, want, &palette)
	for i, index := range []int{0, 0, 255, 0, 0, 0, 255, 255, 0, 255, 0, 0} {
		p := palette[index]
		p.A = 255
		if got.RGBAAt(i, 0) != p {
			t.Fatalf("special scalar %g: got %v, want %v", values[i], got.RGBAAt(i, 0), p)
		}
	}
}

func TestColorImagePreservesRandomFiniteScalars(t *testing.T) {
	rng := rand.New(rand.NewPCG(42, 7))
	values := make([]float32, 0, 16384)
	for len(values) < cap(values) {
		value := math.Float32frombits(rng.Uint32())
		if !finite(float64(value)) {
			continue
		}
		values = append(values, value, float32(rng.Float64()))
	}
	data := renderScalarBytes(values)
	unchanged := bytes.Clone(data)
	palette := renderPalette()
	c := Config{Width: 128, Height: len(values) / 128, ImageMode: "scalar"}
	got := colorImage(nil, data, c, &palette)
	want := referenceColorImage(data, c, palette)
	assertDefaultScalarExact(t, data, c, &palette, want)
	assertScalarRaster(t, got, want, &palette)
	if !bytes.Equal(data, unchanged) {
		t.Fatal("conversion modified authoritative source bytes")
	}
}

func TestColorImageReusesStorageAndRewritesEveryFrame(t *testing.T) {
	palette := renderPalette()
	c := Config{Width: 2, Height: 2, ImageMode: "scalar"}
	data := renderScalarBytes([]float32{0, .25, .5, 1})
	out := colorImage(nil, data, c, &palette)
	storage := &out.Pix[0]
	for _, values := range [][]float32{{1, .5, .25, 0}, {0, .25, .5, 1}, {0, .25, .5, 1}} {
		copy(data, renderScalarBytes(values))
		// Simulate stale scratch contents even when the replay frame repeats.
		for i := range out.Pix {
			out.Pix[i] = 3
		}
		got := colorImage(out, data, c, &palette)
		if got != out || &got.Pix[0] != storage {
			t.Fatal("same dimensions must preserve the image and backing buffer")
		}
		assertScalarRaster(t, got, referenceColorImage(data, c, palette), &palette)
	}
	c.ImageMode = "rgb"
	rgb := []byte{4, 19, 233, 55, 67, 89, 101, 123, 145, 201, 230, 255}
	got := colorImage(out, rgb, c, nil) // RGB needs no palette lookup.
	if got != out || &got.Pix[0] != storage {
		t.Fatal("a mode change with the same dimensions must preserve storage")
	}
	want := []byte{4, 19, 233, 255, 55, 67, 89, 255, 101, 123, 145, 255, 201, 230, 255, 255}
	if !bytes.Equal(got.Pix, want) {
		t.Fatalf("RGB layout or opaque alpha: got %v, want %v", got.Pix, want)
	}
	c.ImageMode = "scalar"
	got = colorImage(out, data, c, &palette)
	if got != out {
		t.Fatal("RGB-to-scalar mode change did not reuse storage")
	}
	assertScalarRaster(t, got, referenceColorImage(data, c, palette), &palette)
}

func TestColorImageReplacesIncompatibleStorage(t *testing.T) {
	c := Config{Width: 3, Height: 2, ImageMode: "scalar"}
	data := renderScalarBytes([]float32{0, .2, .4, .6, .8, 1})
	palette := renderPalette()
	want := referenceColorImage(data, c, palette)
	for name, dst := range map[string]*image.RGBA{
		"nil":     nil,
		"size":    image.NewRGBA(image.Rect(0, 0, 2, 2)),
		"shape":   image.NewRGBA(image.Rect(0, 0, 2, 3)),
		"origin":  image.NewRGBA(image.Rect(5, 7, 8, 9)),
		"stride":  {Pix: make([]byte, 32), Stride: 16, Rect: image.Rect(0, 0, 3, 2)},
		"storage": {Pix: make([]byte, 23), Stride: 12, Rect: image.Rect(0, 0, 3, 2)},
	} {
		t.Run(name, func(t *testing.T) {
			got := colorImage(dst, data, c, &palette)
			if got == dst || got.Rect != want.Rect || got.Stride != want.Stride {
				t.Fatal("incompatible destination was not replaced with a complete contiguous raster")
			}
			assertScalarRaster(t, got, want, &palette)
		})
	}
}

func TestColorImageScalarUnalignedAndRemainder(t *testing.T) {
	palette := renderPalette()
	values := []float32{float32(math.NaN()), -1, 0, 1, float32(math.Inf(1)), float32(math.Inf(-1)), .2, .5, .999, math.Float32frombits(0x7f800001)}
	for count := 0; count <= 33; count++ {
		for offset := 1; offset <= 15; offset++ {
			c := Config{Width: count, Height: 1, ImageMode: "scalar"}
			input := bytes.Repeat([]byte{0xa5}, offset+count*4+17)
			data := input[offset : offset+count*4]
			for i := 0; i < count; i++ {
				binary.LittleEndian.PutUint32(data[i*4:], math.Float32bits(values[(i+offset)%len(values)]))
			}
			unchanged := bytes.Clone(input)
			output := bytes.Repeat([]byte{0xcc}, 3+count*4+19)
			dst := &image.RGBA{Pix: output[3 : 3+count*4], Stride: count * 4, Rect: image.Rect(0, 0, count, 1)}
			got := colorImage(dst, data, c, &palette)
			if got != dst {
				t.Fatalf("count=%d offset=%d: storage replaced", count, offset)
			}
			assertScalarRaster(t, got, referenceColorImage(data, c, palette), &palette)
			if !bytes.Equal(input, unchanged) || !bytes.Equal(output[:3], []byte{0xcc, 0xcc, 0xcc}) || !bytes.Equal(output[3+count*4:], bytes.Repeat([]byte{0xcc}, 19)) {
				t.Fatalf("count=%d offset=%d: source or output sentinel overwritten", count, offset)
			}
		}
	}
}

var benchmarkColorImage *image.RGBA

func BenchmarkColorImage(b *testing.B) {
	palette := renderPalette()
	for _, size := range []int{512, 2048} {
		for _, mode := range []string{"scalar", "rgb"} {
			c := Config{Width: size, Height: size, ImageMode: mode}
			var data []byte
			if mode == "scalar" {
				values := make([]float32, size*size)
				for i := range values {
					values[i] = float32(i%4096) / 4095
				}
				data = renderScalarBytes(values)
			} else {
				data = make([]byte, size*size*3)
				for i := range data {
					data[i] = byte(i)
				}
			}
			b.Run(fmt.Sprintf("%s/%d/previous", mode, size), func(b *testing.B) {
				b.ReportAllocs()
				b.SetBytes(int64(len(data)))
				for b.Loop() {
					benchmarkColorImage = referenceColorImage(data, c, palette)
				}
			})
			b.Run(fmt.Sprintf("%s/%d/reuse", mode, size), func(b *testing.B) {
				out := colorImage(nil, data, c, &palette)
				b.ReportAllocs()
				b.SetBytes(int64(len(data)))
				for b.Loop() {
					out = colorImage(out, data, c, &palette)
				}
				benchmarkColorImage = out
			})
		}
	}
}

// The float32 scalar and selected SIMD variants share palette packing and
// output stores, isolating vectorization from precision/allocation changes.
func BenchmarkScalarImageKernel(b *testing.B) {
	const size = 2048
	values := make([]float32, size*size)
	for i := range values {
		values[i] = float32(i%4096) / 4095
	}
	data := renderScalarBytes(values)
	palette := renderPalette()
	for _, kernel := range []struct {
		name string
		run  func([]byte, []byte, *[256]color.RGBA)
	}{
		{"scalar-float64", colorScalarFloat64},
		{"scalar-float32-packed", colorScalarFloat32},
		{imageConversionKernel(), colorImageScalar},
	} {
		b.Run(kernel.name, func(b *testing.B) {
			out := image.NewRGBA(image.Rect(0, 0, size, size))
			b.ReportAllocs()
			b.SetBytes(int64(len(data)))
			for b.Loop() {
				kernel.run(out.Pix, data, &palette)
			}
			benchmarkColorImage = out
		})
	}
}
