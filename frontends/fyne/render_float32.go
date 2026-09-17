package main

import (
	"encoding/binary"
	"image/color"
	"math"
)

// Packing the small palette does not cache source frames. Every output pixel is
// still converted on every update, and output alpha is always opaque.
func packedImagePalette(palette *[256]color.RGBA) (packed [256]uint32) {
	for i, p := range palette {
		packed[i] = uint32(p.R) | uint32(p.G)<<8 | uint32(p.B)<<16 | 0xff000000
	}
	return
}

// Float32 arithmetic is used only by the SIMD path (including its tail)
// and by its scalar microbenchmark reference. It may select an adjacent LUT
// entry relative to the scalar float64 conversion.
func colorScalarFloat32Packed(dst, data []byte, packed *[256]uint32) {
	for j := 0; j < len(dst); j += 4 {
		v := math.Float32frombits(binary.LittleEndian.Uint32(data[j:]))
		index := 0
		if v >= 1 {
			index = 255
		} else if v > 0 {
			index = int(v * float32(255))
		}
		binary.LittleEndian.PutUint32(dst[j:], packed[index])
	}
}

func colorScalarFloat32(dst, data []byte, palette *[256]color.RGBA) {
	packed := packedImagePalette(palette)
	colorScalarFloat32Packed(dst, data, &packed)
}
