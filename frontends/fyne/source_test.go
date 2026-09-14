package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

func paletteResponse(w http.ResponseWriter) {
	p := make([][3]int, 256)
	_ = json.NewEncoder(w).Encode(p)
}
func TestStreamAcknowledgesDecodedFrameAndCloses(t *testing.T) {
	ack := make(chan map[string]uint64, 1)
	closed := make(chan struct{})
	upgrade := websocket.Upgrader{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/colormap" {
			paletteResponse(w)
			return
		}
		c, err := upgrade.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer c.Close()
		defer close(closed)
		_ = c.WriteMessage(websocket.BinaryMessage, testPacket(17, "both", "rgb"))
		var a map[string]uint64
		_ = c.ReadJSON(&a)
		ack <- a
		_, _, _ = c.ReadMessage()
	}))
	defer srv.Close()
	s := newSource(srv.URL, "stream")
	s.start()
	select {
	case a := <-ack:
		if a["ack"] != 17 || a["generation"] != 0 {
			t.Fatal(a)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("missing ACK")
	}
	f, _ := s.take()
	if f == nil || f.Seq != 17 {
		t.Fatal("frame not offered before ACK")
	}
	s.close()
	select {
	case <-closed:
	case <-time.After(time.Second):
		t.Fatal("socket not closed")
	}
}
func TestReplayPreloadsOnceAndCyclesPresentationSequence(t *testing.T) {
	var requests atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/colormap":
			paletteResponse(w)
		case "/api/replay":
			requests.Add(1)
			_, _ = w.Write(replayPacket())
		default:
			t.Error("unexpected scheduling request", r.URL.Path)
		}
	}))
	defer srv.Close()
	s := newSource(srv.URL, "replay")
	s.start()
	deadline := time.Now().Add(3 * time.Second)
	var f *Frame
	for time.Now().Before(deadline) {
		f, _ = s.take()
		if f != nil && f.Seq >= 3 {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}
	s.close()
	if f == nil || f.Seq < 3 || f.Header.Seq > 1 {
		t.Fatal("replay presentation/payload sequence", f)
	}
	if requests.Load() != 1 {
		t.Fatal("repeated preload")
	}
}
func TestMetricsFinalMetadataAndFailure(t *testing.T) {
	var batch map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&batch)
		w.WriteHeader(200)
	}))
	m := newMetrics(srv.URL, "replay", "test", map[string]any{"termination_reason": "user", "active_seconds": 0.0})
	if err := m.close(); err != nil {
		t.Fatal(err)
	}
	srv.Close()
	if len(batch["samples"].([]any)) != 0 || batch["metadata"].(map[string]any)["termination_reason"] != "user" {
		t.Fatal(batch)
	}
	m = newMetrics(srv.URL, "stream", "test", map[string]any{})
	m.record(Sample{})
	if m.close() == nil || m.lost != 1 {
		t.Fatal("failed export not accounted")
	}
}

func TestViewControlRequiresAuthoritativeStreamConfirmation(t *testing.T) {
	s := newSource("http://localhost", "stream")
	defer s.cancel()
	s.pending = true
	s.requestedView = "image"
	s.requestedGeneration = 1
	f, _ := decode(testPacket(1, "image", "scalar"))
	f.Header.Generation = 1
	s.offer(f)
	if !s.pending {
		t.Fatal("old generation confirmed control")
	}
	f.Header.Generation = 2
	s.offer(f)
	if s.pending {
		t.Fatal("new view not confirmed")
	}
}

func TestReplayViewChangeReloadsOnlyAfterExplicitRequest(t *testing.T) {
	var gets, posts atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/colormap":
			paletteResponse(w)
		case "/api/replay":
			gets.Add(1)
			_, _ = w.Write(replayPacket())
		case "/api/config":
			if r.Method != "POST" {
				t.Error("unexpected config polling")
			}
			posts.Add(1)
			w.WriteHeader(200)
		}
	}))
	defer srv.Close()
	s := newSource(srv.URL, "replay")
	s.start()
	defer s.close()
	deadline := time.Now().Add(3 * time.Second)
	for gets.Load() == 0 && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	// Wait for initial preload to be adopted before issuing an interactive reload.
	for time.Now().Before(deadline) {
		f, _ := s.take()
		if f != nil {
			break
		}
		time.Sleep(time.Millisecond)
	}
	s.requestView("image")
	for gets.Load() < 2 && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	if gets.Load() != 2 || posts.Load() != 1 {
		t.Fatal("explicit reload not honored", gets.Load(), posts.Load())
	}
}
