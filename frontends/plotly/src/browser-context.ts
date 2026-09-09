/** An observation of clock increments, not a guarantee of the browser's timer resolution. */
export function observeTimer(now: () => number = () => performance.now()) {
  const reads = 2048;
  let previous = now();
  let minimum = Infinity;
  for (let index = 1; index < reads; index += 1) {
    const current = now();
    const delta = current - previous;
    if (delta > 0) minimum = Math.min(minimum, delta);
    previous = current;
  }
  return {
    clock: 'performance.now', reads,
    minimum_positive_observed_delta_ms: Number.isFinite(minimum) ? minimum : null,
    method: 'minimum positive difference between bounded consecutive reads before streaming; not a guaranteed resolution',
  };
}

export function browserContext() {
  const display = window.screen as Screen & {
    availLeft?: number; availTop?: number; isExtended?: boolean;
  };
  return {
    screen: {
      width: display.width, height: display.height,
      available_width: display.availWidth, available_height: display.availHeight,
      available_left: display.availLeft ?? null, available_top: display.availTop ?? null,
      color_depth: display.colorDepth, pixel_depth: display.pixelDepth,
      is_extended: display.isExtended ?? null,
      orientation_type: display.orientation?.type ?? null,
      orientation_angle: display.orientation?.angle ?? null,
      refresh_hz: null,
      refresh_measurement: 'unavailable from the standard screen API; record the controlled display configuration separately',
    },
    window: {
      screen_x: window.screenX, screen_y: window.screenY,
      outer_width: window.outerWidth, outer_height: window.outerHeight,
      inner_width: window.innerWidth, inner_height: window.innerHeight,
      device_pixel_ratio: window.devicePixelRatio,
      visibility: document.visibilityState, focused: document.hasFocus(),
    },
    cross_origin_isolated: window.crossOriginIsolated,
    secure_context: window.isSecureContext,
    timer: observeTimer(),
    captured: 'before transport/preload and the first submitted frame; screen geometry may be browser-emulated',
  };
}
