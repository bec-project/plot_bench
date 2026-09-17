//go:build js && wasm

package main

import (
	"encoding/json"
	"fmt"
	"syscall/js"

	"fyne.io/fyne/v2"
)

const displayProtocol = "browser"
const frontendName = "fyne-wasm"
const frontendTitle = "Fyne WebAssembly"
const graphicsAPI = "WebGL via Fyne"

func notifyLifecycle(event string, state lifecycleState) {
	data, _ := json.Marshal(map[string]any{"event": event, "state": state})
	notify := js.Global().Get("__plotbenchNotify")
	if notify.Type() == js.TypeFunction {
		notify.Invoke(js.Global().Get("JSON").Call("parse", string(data)))
	}
}

// The loader samples the actual Fyne WebGL canvas. It never creates a separate
// graphics context just for metadata, and observes visibility between batches.
func platformMetadata() map[string]any {
	probe := js.Global().Get("__plotbenchBrowserMetadata")
	if probe.Type() != js.TypeFunction {
		return nil
	}
	var result map[string]any
	_ = json.Unmarshal([]byte(js.Global().Get("JSON").Call("stringify", probe.Invoke()).String()), &result)
	return result
}

func installStopHandler(_ <-chan struct{}, shutdown func(), fail func(error)) func() {
	stop := js.FuncOf(func(js.Value, []js.Value) any {
		shutdown()
		return nil
	})
	failed := js.FuncOf(func(_ js.Value, args []js.Value) any {
		message := "browser rendering failed"
		if len(args) > 0 {
			message = args[0].String()
		}
		fail(fmt.Errorf("%s", message))
		return nil
	})
	js.Global().Set("__plotbenchStop", stop)
	js.Global().Set("__plotbenchFail", failed)
	return func() {
		js.Global().Delete("__plotbenchStop")
		js.Global().Delete("__plotbenchFail")
		stop.Release()
		failed.Release()
	}
}

// Keep the final canvas available for QA after the measured interval.
// The isolated browser worker closes the page after flushed completion.
func closeWindow(fyne.Window) {}

func runWindow(w fyne.Window, stop <-chan struct{}, finish func()) {
	go func() {
		<-stop
		finish()
	}()
	w.ShowAndRun()
}
