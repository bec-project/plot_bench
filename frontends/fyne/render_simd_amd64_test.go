//go:build go1.27 && goexperiment.simd && amd64

package main

import (
	"bytes"
	"fmt"
	"image/color"
	"math"
	"math/rand/v2"
	"simd/archsimd"
	"testing"
)

func TestAMD64ConversionKernelFeatureSelection(t *testing.T) {
	for _, test := range []struct {
		avx, avx512 bool
		want        string
	}{
		{false, false, "scalar-float64"},
		{false, true, "scalar-float64"},
		{true, false, "simd128-float32-amd64-avx"},
		{true, true, "simd512-float32-amd64-avx512"},
	} {
		if got := amd64ConversionKernel(test.avx, test.avx512); got != test.want {
			t.Errorf("AVX=%t AVX512=%t: got %q, want %q", test.avx, test.avx512, got, test.want)
		}
	}
}

// Run with GODEBUG=cpu.avx=off and GODEBUG=cpu.avx512f=off too: the former
// requires the exact scalar oracle, the latter exercises AVX on capable hosts.
func TestAMD64ConversionKernelMatchesAvailableCPU(t *testing.T) {
	want := "scalar-float64"
	if archsimd.X86.AVX() {
		want = "simd128-float32-amd64-avx"
		if archsimd.X86.AVX512() {
			want = "simd512-float32-amd64-avx512"
		}
	}
	if got := imageConversionKernel(); got != want {
		t.Fatalf("conversion kernel %q, want %q for this CPU", got, want)
	}
	t.Logf("AVX=%t AVX512=%t image_conversion_kernel=%s", archsimd.X86.AVX(), archsimd.X86.AVX512(), want)
}

// Every available SIMD kernel must exactly match float32 scalar conversion,
// even though the earlier float64 implementation permits a one-entry difference.
// Unsupported kernels skip here; their guarded fallback entrypoints are tested
// separately without executing instructions unavailable on the current CPU.
func TestAMD64SIMDKernelsMatchFloat32(t *testing.T) {
	for _, kernel := range []struct {
		name      string
		available bool
		convert   func([]byte, []byte, *[256]color.RGBA)
	}{
		{"avx128", archsimd.X86.AVX(), colorScalarAVX128},
		{"avx512", archsimd.X86.AVX() && archsimd.X86.AVX512(), colorScalarAVX512},
	} {
		t.Run(kernel.name, func(t *testing.T) {
			if !kernel.available {
				t.Skip("CPU/OS SIMD capability unavailable")
			}
			checkAMD64Kernel(t, kernel.convert, colorScalarFloat32)
		})
	}
}

func TestAMD64SIMDKernelGuardedFallbacks(t *testing.T) {
	reference := colorScalarFloat32
	if !archsimd.X86.AVX() {
		reference = colorScalarFloat64
	}
	if !archsimd.X86.AVX() {
		t.Run("avx128-to-scalar", func(t *testing.T) {
			checkAMD64Kernel(t, colorScalarAVX128, reference)
		})
	}
	if !archsimd.X86.AVX() || !archsimd.X86.AVX512() {
		t.Run("avx512-fallback", func(t *testing.T) {
			checkAMD64Kernel(t, colorScalarAVX512, reference)
		})
	}
}

func checkAMD64Kernel(t *testing.T, convert, reference func([]byte, []byte, *[256]color.RGBA)) {
	t.Helper()
	values := []float32{
		math.Float32frombits(0x7fc00001), math.Float32frombits(0x7f800001),
		math.Float32frombits(0xffc00001), math.Float32frombits(0xff800001),
		float32(math.Inf(-1)), float32(math.Inf(1)), math.Float32frombits(0x80000000),
		0, -1, 1, 2, -math.MaxFloat32, math.MaxFloat32,
		-math.SmallestNonzeroFloat32, math.SmallestNonzeroFloat32,
	}
	for i := 0; i < 256; i++ {
		boundary := float32(float64(i) / 255)
		values = append(values, math.Nextafter32(boundary, float32(math.Inf(-1))), boundary,
			math.Nextafter32(boundary, float32(math.Inf(1))))
	}
	rng := rand.New(rand.NewPCG(721, 982))
	for i := 0; i < 8192; i++ {
		values = append(values, math.Float32frombits(rng.Uint32()))
	}
	payload := renderScalarBytes(values)
	palette := renderPalette()
	counts := make([]int, 66)
	for i := range counts {
		counts[i] = i
	}
	counts = append(counts, len(values)-1, len(values))
	for _, offset := range []int{1, 2, 3, 7, 15, 31, 32, 63} {
		for _, count := range counts {
			t.Run(fmt.Sprintf("offset%d/pixels%d", offset, count), func(t *testing.T) {
				input := make([]byte, offset+count*4)
				copy(input[offset:], payload[:count*4])
				backing := bytes.Repeat([]byte{0x5a}, count*4+10)
				dst := backing[3 : 3+count*4]
				want := make([]byte, len(dst))
				reference(want, input[offset:], &palette)
				convert(dst, input[offset:], &palette)
				if !bytes.Equal(dst, want) {
					t.Fatal("conversion differs from scalar arithmetic oracle")
				}
				if !bytes.Equal(backing[:3], []byte{0x5a, 0x5a, 0x5a}) || !bytes.Equal(backing[3+len(dst):], bytes.Repeat([]byte{0x5a}, 7)) {
					t.Fatal("conversion wrote beyond destination")
				}
				if !bytes.Equal(input[offset:], payload[:count*4]) {
					t.Fatal("conversion changed source bytes")
				}
				// Reusing the output must rewrite the full frame, including tails.
				clear(input[offset:])
				reference(want, input[offset:], &palette)
				convert(dst, input[offset:], &palette)
				if !bytes.Equal(dst, want) {
					t.Fatal("conversion retained pixels from the earlier frame")
				}
			})
		}
	}
	dst := make([]byte, len(payload))
	if allocs := testing.AllocsPerRun(10, func() { convert(dst, payload, &palette) }); allocs != 0 {
		t.Fatalf("conversion allocated %g times per frame, want 0", allocs)
	}
}
