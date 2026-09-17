//go:build !js

package main

import (
	"os"
	"os/signal"
	"syscall"

	"fyne.io/fyne/v2"
)

const frontendName = "fyne"
const frontendTitle = "Fyne"
const graphicsAPI = "OpenGL via Fyne GLFW"

func notifyLifecycle(string, lifecycleState) {}
func platformMetadata() map[string]any       { return nil }

func installStopHandler(stop <-chan struct{}, shutdown func(), _ func(error)) func() {
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, os.Interrupt, syscall.SIGTERM)
	go func() {
		select {
		case <-stop:
		case <-signals:
			shutdown()
		}
	}()
	return func() { signal.Stop(signals) }
}

func closeWindow(w fyne.Window) { w.Close() }

func runWindow(w fyne.Window, _ <-chan struct{}, finish func()) {
	w.ShowAndRun()
	finish()
}
