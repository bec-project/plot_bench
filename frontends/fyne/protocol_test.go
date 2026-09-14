package main

import (
	"encoding/binary"
	"encoding/json"
	"image/color"
	"math"
	"testing"
)

// testPacket is a protocol v2 frame with one waveform plot of one curve (samples
// -1, 0, 1) and one 3×1 image plot (scalar 0, .5, 1 or RGB red, green, blue).
func testPacket(seq uint64, view, imageMode string) []byte {
	c := Config{Hz: 60, Points: 3, AppendCount: 1, Curves: 1, WaveformPlots: 1, Width: 3, Height: 1, ImagePlots: 1, WaveformMode: "append", ImageMode: imageMode, View: view, Seed: 42}
	h := Header{Version: 2, Seq: seq, Config: c, Emitted: 1}
	payload := []byte{}
	if view != "image" {
		h.Arrays = append(h.Arrays, Array{"waveform", "float32", []int{1, 1, 3}, 0, 12})
		for _, v := range []float32{-1, 0, 1} {
			payload = binary.LittleEndian.AppendUint32(payload, math.Float32bits(v))
		}
	}
	if view != "waveform" {
		shape := []int{1, 1, 3}
		dtype := "float32"
		data := []byte{}
		if imageMode == "rgb" {
			shape = append(shape, 3)
			dtype = "uint8"
			data = []byte{255, 0, 0, 0, 255, 0, 0, 0, 255}
		} else {
			for _, v := range []float32{0, .5, 1} {
				data = binary.LittleEndian.AppendUint32(data, math.Float32bits(v))
			}
		}
		h.Arrays = append(h.Arrays, Array{"image", dtype, shape, len(payload), len(data)})
		payload = append(payload, data...)
	}
	return packet(h, payload)
}

// waveSample and imageSample are the distinct per-plot/per-curve values of multiPacket.
func waveSample(p, c, i int) float32   { return float32(p) + float32(c)/10 + float32(i)/100 }
func imageSample(p, i int) float32     { return float32(p)/10 + float32(i)/100 }
func rgbSample(p, i, channel int) byte { return byte(p*40 + i*3 + channel) }

// multiPacket is a protocol v2 frame with `plots` waveform plots of `curves` curves
// (3 points each) and `images` 2×2 image plots, every plot and curve holding
// distinct values so slicing can be verified.
func multiPacket(seq uint64, view, imageMode string, plots, curves, images int) []byte {
	c := Config{Hz: 60, Points: 3, AppendCount: 1, Curves: curves, WaveformPlots: plots, Width: 2, Height: 2, ImagePlots: images, WaveformMode: "replace", ImageMode: imageMode, View: view, Seed: 42}
	h := Header{Version: 2, Seq: seq, Config: c, Emitted: 1}
	payload := []byte{}
	if view != "image" {
		for p := 0; p < plots; p++ {
			for cv := 0; cv < curves; cv++ {
				for i := 0; i < 3; i++ {
					payload = binary.LittleEndian.AppendUint32(payload, math.Float32bits(waveSample(p, cv, i)))
				}
			}
		}
		h.Arrays = append(h.Arrays, Array{"waveform", "float32", []int{plots, curves, 3}, 0, len(payload)})
	}
	if view != "waveform" {
		shape := []int{images, 2, 2}
		dtype := "float32"
		data := []byte{}
		for p := 0; p < images; p++ {
			for i := 0; i < 4; i++ {
				if imageMode == "rgb" {
					data = append(data, rgbSample(p, i, 0), rgbSample(p, i, 1), rgbSample(p, i, 2))
				} else {
					data = binary.LittleEndian.AppendUint32(data, math.Float32bits(imageSample(p, i)))
				}
			}
		}
		if imageMode == "rgb" {
			shape = append(shape, 3)
			dtype = "uint8"
		}
		h.Arrays = append(h.Arrays, Array{"image", dtype, shape, len(payload), len(data)})
		payload = append(payload, data...)
	}
	return packet(h, payload)
}
func packet(h Header, payload []byte) []byte {
	b, _ := json.Marshal(h)
	out := binary.LittleEndian.AppendUint32(nil, uint32(len(b)))
	out = append(out, b...)
	for len(out)%4 != 0 {
		out = append(out, 0)
	}
	return append(out, payload...)
}
func replayPacket() []byte {
	out := binary.LittleEndian.AppendUint32(nil, 2)
	for seq := uint64(0); seq < 2; seq++ {
		p := testPacket(seq, "both", "scalar")
		out = binary.LittleEndian.AppendUint32(out, uint32(len(p)))
		out = append(out, p...)
	}
	return out
}
func TestDecodeLayoutsAndFullAppend(t *testing.T) {
	for _, view := range []string{"both", "waveform", "image"} {
		for _, mode := range []string{"scalar", "rgb"} {
			f, err := decode(testPacket(7, view, mode))
			if err != nil {
				t.Fatal(err)
			}
			if f.Seq != 7 || f.Header.Config.WaveformMode != "append" {
				t.Fatal(f)
			}
			if view != "image" && (len(f.Arrays["waveform"]) != 12 || scalar(f.Arrays["waveform"], 2) != 1) {
				t.Fatal("append window not retained")
			}
		}
	}
}
func TestRejectMalformedPackets(t *testing.T) {
	good := testPacket(0, "both", "scalar")
	f, _ := decode(good)
	payload := append(append([]byte{}, f.Arrays["waveform"]...), f.Arrays["image"]...)
	for _, mutate := range []func(*Header){
		func(h *Header) { h.Version = 1 },
		func(h *Header) { h.Version = 3 },
		func(h *Header) { h.Config.Points = 10000001 },
		func(h *Header) { h.Config.Hz = 0 },
		func(h *Header) { h.Config.Curves = 0 },
		func(h *Header) { h.Config.Curves = 65 },
		func(h *Header) { h.Config.WaveformPlots = 0 },
		func(h *Header) { h.Config.WaveformPlots = 17 },
		func(h *Header) { h.Config.ImagePlots = 0 },
		func(h *Header) { h.Config.ImagePlots = 17 },
		func(h *Header) { h.Arrays[0].Offset = 4 },
		func(h *Header) { h.Arrays[0].Shape = []int{1 << 60} },
		func(h *Header) { h.Arrays[0].Shape = []int{3} },
		func(h *Header) { h.Arrays[0].Shape = []int{1, 3} },
		func(h *Header) { h.Arrays[0].Shape = []int{1, 1, 3, 1} },
		func(h *Header) { h.Arrays[0].Shape = []int{1, 3, 1} },
		func(h *Header) { h.Arrays[1].Shape = []int{1, 3} },
		func(h *Header) { h.Arrays[1].Shape = []int{1, 3, 1} },
		func(h *Header) { h.Arrays[1].Shape = []int{1, 1, 3, 3}; h.Arrays[1].Dtype = "uint8" },
		func(h *Header) { h.Arrays[0].Nbytes = -1 },
		func(h *Header) { h.Arrays[1].Name = "waveform" },
		func(h *Header) { h.Arrays = h.Arrays[:1] },
		func(h *Header) { h.Config.View = "image" },
	} {
		h := f.Header
		h.Arrays = append([]Array{}, h.Arrays...)
		mutate(&h)
		if _, err := decode(packet(h, payload)); err == nil {
			t.Fatalf("accepted malformed header %+v", h)
		}
	}
	// A frame whose counts disagree with its payload (2 plots declared, 1 sent) is rejected.
	h := f.Header
	h.Arrays = append([]Array{}, h.Arrays...)
	h.Config.WaveformPlots = 2
	if _, err := decode(packet(h, payload)); err == nil {
		t.Fatal("accepted payload shorter than the configured plot count")
	}
	h.Arrays[0].Shape = []int{2, 1, 3}
	if _, err := decode(packet(h, payload)); err == nil {
		t.Fatal("accepted shape without matching payload")
	}
	for _, b := range [][]byte{nil, good[:3], good[:10], good[:len(good)-1], append(append([]byte{}, good...), 0)} {
		if _, err := decode(b); err == nil {
			t.Fatal("accepted truncation/trailing bytes")
		}
	}
}
func TestReplayBoundsAndSequence(t *testing.T) {
	b := replayPacket()
	frames, err := decodeReplay(b)
	if err != nil || len(frames) != 2 {
		t.Fatal(err)
	}
	for _, bad := range [][]byte{b[:3], b[:len(b)-1], append(append([]byte{}, b...), 0), {255, 255, 255, 255}} {
		if _, err := decodeReplay(bad); err == nil {
			t.Fatal("accepted malformed replay")
		}
	}
}
func TestColorConversionAndRaster(t *testing.T) {
	var palette [256]color.RGBA
	for i := range palette {
		palette[i] = color.RGBA{uint8(i), 0, 0, 255}
	}
	f, _ := decode(testPacket(0, "both", "scalar"))
	im := colorImage(f.imagePlot(0), f.Header.Config, palette)
	for i, v := range []uint8{0, 127, 255} {
		if im.RGBAAt(i, 0).R != v {
			t.Fatalf("LUT index %d: %v", i, im.RGBAAt(i, 0))
		}
	}
	f, _ = decode(testPacket(0, "image", "rgb"))
	im = colorImage(f.imagePlot(0), f.Header.Config, palette)
	if im.RGBAAt(1, 0) != (color.RGBA{0, 255, 0, 255}) {
		t.Fatal("RGB layout")
	}
	data := []byte{}
	for _, v := range []float32{-1.5, 1.5, -1.5} {
		data = binary.LittleEndian.AppendUint32(data, math.Float32bits(v))
	}
	wave := rasterWaveform([][]byte{data}, 3, 3)
	for _, p := range [][2]int{{0, 2}, {1, 0}, {2, 2}} {
		if wave.RGBAAt(p[0], p[1]) != accent {
			t.Fatal("lost waveform sample", p)
		}
	}
	if wave.Bounds().Dx() != 3 || wave.Bounds().Dy() != 3 {
		t.Fatal("physical dimensions")
	}
}
func TestMailboxReplacementAndGeneration(t *testing.T) {
	s := newSource("http://localhost", "stream")
	defer s.cancel()
	for i := uint64(0); i < 3; i++ {
		f, _ := decode(testPacket(i, "waveform", "scalar"))
		s.offer(f)
	}
	f, skipped := s.take()
	if f.Seq != 2 || skipped != 0 {
		t.Fatal(f, skipped)
	}
	f.Seq = 5
	s.offer(f)
	_, skipped = s.take()
	if skipped != 2 {
		t.Fatal(skipped)
	}
	f.Seq = 0
	f.Header.Generation = 1
	s.offer(f)
	_, skipped = s.take()
	if skipped != 0 {
		t.Fatal("cross-generation skips")
	}
	if f, _ = s.take(); f != nil {
		t.Fatal("mailbox not drained")
	}
}

func TestMissingIdentityIsRejected(t *testing.T) {
	good := testPacket(0, "waveform", "scalar")
	n := int(binary.LittleEndian.Uint32(good))
	var h map[string]any
	_ = json.Unmarshal(good[4:4+n], &h)
	for _, key := range []string{"seq", "generation", "emitted_at_ms"} {
		saved := h[key]
		delete(h, key)
		b, _ := json.Marshal(h)
		out := binary.LittleEndian.AppendUint32(nil, uint32(len(b)))
		out = append(out, b...)
		for len(out)%4 != 0 {
			out = append(out, 0)
		}
		out = append(out, good[(4+n+3)&^3:]...)
		if _, err := decode(out); err == nil {
			t.Fatal("accepted missing identity", key)
		}
		h[key] = saved
	}
}

func TestDecodeMultiPlotAndCurveSlices(t *testing.T) {
	for _, mode := range []string{"scalar", "rgb"} {
		f, err := decode(multiPacket(3, "both", mode, 2, 3, 2))
		if err != nil {
			t.Fatal(mode, err)
		}
		c := f.Header.Config
		if c.Curves != 3 || c.WaveformPlots != 2 || c.ImagePlots != 2 || len(f.Arrays["waveform"]) != 2*3*3*4 {
			t.Fatalf("configuration or waveform size %+v %d", c, len(f.Arrays["waveform"]))
		}
		for p := 0; p < 2; p++ {
			curves := f.waveformPlot(p)
			if len(curves) != 3 {
				t.Fatal("curves per plot", len(curves))
			}
			for cv, data := range curves {
				if len(data) != 12 || &data[0] != &f.Arrays["waveform"][(p*3+cv)*12] {
					t.Fatalf("curve %d of plot %d is not a zero-copy slice", cv, p)
				}
				for i := 0; i < 3; i++ {
					if float32(scalar(data, i)) != waveSample(p, cv, i) {
						t.Fatalf("plot %d curve %d sample %d: %v", p, cv, i, scalar(data, i))
					}
				}
			}
		}
		item := c.imageItem()
		if (mode == "rgb") != (item == 3) || len(f.Arrays["image"]) != 2*4*item {
			t.Fatal("image size", len(f.Arrays["image"]))
		}
		for p := 0; p < 2; p++ {
			block := f.imagePlot(p)
			if len(block) != 4*item || &block[0] != &f.Arrays["image"][p*4*item] {
				t.Fatalf("image plot %d is not a zero-copy slice", p)
			}
			for i := 0; i < 4; i++ {
				if mode == "rgb" {
					if block[i*3] != rgbSample(p, i, 0) || block[i*3+2] != rgbSample(p, i, 2) {
						t.Fatalf("image plot %d pixel %d: %v", p, i, block[i*3:i*3+3])
					}
				} else if float32(scalar(block, i)) != imageSample(p, i) {
					t.Fatalf("image plot %d pixel %d: %v", p, i, scalar(block, i))
				}
			}
		}
	}
	f, err := decode(multiPacket(0, "waveform", "scalar", 16, 64, 1))
	if err != nil || len(f.waveformPlot(15)) != 64 || float32(scalar(f.waveformCurve(15, 63), 2)) != waveSample(15, 63, 2) {
		t.Fatal("maximum plot and curve counts", err)
	}
	if _, err := decode(multiPacket(0, "image", "rgb", 1, 1, 16)); err != nil {
		t.Fatal("maximum image plots", err)
	}
}

func TestMultiImageConversionPerPlot(t *testing.T) {
	var palette [256]color.RGBA
	for i := range palette {
		palette[i] = color.RGBA{uint8(i), 0, 0, 255}
	}
	f, _ := decode(multiPacket(0, "image", "scalar", 1, 1, 3))
	for p := 0; p < 3; p++ {
		im := colorImage(f.imagePlot(p), f.Header.Config, palette)
		if im.Bounds().Dx() != 2 || im.Bounds().Dy() != 2 {
			t.Fatal("image plot dimensions")
		}
		for i := 0; i < 4; i++ {
			want := uint8(math.Floor(float64(imageSample(p, i)) * 255))
			if got := im.RGBAAt(i%2, i/2).R; got != want {
				t.Fatalf("image plot %d pixel %d: %d != %d", p, i, got, want)
			}
		}
	}
	f, _ = decode(multiPacket(0, "image", "rgb", 1, 1, 2))
	im := colorImage(f.imagePlot(1), f.Header.Config, palette)
	if im.RGBAAt(1, 1) != (color.RGBA{rgbSample(1, 3, 0), rgbSample(1, 3, 1), rgbSample(1, 3, 2), 255}) {
		t.Fatal("RGB plot 1 pixel", im.RGBAAt(1, 1))
	}
}

func TestRasterColoursCurvesByIndex(t *testing.T) {
	constant := func(v float32) []byte {
		data := []byte{}
		for i := 0; i < 3; i++ {
			data = binary.LittleEndian.AppendUint32(data, math.Float32bits(v))
		}
		return data
	}
	curves := [][]byte{}
	for cv := 0; cv < 9; cv++ {
		curves = append(curves, constant(1.5-float32(cv)*0.375)) // rows 0..8 of a 9-row image
	}
	wave := rasterWaveform(curves, 3, 9)
	for cv := 0; cv < 9; cv++ {
		want := curveColors[cv%8]
		if cv == 8 && want != accent {
			t.Fatal("palette does not wrap at 8")
		}
		for x := 0; x < 3; x++ {
			if got := wave.RGBAAt(x, cv); got != want {
				t.Fatalf("curve %d pixel %d: %v != %v", cv, x, got, want)
			}
		}
	}
	if curveColors[1] != (color.RGBA{0xf5, 0xc7, 0x6e, 255}) || curveColors[7] != (color.RGBA{0x6e, 0xe7, 0xff, 255}) {
		t.Fatal("palette differs from CURVE_COLORS")
	}
	// Later curves overdraw earlier ones and NaN gaps do not join segments.
	gap := constant(1.5)
	binary.LittleEndian.PutUint32(gap[4:], math.Float32bits(float32(math.NaN())))
	wave = rasterWaveform([][]byte{constant(1.5), gap}, 3, 3)
	if wave.RGBAAt(0, 0) != curveColors[1] || wave.RGBAAt(1, 0) != accent || wave.RGBAAt(2, 0) != curveColors[1] {
		t.Fatal("overdraw order or NaN gap", wave.RGBAAt(0, 0), wave.RGBAAt(1, 0), wave.RGBAAt(2, 0))
	}
	if wave.RGBAAt(1, 1) != plotBackground {
		t.Fatal("background")
	}
}

func TestMissingPlotFieldsAreRejected(t *testing.T) {
	good := testPacket(0, "both", "scalar")
	n := int(binary.LittleEndian.Uint32(good))
	var h map[string]any
	_ = json.Unmarshal(good[4:4+n], &h)
	config := h["config"].(map[string]any)
	for _, key := range []string{"curves", "waveform_plots", "image_plots"} {
		saved := config[key]
		delete(config, key)
		b, _ := json.Marshal(h)
		out := binary.LittleEndian.AppendUint32(nil, uint32(len(b)))
		out = append(out, b...)
		for len(out)%4 != 0 {
			out = append(out, 0)
		}
		out = append(out, good[(4+n+3)&^3:]...)
		if _, err := decode(out); err == nil {
			t.Fatal("accepted missing configuration", key)
		}
		config[key] = saved
	}
}
