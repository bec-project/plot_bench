package main

// The browser worker observes completion only after the source and metrics sink
// have drained. Native builds keep the same shutdown path and ignore these events.
type lifecycleState struct {
	Submitted      uint64 `json:"submitted"`
	Running        bool   `json:"running"`
	Complete       bool   `json:"complete"`
	StopReason     string `json:"stop_reason,omitempty"`
	Error          string `json:"error,omitempty"`
	MetricsError   string `json:"metrics_error,omitempty"`
	DroppedMetrics int    `json:"dropped_metrics"`
}
