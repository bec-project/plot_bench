//go:build go1.27 && goexperiment.simd && amd64

package main

import (
	"encoding/binary"
	"image/color"
	"simd/archsimd"
)

func imageConversionKernel() string {
	return amd64ConversionKernel(archsimd.X86.AVX(), archsimd.X86.AVX512())
}

func amd64ConversionKernel(avx, avx512 bool) string {
	// GODEBUG can disable AVX independently of the bundled AVX-512 feature.
	if !avx {
		return "scalar-float64"
	}
	if avx512 {
		return "simd512-float32-amd64-avx512"
	}
	return "simd128-float32-amd64-avx"
}

func colorImageScalar(dst, data []byte, palette *[256]color.RGBA) {
	if !archsimd.X86.AVX() {
		colorScalarFloat64(dst, data, palette)
		return
	}
	if archsimd.X86.AVX512() {
		colorScalarAVX512(dst, data, palette)
		return
	}
	colorScalarAVX128(dst, data, palette)
}

func colorScalarAVX128(dst, data []byte, palette *[256]color.RGBA) {
	// Go's x86 SIMD API emits AVX instructions even for 128-bit vectors.
	// Check the CPU/OS feature before creating any vector, retaining the exact
	// scalar fallback on older x86-64 machines or when AVX is disabled.
	if !archsimd.X86.AVX() {
		colorScalarFloat64(dst, data, palette)
		return
	}
	packed := packedImagePalette(palette)
	zero := archsimd.BroadcastFloat32x4(0)
	one := archsimd.BroadcastFloat32x4(1)
	scale := archsimd.BroadcastFloat32x4(255)
	j := 0
	for ; j+16 <= len(dst); j += 16 {
		v := archsimd.LoadUint8x16(data[j:]).ReshapeToUint32s().BitsToFloat32()
		v = v.Masked(v.Greater(zero)).Min(one)
		// The unsigned conversion requires AVX-512 on x86. These clamped
		// indices fit in signed int32, so AVX truncation followed by a bit
		// reinterpretation produces identical 0..255 indices without AVX-512.
		indices := v.Mul(scale).ConvertToInt32().ToBits()
		binary.LittleEndian.PutUint32(dst[j:], packed[uint8(indices.GetElem(0))])
		binary.LittleEndian.PutUint32(dst[j+4:], packed[uint8(indices.GetElem(1))])
		binary.LittleEndian.PutUint32(dst[j+8:], packed[uint8(indices.GetElem(2))])
		binary.LittleEndian.PutUint32(dst[j+12:], packed[uint8(indices.GetElem(3))])
	}
	colorScalarFloat32Packed(dst[j:], data[j:], &packed)
}

func colorScalarAVX512(dst, data []byte, palette *[256]color.RGBA) {
	// Go's bundled AVX512 capability requires F, CD, BW, DQ and VL, as well
	// as OS support for opmask and ZMM state. Guard before constructing vectors.
	if !archsimd.X86.AVX() || !archsimd.X86.AVX512() {
		colorScalarAVX128(dst, data, palette)
		return
	}
	packed := packedImagePalette(palette)
	zero := archsimd.BroadcastFloat32x16(0)
	one := archsimd.BroadcastFloat32x16(1)
	scale := archsimd.BroadcastFloat32x16(255)
	var indices [16]uint32
	j := 0
	for ; j+64 <= len(dst); j += 64 {
		v := archsimd.LoadUint8x64(data[j:]).ReshapeToUint32s().BitsToFloat32()
		v = v.Masked(v.Greater(zero)).Min(one)
		v.Mul(scale).ConvertToUint32().StoreArray(&indices)
		// archsimd has no wide gather or lane extraction API. Store the indices
		// on the stack, then use the same opaque packed palette as the AVX path.
		binary.LittleEndian.PutUint32(dst[j:], packed[uint8(indices[0])])
		binary.LittleEndian.PutUint32(dst[j+4:], packed[uint8(indices[1])])
		binary.LittleEndian.PutUint32(dst[j+8:], packed[uint8(indices[2])])
		binary.LittleEndian.PutUint32(dst[j+12:], packed[uint8(indices[3])])
		binary.LittleEndian.PutUint32(dst[j+16:], packed[uint8(indices[4])])
		binary.LittleEndian.PutUint32(dst[j+20:], packed[uint8(indices[5])])
		binary.LittleEndian.PutUint32(dst[j+24:], packed[uint8(indices[6])])
		binary.LittleEndian.PutUint32(dst[j+28:], packed[uint8(indices[7])])
		binary.LittleEndian.PutUint32(dst[j+32:], packed[uint8(indices[8])])
		binary.LittleEndian.PutUint32(dst[j+36:], packed[uint8(indices[9])])
		binary.LittleEndian.PutUint32(dst[j+40:], packed[uint8(indices[10])])
		binary.LittleEndian.PutUint32(dst[j+44:], packed[uint8(indices[11])])
		binary.LittleEndian.PutUint32(dst[j+48:], packed[uint8(indices[12])])
		binary.LittleEndian.PutUint32(dst[j+52:], packed[uint8(indices[13])])
		binary.LittleEndian.PutUint32(dst[j+56:], packed[uint8(indices[14])])
		binary.LittleEndian.PutUint32(dst[j+60:], packed[uint8(indices[15])])
	}
	colorScalarFloat32Packed(dst[j:], data[j:], &packed)
}
