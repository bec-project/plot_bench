"use strict";

// Use Playwright's installed Node API in-process so its existing Chromium CDP
// session is accessible. A newly attached CDP session cannot disable monitoring
// on the session Playwright enabled. Keeping Network enabled duplicates every
// binary WebSocket frame as base64 through the automation transport.
async function disableNetworkMonitoring(page) {
  const connection = page && page._connection;
  const implementation =
    connection && typeof connection.toImpl === "function"
      ? connection.toImpl(page)
      : null;
  const client = implementation?.delegate?._mainFrameSession?._client;
  if (!client || typeof client.send !== "function") {
    throw new Error(
      "Unsupported Playwright internals: cannot disable Network monitoring on " +
        "the original Chromium session. No monitored fallback is permitted.",
    );
  }
  await client.send("Network.disable");
}

class BrowserDriver {
  constructor(playwright, emit) {
    this.playwright = playwright;
    this.emit = emit;
    this.browser = null;
    this.page = null;
    this.started = false;
    this.closedEmitted = false;
    this.launchPromise = null;
    this.shutdownPromise = null;
    this.shuttingDown = false;
  }

  closed() {
    if (!this.closedEmitted) {
      this.closedEmitted = true;
      this.emit({ event: "closed" });
    }
  }

  shutdown() {
    this.shuttingDown = true;
    if (!this.shutdownPromise) {
      this.shutdownPromise = (async () => {
        // EOF can arrive while Chromium is still launching. Close that browser
        // as soon as it exists instead of leaving an orphan after launch.
        const browser = this.browser || (this.launchPromise && await this.launchPromise);
        if (browser) await browser.close();
      })();
    }
    return this.shutdownPromise;
  }

  async start(command) {
    if (this.started) throw new Error("Browser controller has already started");
    this.started = true;
    const { options, width, height, url } = command;
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 200 || height < 200) {
      throw new Error("Browser viewport dimensions must be integers of at least 200 pixels");
    }
    this.launchPromise = this.playwright.chromium.launch(options);
    this.browser = await this.launchPromise;
    if (this.shuttingDown) return;
    this.browser.on("disconnected", () => this.closed());

    // Observe native scaling before applying the requested logical viewport.
    const probe = await this.browser.newPage({ viewport: null });
    let pixelRatio;
    try {
      pixelRatio = await probe.evaluate(() => window.devicePixelRatio);
    } finally {
      await probe.close();
    }
    if (this.shuttingDown) return;
    if (!Number.isFinite(pixelRatio) || pixelRatio <= 0) {
      throw new Error("Browser returned an invalid native device pixel ratio");
    }
    this.page = await this.browser.newPage({
      viewport: { width, height },
      deviceScaleFactor: pixelRatio,
    });
    if (this.shuttingDown) return;
    this.page.on("pageerror", (error) => {
      this.emit({ event: "error", error: `BROWSER ERROR: ${String(error)}` });
    });
    this.page.on("crash", () => {
      this.emit({ event: "error", error: "Browser page crashed" });
    });
    this.page.on("close", () => this.closed());
    await this.page.exposeBinding("__plotbenchLifecycle", (_source, message) => {
      this.emit({ event: "lifecycle", message });
    });
    if (this.shuttingDown) return;
    await disableNetworkMonitoring(this.page);
    if (this.shuttingDown) return;
    this.emit({
      event: "ready",
      metadata: {
        browser_version: this.browser.version(),
        browser_device_scale_factor: pixelRatio,
        browser_network_instrumentation: "disabled",
      },
    });
    // Page lifecycle events and Runtime bindings remain enabled. Network events
    // and navigation response objects are deliberately unavailable in this mode.
    await this.page.goto(url, { waitUntil: "load" });
  }

  // Commands are serialized by the stdin controller. Python owns duration,
  // completion validation, and the decision to capture the final canvas.
  async handle(command) {
    const id = command?.id;
    try {
      switch (command?.command) {
        case "start":
          await this.start(command);
          break;
        case "screenshot":
          if (!this.page) throw new Error("Browser page has not started");
          if (typeof command.path !== "string" || !command.path) {
            throw new Error("Screenshot path is required");
          }
          await this.page.screenshot({ path: command.path });
          this.emit({ event: "reply", id });
          break;
        case "close":
          await this.shutdown();
          this.emit({ event: "reply", id });
          return true;
        default:
          throw new Error(`Unknown browser controller command: ${command?.command}`);
      }
    } catch (error) {
      const message = String(error);
      this.emit({ event: "reply", id, error: message });
      this.emit({ event: "error", error: message });
    }
    return false;
  }
}

function main(packagePath) {
  let inputEnded = false;
  const emit = (message) => {
    if (!inputEnded) process.stdout.write(`${JSON.stringify(message)}\n`);
  };
  let playwright;
  try {
    if (!packagePath || !require("node:path").isAbsolute(packagePath)) {
      throw new Error("An absolute installed Playwright package path is required");
    }
    playwright = require(packagePath);
  } catch (error) {
    emit({ event: "error", error: String(error) });
    process.exitCode = 1;
    return;
  }
  const driver = new BrowserDriver(playwright, emit);
  const lines = require("node:readline").createInterface({ input: process.stdin });
  let commands = Promise.resolve();
  let closing = false;
  lines.on("close", () => {
    if (closing) return;
    closing = true;
    inputEnded = true;
    // Do not queue this behind navigation or another pending command: closing
    // Chromium must also interrupt startup when the Python owner disappears.
    driver.shutdown().then(
      () => process.exit(0),
      (error) => {
        process.stderr.write(`Browser cleanup after stdin EOF failed: ${String(error)}\n`);
        process.exit(1);
      },
    );
  });
  lines.on("line", (line) => {
    commands = commands.then(async () => {
      if (closing) return;
      let command;
      try {
        command = JSON.parse(line);
      } catch (error) {
        emit({ event: "error", error: `Invalid browser controller JSON: ${String(error)}` });
        return;
      }
      if (await driver.handle(command)) {
        closing = true;
        lines.close();
        process.stdin.pause();
        // Flush the close reply before ending the controller process.
        process.stdout.write("", () => process.exit(0));
      }
    }).catch((error) => {
      emit({ event: "error", error: String(error) });
    });
  });
}

module.exports = { BrowserDriver, disableNetworkMonitoring, main };
if (require.main === module) main(process.argv[2]);
