//go:build go1.27 && goexperiment.simd && (arm64 || wasm)

package main

import (
	"encoding/binary"
	"image/color"
	"runtime"
	"simd/archsimd"
)

func imageConversionKernel() string { return "simd128-float32-" + runtime.GOARCH }

func colorImageScalar(dst, data []byte, palette *[256]color.RGBA) {
	packed := packedImagePalette(palette)
	zero := archsimd.BroadcastFloat32x4(0)
	one := archsimd.BroadcastFloat32x4(1)
	scale := archsimd.BroadcastFloat32x4(255)
	j := 0
	for ; j+16 <= len(dst); j += 16 {
		// Both supported targets are little-endian. Byte-vector loads allow an
		// unaligned protocol payload without unsafe casts or a decoded copy.
		v := archsimd.LoadUint8x16(data[j:]).ReshapeToUint32s().BitsToFloat32()
		// Mask first: NaN, negative values and -Infinity must become zero
		// before Min and integer conversion; +Infinity clamps to one.
		v = v.Masked(v.Greater(zero)).Min(one)
		indices := v.Mul(scale).ConvertToUint32()
		// Neither NEON nor WASM SIMD provides a memory gather for this LUT.
		// Keep the four lookups scalar, and write packed opaque RGBA pixels.
		binary.LittleEndian.PutUint32(dst[j:], packed[uint8(indices.GetElem(0))])
		binary.LittleEndian.PutUint32(dst[j+4:], packed[uint8(indices.GetElem(1))])
		binary.LittleEndian.PutUint32(dst[j+8:], packed[uint8(indices.GetElem(2))])
		binary.LittleEndian.PutUint32(dst[j+12:], packed[uint8(indices.GetElem(3))])
	}
	colorScalarFloat32Packed(dst[j:], data[j:], &packed)
}
