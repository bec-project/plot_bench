//go:build js && wasm

package main

import (
	"encoding/json"
	"fmt"
	"net/url"
	"syscall/js"
	"time"
)

type browserSocketResult struct {
	err   error
	fatal bool
}

func (s *Source) stream() error {
	u, _ := url.Parse(endpoint(s.base, "/ws"))
	if u.Scheme == "https" {
		u.Scheme = "wss"
	} else {
		u.Scheme = "ws"
	}
	connected := false
	for s.ctx.Err() == nil {
		result := s.browserStream(u.String(), &connected)
		if result.fatal {
			return result.err
		}
		s.mu.Lock()
		s.status = "Reconnecting"
		s.mu.Unlock()
		select {
		case <-s.ctx.Done():
			return s.ctx.Err()
		case <-time.After(time.Second):
		}
	}
	return s.ctx.Err()
}

func (s *Source) browserStream(address string, connected *bool) browserSocketResult {
	ws := js.Global().Get("WebSocket").New(address)
	ws.Set("binaryType", "arraybuffer")
	result := make(chan browserSocketResult, 1)
	activity := make(chan struct{}, 1)
	finish := func(err error, fatal bool) {
		select {
		case result <- browserSocketResult{err: err, fatal: fatal}:
		default:
		}
	}
	opened := js.FuncOf(func(js.Value, []js.Value) any {
		if *connected {
			s.mu.Lock()
			s.reconnects++
			s.mu.Unlock()
		}
		*connected = true
		return nil
	})
	message := js.FuncOf(func(_ js.Value, args []js.Value) any {
		data := args[0].Get("data")
		// A malformed frame type or over-limit packet drops the connection and
		// reconnects, matching the native reader (which breaks the read loop on
		// the same violations). Only an undecodable frame is fatal, as there too.
		if !data.InstanceOf(js.Global().Get("ArrayBuffer")) {
			finish(fmt.Errorf("expected binary source frame"), false)
			return nil
		}
		size := data.Get("byteLength").Int()
		if size > maxPacket {
			finish(fmt.Errorf("source frame exceeds %d bytes", maxPacket), false)
			return nil
		}
		packet := make([]byte, size)
		js.CopyBytesToGo(packet, js.Global().Get("Uint8Array").New(data))
		f, err := decode(packet)
		if err != nil {
			finish(err, true)
			return nil
		}
		// Decode and offer before acknowledging. The source's one in-flight
		// frame and one pending frame bound browser and Go mailbox accumulation.
		s.offer(f)
		ack, _ := json.Marshal(map[string]uint64{"ack": f.Header.Seq, "generation": f.Header.Generation})
		if ws.Get("readyState").Int() == 1 {
			ws.Call("send", string(ack))
		}
		select {
		case activity <- struct{}{}:
		default:
		}
		return nil
	})
	closed := js.FuncOf(func(js.Value, []js.Value) any {
		finish(fmt.Errorf("source WebSocket closed"), false)
		return nil
	})
	failed := js.FuncOf(func(js.Value, []js.Value) any {
		finish(fmt.Errorf("source WebSocket failed"), false)
		return nil
	})
	callbacks := map[string]js.Func{"open": opened, "message": message, "close": closed, "error": failed}
	for event, callback := range callbacks {
		ws.Call("addEventListener", event, callback)
	}
	defer func() {
		for event, callback := range callbacks {
			ws.Call("removeEventListener", event, callback)
			callback.Release()
		}
		ws.Call("close")
	}()
	timeout := time.NewTimer(40 * time.Second)
	defer timeout.Stop()
	for {
		select {
		case <-s.ctx.Done():
			return browserSocketResult{err: s.ctx.Err()}
		case r := <-result:
			return r
		case <-activity:
			timeout.Reset(40 * time.Second)
		case <-timeout.C:
			return browserSocketResult{err: fmt.Errorf("source WebSocket receive timeout")}
		}
	}
}
