package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"image/color"
	"io"
	"net/http"
	"net/url"
	"sync"
	"time"
)

var httpClient = &http.Client{Timeout: 30 * time.Second}

func endpoint(base, path string) string {
	u, _ := url.Parse(base)
	u.Path = path
	u.RawQuery = ""
	u.Fragment = ""
	return u.String()
}
func fetch(ctx context.Context, base, path string, limit int) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", endpoint(base, path), nil)
	if err != nil {
		return nil, err
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("GET %s: %s", path, resp.Status)
	}
	b, err := io.ReadAll(io.LimitReader(resp.Body, int64(limit)+1))
	if len(b) > limit {
		return nil, fmt.Errorf("response exceeds %d bytes", limit)
	}
	return b, err
}
func post(ctx context.Context, base, path string, body any) error {
	b, err := json.Marshal(body)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, "POST", endpoint(base, path), bytes.NewReader(b))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 65536))
	if resp.StatusCode >= 300 {
		return fmt.Errorf("POST %s: %s", path, resp.Status)
	}
	return nil
}

type Source struct {
	requestedView            string
	requestedGeneration      uint64
	mu                       sync.Mutex
	latest                   *Frame
	status                   string
	err                      error
	reconnects               int
	replayCount, replayBytes int
	palette                  [256]color.RGBA
	pending                  bool
	viewError                string
	lastSeq, lastGeneration  uint64
	taken                    bool
	ctx                      context.Context
	cancel                   context.CancelFunc
	done                     chan struct{}
	reload                   chan struct{}
	base, mode               string
}

func newSource(base, mode string) *Source {
	ctx, cancel := context.WithCancel(context.Background())
	return &Source{ctx: ctx, cancel: cancel, done: make(chan struct{}), reload: make(chan struct{}, 1), base: base, mode: mode, status: "Connecting"}
}
func (s *Source) start() { go s.run() }
func (s *Source) close() { s.cancel(); <-s.done }
func (s *Source) fail(err error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.err = err
	s.status = err.Error()
}
func (s *Source) offer(f *Frame) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.latest = f
	s.status = "Connected"
	if s.pending && s.mode == "stream" && f.Header.Config.View == s.requestedView && f.Header.Generation > s.requestedGeneration {
		s.pending = false
	}
}
func (s *Source) take() (*Frame, uint64) {
	s.mu.Lock()
	defer s.mu.Unlock()
	f := s.latest
	s.latest = nil
	if f == nil {
		return nil, 0
	}
	skipped := uint64(0)
	if s.taken && s.lastGeneration == f.Header.Generation && f.Seq > s.lastSeq {
		skipped = f.Seq - s.lastSeq - 1
	}
	s.lastSeq = f.Seq
	s.lastGeneration = f.Header.Generation
	s.taken = true
	return f, skipped
}
func (s *Source) run() {
	defer close(s.done)
	b, err := fetch(s.ctx, s.base, "/api/colormap", 65536)
	if err != nil {
		s.fail(err)
		return
	}
	var lut [][]int
	if err = json.Unmarshal(b, &lut); err != nil || len(lut) != 256 {
		s.fail(fmt.Errorf("invalid source palette"))
		return
	}
	for i, p := range lut {
		if len(p) != 3 || p[0] < 0 || p[0] > 255 || p[1] < 0 || p[1] > 255 || p[2] < 0 || p[2] > 255 {
			s.fail(fmt.Errorf("invalid palette entry"))
			return
		}
		s.palette[i] = color.RGBA{uint8(p[0]), uint8(p[1]), uint8(p[2]), 255}
	}
	if s.mode == "replay" {
		err = s.replay()
	} else {
		err = s.stream()
	}
	if err != nil && s.ctx.Err() == nil {
		s.fail(err)
	}
}
func (s *Source) replay() error {
	for {
		// Default /api/replay count is the source's bounded 16-frame dataset.
		data, err := fetch(s.ctx, s.base, "/api/replay", maxReplay)
		if err != nil {
			return err
		}
		frames, err := decodeReplay(data)
		if err != nil {
			return err
		}
		s.mu.Lock()
		s.replayCount = len(frames)
		s.replayBytes = len(data)
		s.latest = nil
		s.taken = false
		s.pending = false
		s.mu.Unlock()
		start := time.Now()
		period := time.Duration(float64(time.Second) / frames[0].Header.Config.Hz)
		seq := uint64(0)
		reload := false
		for !reload {
			due := uint64(time.Since(start) / period)
			if due > seq {
				seq = due
			}
			f := *frames[seq%uint64(len(frames))]
			f.Seq = seq
			s.offer(&f)
			seq++
			timer := time.NewTimer(time.Until(start.Add(time.Duration(seq) * period)))
			select {
			case <-s.ctx.Done():
				timer.Stop()
				return s.ctx.Err()
			case <-s.reload:
				timer.Stop()
				reload = true
			case <-timer.C:
			}
		}
	}
}

// Workload changes are explicit UI actions, never part of replay scheduling.
func (s *Source) requestView(view string) {
	s.mu.Lock()
	if s.pending {
		s.mu.Unlock()
		return
	}
	s.pending = true
	s.requestedView = view
	s.requestedGeneration = s.lastGeneration
	s.viewError = ""
	s.mu.Unlock()
	go func() {
		ctx, cancel := context.WithTimeout(s.ctx, 5*time.Second)
		defer cancel()
		err := post(ctx, s.base, "/api/config", map[string]string{"view": view})
		s.mu.Lock()
		if err != nil {
			s.viewError = err.Error()
		}
		if err != nil {
			s.pending = false
		}
		s.mu.Unlock()
		if err == nil && s.mode == "replay" {
			select {
			case s.reload <- struct{}{}:
			case <-s.ctx.Done():
			}
		}
	}()
}
