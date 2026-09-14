package main

import (
	"encoding/binary"
	"encoding/json"
	"image/color"
	"math"
	"testing"
)

func testPacket(seq uint64, view, imageMode string) []byte {
	c := Config{Hz: 60, Points: 3, AppendCount: 1, Width: 3, Height: 1, WaveformMode: "append", ImageMode: imageMode, View: view, Seed: 42}
	h := Header{Version: 1, Seq: seq, Config: c, Emitted: 1}
	payload := []byte{}
	if view != "image" {
		h.Arrays = append(h.Arrays, Array{"waveform", "float32", []int{3}, 0, 12})
		for _, v := range []float32{-1, 0, 1} {
			payload = binary.LittleEndian.AppendUint32(payload, math.Float32bits(v))
		}
	}
	if view != "waveform" {
		shape := []int{1, 3}
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
	for _, mutate := range []func(*Header){func(h *Header) { h.Version = 2 }, func(h *Header) { h.Config.Points = 10000001 }, func(h *Header) { h.Config.Hz = 0 }, func(h *Header) { h.Arrays[0].Offset = 4 }, func(h *Header) { h.Arrays[0].Shape = []int{1 << 60} }, func(h *Header) { h.Arrays[0].Nbytes = -1 }, func(h *Header) { h.Arrays[1].Name = "waveform" }, func(h *Header) { h.Arrays = h.Arrays[:1] }, func(h *Header) { h.Config.View = "image" }} {
		h := f.Header
		h.Arrays = append([]Array{}, h.Arrays...)
		mutate(&h)
		if _, err := decode(packet(h, payload)); err == nil {
			t.Fatalf("accepted malformed header %+v", h)
		}
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
	im := colorImage(f, palette)
	for i, v := range []uint8{0, 127, 255} {
		if im.RGBAAt(i, 0).R != v {
			t.Fatalf("LUT index %d: %v", i, im.RGBAAt(i, 0))
		}
	}
	f, _ = decode(testPacket(0, "image", "rgb"))
	im = colorImage(f, palette)
	if im.RGBAAt(1, 0) != (color.RGBA{0, 255, 0, 255}) {
		t.Fatal("RGB layout")
	}
	data := []byte{}
	for _, v := range []float32{-1.5, 1.5, -1.5} {
		data = binary.LittleEndian.AppendUint32(data, math.Float32bits(v))
	}
	wave := rasterWaveform(data, 3, 3)
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
