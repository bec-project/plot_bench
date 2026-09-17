package main

import (
	"context"
	"fmt"
	"sync"
	"time"
)

type Sample struct {
	Seq        uint64   `json:"seq"`
	Generation uint64   `json:"generation"`
	ClientTime float64  `json:"client_time_ms"`
	Update     float64  `json:"update_ms"`
	Conversion float64  `json:"conversion_ms"`
	ReceiveAge *float64 `json:"receive_age_ms"`
	Skipped    uint64   `json:"skipped"`
}
type Metrics struct {
	mu                sync.Mutex
	samples           []Sample
	metadata          map[string]any
	lost              int
	err               error
	base, mode, runID string
	stop, done        chan struct{}
}

func newMetrics(base, mode, runID string, metadata map[string]any) *Metrics {
	m := &Metrics{base: base, mode: mode, runID: runID, metadata: metadata, stop: make(chan struct{}), done: make(chan struct{})}
	go func() {
		defer close(m.done)
		t := time.NewTicker(time.Second)
		defer t.Stop()
		for {
			select {
			case <-m.stop:
				m.flush(true)
				return
			case <-t.C:
				m.flush(false)
			}
		}
	}()
	return m
}
func (m *Metrics) record(s Sample) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if len(m.samples) >= 4096 {
		m.lost++
		m.err = fmt.Errorf("telemetry buffer overflow")
	} else {
		m.samples = append(m.samples, s)
	}
}
func (m *Metrics) set(values map[string]any) {
	m.mu.Lock()
	defer m.mu.Unlock()
	for k, v := range values {
		m.metadata[k] = v
	}
}
func (m *Metrics) flush(final bool) {
	m.mu.Lock()
	samples := m.samples
	m.samples = nil
	meta := map[string]any{}
	for k, v := range m.metadata {
		meta[k] = v
	}
	meta["telemetry_lost"] = m.lost
	if m.err != nil {
		meta["telemetry_error"] = m.err.Error()
		if final {
			meta["termination_reason"] = "error"
		}
	}
	m.mu.Unlock()
	if len(samples) == 0 && !final {
		return
	}
	if samples == nil {
		samples = []Sample{}
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	err := post(ctx, m.base, "/api/metrics", map[string]any{"frontend": frontendName, "mode": m.mode, "run_id": m.runID, "samples": samples, "metadata": meta})
	if err != nil {
		m.mu.Lock()
		m.lost += len(samples)
		m.err = err
		m.mu.Unlock()
		fmt.Println("Metrics export failed:", err)
	}
}
func (m *Metrics) close() error {
	close(m.stop)
	<-m.done
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.err
}
