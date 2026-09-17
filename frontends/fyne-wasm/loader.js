"use strict";

(() => {
  const loading = document.getElementById("loading");
  const params = new URLSearchParams(location.search);
  const state = {
    submitted: 0,
    running: false,
    complete: false,
    dropped_metrics: 0,
  };
  let visibilityChanges = 0;
  let contextLosses = 0;
  let observedCanvas;
  let firstBrowserContext;
  document.addEventListener("visibilitychange", () => { visibilityChanges += 1; });
  window.__plotbenchState = state;
  window.__plotbenchNotify = (message) => {
    Object.assign(state, message.state);
    if (message.event === "started") loading.hidden = true;
    if (state.error) {
      loading.hidden = false;
      loading.textContent = `Fyne WebAssembly failed: ${state.error}`;
    }
    if (typeof window.__plotbenchLifecycle === "function") {
      Promise.resolve(window.__plotbenchLifecycle(message)).catch((error) => {
        console.error("Browser lifecycle notification failed", error);
      });
    }
  };

  function browserContext() {
    return {
      screen: {
        width: screen.width, height: screen.height,
        available_width: screen.availWidth, available_height: screen.availHeight,
        available_left: screen.availLeft ?? null, available_top: screen.availTop ?? null,
        color_depth: screen.colorDepth, pixel_depth: screen.pixelDepth,
        is_extended: screen.isExtended ?? null,
        orientation_type: screen.orientation?.type ?? null,
        orientation_angle: screen.orientation?.angle ?? null,
        refresh_hz: null,
      },
      window: {
        screen_x: screenX, screen_y: screenY, outer_width: outerWidth, outer_height: outerHeight,
        inner_width: innerWidth, inner_height: innerHeight,
        device_pixel_ratio: devicePixelRatio,
        visibility: document.visibilityState, focused: document.hasFocus(),
      },
      cross_origin_isolated: crossOriginIsolated,
      secure_context: isSecureContext,
      captured: "before transport/preload; screen geometry may be browser-emulated",
    };
  }

  window.__plotbenchBrowserMetadata = () => {
    const canvas = document.querySelector("canvas");
    let graphics = null;
    if (canvas) {
      if (observedCanvas !== canvas) {
        observedCanvas = canvas;
        canvas.addEventListener("webglcontextlost", () => {
          contextLosses += 1;
          const message = "Fyne WebGL context lost";
          if (typeof window.__plotbenchFail === "function") window.__plotbenchFail(message);
          else fail(message);
        });
      }
      // Fyne already owns this context; getContext returns that same context.
      const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
      if (gl) {
        const debug = gl.getExtension("WEBGL_debug_renderer_info");
        graphics = {
          version: gl.getParameter(gl.VERSION),
          vendor: gl.getParameter(gl.VENDOR),
          renderer: gl.getParameter(gl.RENDERER),
          unmasked_vendor: debug ? gl.getParameter(debug.UNMASKED_VENDOR_WEBGL) : null,
          unmasked_renderer: debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : null,
          drawing_buffer: [gl.drawingBufferWidth, gl.drawingBufferHeight],
          context_attributes: gl.getContextAttributes(),
        };
      }
    }
    return {
      user_agent: navigator.userAgent,
      browser_context: firstBrowserContext,
      device_pixel_ratio: devicePixelRatio,
      visibility: document.visibilityState,
      visibility_changes: visibilityChanges,
      focused: document.hasFocus(),
      graphics_webgl: graphics,
      graphics_context_losses: contextLosses,
    };
  };

  function fail(error) {
    window.__plotbenchNotify({
      event: "stopped",
      state: { ...state, running: false, complete: false, stop_reason: "error", error: String(error) },
    });
    console.error(error);
  }

  async function start() {
    const go = new Go();
    go.argv = ["plotbench-fyne"];
    for (const [query, flag, fallback] of [
      ["url", "url", "http://127.0.0.1:8765"],
      ["mode", "mode", "stream"],
      ["run_id", "run-id", "demo"],
      ["duration", "duration", "0"],
      ["width", "width", "1100"],
      ["height", "height", "820"],
    ]) {
      go.argv.push(`--${flag}`, params.get(query) ?? fallback);
    }
    firstBrowserContext = browserContext();
    go.exit = (code) => {
      if (code !== 0 || !state.complete) fail(`Go runtime exited with code ${code}`);
    };
    const response = await fetch("plotbench-fyne.wasm");
    if (!response.ok) throw new Error(`WASM download failed: HTTP ${response.status}`);
    // Compile the exact locked Go build. ArrayBuffer works with ordinary static
    // servers even when their WASM MIME type is absent.
    const result = await WebAssembly.instantiate(await response.arrayBuffer(), go.importObject);
    await go.run(result.instance);
  }
  start().catch(fail);
})();
