//go:build js && wasm

package main

import (
	"encoding/json"
	"syscall/js"
	"testing"
	"time"
)

// These tests run in Node with Go's go_js_wasm_exec and a small WebSocket fake;
// they exercise the actual browser transport callbacks without a Fyne window.
func fakeBrowserSocket(t *testing.T, s *Source) (js.Value, <-chan browserSocketResult) {
	t.Helper()
	previous := js.Global().Get("WebSocket")
	js.Global().Get("Function").New(`
globalThis.WebSocket = class {
  constructor() { this.readyState = 1; this.handlers = {}; this.sent = []; globalThis.testSocket = this; }
  addEventListener(name, callback) { this.handlers[name] = callback; }
  removeEventListener(name) { delete this.handlers[name]; }
  emit(name, data) { this.handlers[name]({data}); }
  send(message) { if (globalThis.beforeAck) globalThis.beforeAck(); this.sent.push(message); }
  close() { this.readyState = 3; }
};`).Invoke()
	t.Cleanup(func() {
		js.Global().Set("WebSocket", previous)
		js.Global().Delete("testSocket")
	})
	done := make(chan browserSocketResult, 1)
	go func() { connected := false; done <- s.browserStream("ws://localhost/ws", &connected) }()
	deadline := time.Now().Add(time.Second)
	for js.Global().Get("testSocket").IsUndefined() && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	ws := js.Global().Get("testSocket")
	if ws.IsUndefined() {
		t.Fatal("browser WebSocket was not created")
	}
	ws.Call("emit", "open", js.Undefined())
	return ws, done
}

func emitBrowserPacket(ws js.Value, packet []byte) {
	data := js.Global().Get("Uint8Array").New(len(packet))
	js.CopyBytesToJS(data, packet)
	ws.Call("emit", "message", data.Get("buffer"))
}

func TestBrowserDecodeOfferThenAckAndClose(t *testing.T) {
	s := newSource("http://localhost", "stream")
	defer s.cancel()
	ws, done := fakeBrowserSocket(t, s)
	beforeAck := js.FuncOf(func(js.Value, []js.Value) any {
		if s.latest == nil {
			t.Error("ACK preceded decoding and mailbox offer")
		}
		return nil
	})
	js.Global().Set("beforeAck", beforeAck)
	defer func() { js.Global().Delete("beforeAck"); beforeAck.Release() }()
	for seq := uint64(0); seq < 3; seq++ {
		emitBrowserPacket(ws, multiPacket(seq, "both", "rgb", 2, 3, 2))
	}
	f, _ := s.take()
	if f == nil || f.Seq != 2 || len(f.waveformPlot(1)) != 3 || len(f.imagePlot(1)) != 12 {
		t.Fatal("latest multi-plot frame not retained")
	}
	if ws.Get("sent").Length() != 3 {
		t.Fatal("missing per-received-frame ACK")
	}
	var ack map[string]uint64
	if err := json.Unmarshal([]byte(ws.Get("sent").Index(2).String()), &ack); err != nil || ack["ack"] != 2 || ack["generation"] != 0 {
		t.Fatal("wrong ACK", ack, err)
	}
	s.cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("cancel did not stop browser receiver")
	}
	if ws.Get("readyState").Int() != 3 || js.Global().Get("Object").Call("keys", ws.Get("handlers")).Length() != 0 {
		t.Fatal("socket or callbacks leaked")
	}
}

func TestBrowserNonBinaryFrameReconnects(t *testing.T) {
	s := newSource("http://localhost", "stream")
	defer s.cancel()
	ws, done := fakeBrowserSocket(t, s)
	// A non-binary (text) frame is a protocol violation that must drop the
	// connection and reconnect, matching the native reader, not fail the run.
	ws.Call("emit", "message", js.ValueOf("not-binary"))
	select {
	case result := <-done:
		if result.fatal || result.err == nil {
			t.Fatal("non-binary frame should be a non-fatal reconnect")
		}
	case <-time.After(time.Second):
		t.Fatal("non-binary frame was not rejected")
	}
	if ws.Get("sent").Length() != 0 || s.latest != nil {
		t.Fatal("non-binary frame was offered or acknowledged")
	}
}

func TestBrowserMalformedFrameDoesNotAck(t *testing.T) {
	s := newSource("http://localhost", "stream")
	defer s.cancel()
	ws, done := fakeBrowserSocket(t, s)
	emitBrowserPacket(ws, []byte{1, 2, 3})
	select {
	case result := <-done:
		if !result.fatal || result.err == nil {
			t.Fatal("invalid frame did not fail permanently")
		}
	case <-time.After(time.Second):
		t.Fatal("invalid frame was not rejected")
	}
	if ws.Get("sent").Length() != 0 || s.latest != nil {
		t.Fatal("invalid frame was offered or acknowledged")
	}
}
