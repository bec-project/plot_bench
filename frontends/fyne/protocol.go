package main

import (
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"reflect"
)

const maxPacket = 257 * 1024 * 1024
const maxReplay = 256 * 1024 * 1024

type Config struct {
	Hz           float64 `json:"hz"`
	Points       int     `json:"points"`
	AppendCount  int     `json:"append_count"`
	Width        int     `json:"width"`
	Height       int     `json:"height"`
	WaveformMode string  `json:"waveform_mode"`
	ImageMode    string  `json:"image_mode"`
	View         string  `json:"view"`
	Seed         uint64  `json:"seed"`
	Generation   uint64  `json:"generation"`
}
type Array struct {
	Name   string `json:"name"`
	Dtype  string `json:"dtype"`
	Shape  []int  `json:"shape"`
	Offset int    `json:"offset"`
	Nbytes int    `json:"nbytes"`
}
type Header struct {
	Version    int     `json:"version"`
	Seq        uint64  `json:"seq"`
	Generation uint64  `json:"generation"`
	Emitted    float64 `json:"emitted_at_ms"`
	Config     Config  `json:"config"`
	Arrays     []Array `json:"arrays"`
}
type Frame struct {
	Header Header
	Arrays map[string][]byte // immutable slices into one owned packet
	Seq    uint64            // replay presentation sequence, independent of payload sequence
}

func finite(v float64) bool { return !math.IsNaN(v) && !math.IsInf(v, 0) }
func decode(data []byte) (*Frame, error) {
	if len(data) < 4 || len(data) > maxPacket {
		return nil, errors.New("invalid packet length")
	}
	n := int(binary.LittleEndian.Uint32(data))
	end := 4 + n
	payload := (end + 3) &^ 3
	if n > 65536 || payload > len(data) {
		return nil, errors.New("invalid header length")
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data[4:end], &fields); err != nil {
		return nil, err
	}
	for _, key := range []string{"version", "seq", "generation", "emitted_at_ms", "config", "arrays"} {
		if len(fields[key]) == 0 || string(fields[key]) == "null" {
			return nil, fmt.Errorf("missing header %s", key)
		}
	}
	var configFields map[string]json.RawMessage
	if err := json.Unmarshal(fields["config"], &configFields); err != nil {
		return nil, err
	}
	for _, key := range []string{"hz", "points", "append_count", "width", "height", "waveform_mode", "image_mode", "view", "seed", "generation"} {
		if len(configFields[key]) == 0 || string(configFields[key]) == "null" {
			return nil, fmt.Errorf("missing configuration %s", key)
		}
	}
	var h Header
	if err := json.Unmarshal(data[4:end], &h); err != nil {
		return nil, err
	}
	c := h.Config
	if h.Version != 1 || !finite(h.Emitted) || !finite(c.Hz) || c.Hz <= 0 || c.Hz > 120 || c.Points < 1 || c.Points > 10000000 || c.Width < 1 || c.Width > 8192 || c.Height < 1 || c.Height > 8192 || c.AppendCount < 1 || c.AppendCount > c.Points {
		return nil, errors.New("invalid header/configuration")
	}
	if (c.WaveformMode != "append" && c.WaveformMode != "replace") || (c.ImageMode != "rgb" && c.ImageMode != "scalar") || (c.View != "both" && c.View != "waveform" && c.View != "image") {
		return nil, errors.New("invalid modes")
	}
	f := &Frame{Header: h, Seq: h.Seq, Arrays: map[string][]byte{}}
	offset := 0
	for _, a := range h.Arrays {
		var shape []int
		dtype := "float32"
		item := 4
		switch a.Name {
		case "waveform":
			if c.View == "image" {
				return nil, errors.New("unexpected waveform")
			}
			shape = []int{c.Points}
		case "image":
			if c.View == "waveform" {
				return nil, errors.New("unexpected image")
			}
			shape = []int{c.Height, c.Width}
			if c.ImageMode == "rgb" {
				shape = append(shape, 3)
				dtype = "uint8"
				item = 1
			}
		default:
			return nil, errors.New("unknown array")
		}
		size := item
		for _, s := range shape {
			size *= s
		}
		if _, ok := f.Arrays[a.Name]; ok || a.Dtype != dtype || !reflect.DeepEqual(a.Shape, shape) || a.Nbytes != size || a.Offset != offset || a.Offset%item != 0 || size > len(data)-payload-offset {
			return nil, fmt.Errorf("invalid array %s", a.Name)
		}
		f.Arrays[a.Name] = data[payload+offset : payload+offset+size]
		offset += size
	}
	expected := 1
	if c.View == "both" {
		expected = 2
	}
	if len(f.Arrays) != expected || offset != len(data)-payload || offset > maxReplay {
		return nil, errors.New("missing arrays or trailing payload")
	}
	return f, nil
}
func decodeReplay(data []byte) ([]*Frame, error) {
	if len(data) < 4 || len(data) > maxReplay {
		return nil, errors.New("invalid replay size")
	}
	count := int(binary.LittleEndian.Uint32(data))
	if count < 2 || count > 256 {
		return nil, errors.New("invalid replay count")
	}
	frames := make([]*Frame, 0, count)
	offset := 4
	for i := 0; i < count; i++ {
		if len(data)-offset < 4 {
			return nil, errors.New("truncated replay length")
		}
		n := int(binary.LittleEndian.Uint32(data[offset:]))
		offset += 4
		if n > len(data)-offset {
			return nil, errors.New("truncated replay frame")
		}
		f, err := decode(data[offset : offset+n])
		if err != nil {
			return nil, err
		}
		offset += n
		if i > 0 && (f.Header.Config != frames[0].Header.Config || f.Header.Generation != frames[0].Header.Generation || f.Header.Seq <= frames[i-1].Header.Seq) {
			return nil, errors.New("inconsistent replay configuration or sequence")
		}
		frames = append(frames, f)
	}
	if offset != len(data) {
		return nil, errors.New("trailing replay data")
	}
	return frames, nil
}
func scalar(data []byte, i int) float64 {
	return float64(math.Float32frombits(binary.LittleEndian.Uint32(data[i*4:])))
}
