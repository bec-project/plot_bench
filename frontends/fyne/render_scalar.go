//go:build !go1.27 || !goexperiment.simd || (!amd64 && !arm64 && !wasm)

package main

import "image/color"

func imageConversionKernel() string { return "scalar-float64" }

func colorImageScalar(dst, data []byte, palette *[256]color.RGBA) {
	colorScalarFloat64(dst, data, palette)
}
