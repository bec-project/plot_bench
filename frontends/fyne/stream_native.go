//go:build !js

package main

import (
	"context"
	"fmt"
	"net/url"
	"time"

	"github.com/gorilla/websocket"
)

func (s *Source) stream() error {
	u, _ := url.Parse(endpoint(s.base, "/ws"))
	if u.Scheme == "https" {
		u.Scheme = "wss"
	} else {
		u.Scheme = "ws"
	}
	connected := false
	for s.ctx.Err() == nil {
		conn, _, err := websocket.DefaultDialer.DialContext(s.ctx, u.String(), nil)
		if err == nil {
			if connected {
				s.mu.Lock()
				s.reconnects++
				s.mu.Unlock()
			}
			connected = true
			conn.SetReadLimit(maxPacket)
			stop := context.AfterFunc(s.ctx, func() { _ = conn.Close() })
			for {
				_ = conn.SetReadDeadline(time.Now().Add(40 * time.Second))
				var typ int
				var b []byte
				typ, b, err = conn.ReadMessage()
				if err != nil {
					break
				}
				if typ != websocket.BinaryMessage {
					err = fmt.Errorf("expected binary source frame")
					break
				}
				var f *Frame
				f, err = decode(b)
				if err != nil {
					stop()
					_ = conn.Close()
					return err
				}
				s.offer(f)
				_ = conn.SetWriteDeadline(time.Now().Add(3 * time.Second))
				err = conn.WriteJSON(map[string]uint64{"ack": f.Header.Seq, "generation": f.Header.Generation})
				if err != nil {
					break
				}
			}
			stop()
			_ = conn.Close()
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
