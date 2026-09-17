"use strict";

const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const { fork } = require("node:child_process");
const { mkdtemp, writeFile, rm } = require("node:fs/promises");
const { tmpdir } = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { BrowserDriver } = require("../src/plotbench/browser_driver.cjs");

function fakePlaywright({ privateApi = true, disableError = null } = {}) {
  const order = [];
  const events = [];
  const probe = {
    evaluate: async () => 2,
    close: async () => order.push("probe-close"),
  };
  const page = new EventEmitter();
  page.exposeBinding = async (name, binding) => {
    assert.equal(name, "__plotbenchLifecycle");
    page.binding = binding;
    order.push("binding");
  };
  const primaryClient = {
    send: async (method) => {
      assert.equal(method, "Network.disable");
      order.push("disable-original-network");
      if (disableError) throw disableError;
    },
  };
  if (privateApi) {
    page._connection = {
      toImpl: (value) => {
        assert.equal(value, page);
        return { delegate: { _mainFrameSession: { _client: primaryClient } } };
      },
    };
  }
  page.goto = async (url, options) => {
    assert.equal(url, "http://localhost/frontend");
    assert.deepEqual(options, { waitUntil: "load" });
    order.push("navigate");
  };
  page.screenshot = async (options) => {
    assert.equal(options.path, "/tmp/final-canvas.png");
    order.push("screenshot");
  };
  const browser = new EventEmitter();
  browser.version = () => "123.0-test";
  browser.newPage = async (options) => {
    if (options.viewport === null) {
      order.push("probe");
      return probe;
    }
    assert.deepEqual(options, {
      viewport: { width: 1100, height: 820 },
      deviceScaleFactor: 2,
    });
    order.push("page");
    return page;
  };
  browser.close = async () => {
    order.push("close");
    page.emit("close");
    browser.emit("disconnected");
  };
  const playwright = {
    chromium: {
      launch: async (options) => {
        assert.deepEqual(options, { headless: false });
        order.push("launch");
        return browser;
      },
    },
  };
  const driver = new BrowserDriver(playwright, (event) => {
    events.push(event);
    if (event.event === "ready") order.push("ready");
  });
  return { driver, order, events, page };
}

const start = {
  id: 1,
  command: "start",
  options: { headless: false },
  width: 1100,
  height: 820,
  url: "http://localhost/frontend",
};

test("disables original session before navigation and preserves lifecycle bindings", async () => {
  const { driver, order, events, page } = fakePlaywright();
  assert.equal(await driver.handle(start), false);
  assert.deepEqual(order, [
    "launch", "probe", "probe-close", "page", "binding",
    "disable-original-network", "ready", "navigate",
  ]);
  assert.deepEqual(events[0], {
    event: "ready",
    metadata: {
      browser_version: "123.0-test",
      browser_device_scale_factor: 2,
      browser_network_instrumentation: "disabled",
    },
  });
  const message = { event: "stopped", state: { submitted: 4, complete: true } };
  page.binding({}, message);
  assert.deepEqual(events[1], { event: "lifecycle", message });
});

test("missing original session interface fails without navigation or fallback", async () => {
  const { driver, order, events } = fakePlaywright({ privateApi: false });
  await driver.handle(start);
  assert.equal(order.includes("navigate"), false);
  assert.equal(events.some((event) => event.event === "ready"), false);
  assert.match(events[0].error, /Unsupported Playwright internals/);
  assert.deepEqual(events[0], { event: "reply", id: 1, error: events[0].error });
  assert.equal(events[1].event, "error");
});

test("rejected Network.disable fails without a monitored fallback", async () => {
  const { driver, order, events } = fakePlaywright({ disableError: new Error("CDP rejected") });
  await driver.handle(start);
  assert.equal(order.includes("navigate"), false);
  assert.match(events[0].error, /CDP rejected/);
  assert.equal(events[1].event, "error");
});

test("captures only on command and acknowledges capture and close after completion", async () => {
  const { driver, order, events, page } = fakePlaywright();
  await driver.handle(start);
  assert.equal(order.includes("screenshot"), false);
  let finishCapture;
  page.screenshot = () => new Promise((resolve) => { finishCapture = resolve; });
  const capture = driver.handle({ id: 2, command: "screenshot", path: "/tmp/final-canvas.png" });
  assert.equal(events.some((event) => event.id === 2), false);
  finishCapture();
  await capture;
  assert.deepEqual(events.at(-1), { event: "reply", id: 2 });
  assert.equal(await driver.handle({ id: 3, command: "close" }), true);
  assert.equal(order.at(-1), "close");
  assert.equal(events.filter((event) => event.event === "closed").length, 1);
  assert.deepEqual(events.at(-1), { event: "reply", id: 3 });
});

test("page failures and closure remain visible to the Python completion authority", async () => {
  const { driver, events, page } = fakePlaywright();
  await driver.handle(start);
  page.emit("pageerror", new Error("render failed"));
  page.emit("crash");
  page.emit("close");
  assert.match(events.at(-3).error, /render failed/);
  assert.deepEqual(events.at(-2), { event: "error", error: "Browser page crashed" });
  assert.deepEqual(events.at(-1), { event: "closed" });
});

// Run the real stdin controller with a fake Playwright package and an interval
// standing in for Chromium resources. No browser, ports, or network are used.
async function controllerChild(t, mode) {
  const directory = await mkdtemp(path.join(tmpdir(), "plotbench-controller-"));
  await writeFile(path.join(directory, "index.js"), `
const { EventEmitter } = require("node:events");
let resource, finishNavigation;
const page = new EventEmitter();
const browser = new EventEmitter();
page._connection = { toImpl: () => ({ delegate: {
  _mainFrameSession: { _client: { send: async () => {} } }
} }) };
page.exposeBinding = async () => {};
page.goto = async () => {
  process.send({ event: "navigate" });
  if (process.env.CONTROLLER_TEST_MODE === "navigation")
    await new Promise(resolve => { finishNavigation = resolve; });
};
browser.version = () => "test";
browser.newPage = async options => options.viewport === null
  ? { evaluate: async () => 1, close: async () => {} } : page;
browser.close = async () => {
  process.send({ event: "browser-close" });
  clearInterval(resource);
  finishNavigation?.();
  browser.emit("disconnected");
};
module.exports = { chromium: { launch: async () => {
  resource = setInterval(() => {}, 1000);
  process.send({ event: "launch" });
  if (process.env.CONTROLLER_TEST_MODE === "launch")
    await new Promise(resolve => setTimeout(resolve, 100));
  return browser;
} } };
`);
  const child = fork(path.resolve(__dirname, "../src/plotbench/browser_driver.cjs"), [directory], {
    silent: true,
    env: { ...process.env, CONTROLLER_TEST_MODE: mode },
  });
  const messages = [];
  const waiters = new Map();
  child.on("message", (message) => {
    messages.push(message);
    waiters.get(message.event)?.();
  });
  let output = "";
  let errors = "";
  child.stdout.on("data", (data) => { output += data; });
  child.stderr.on("data", (data) => { errors += data; });
  const exited = new Promise((resolve, reject) => {
    child.on("error", reject);
    child.on("exit", (code, signal) => resolve({ code, signal }));
  });
  t.after(async () => {
    if (child.exitCode === null && child.signalCode === null) child.kill();
    await exited;
    await rm(directory, { recursive: true, force: true });
  });
  child.stdin.write(`${JSON.stringify(start)}\n`);
  return {
    child, messages, exited,
    output: () => output,
    errors: () => errors,
    waitFor: (event) => messages.some((message) => message.event === event)
      ? Promise.resolve() : new Promise((resolve) => waiters.set(event, resolve)),
  };
}

for (const mode of ["ready", "launch", "navigation"]) {
  test(`stdin EOF during ${mode} closes browser once and exits controller`, { timeout: 3000 }, async (t) => {
    const controller = await controllerChild(t, mode);
    await controller.waitFor(mode === "launch" ? "launch" : "navigate");
    controller.child.stdin.end();
    assert.deepEqual(await controller.exited, { code: 0, signal: null });
    assert.equal(controller.errors(), "");
    assert.equal(controller.messages.filter((message) => message.event === "browser-close").length, 1);
    if (mode === "launch") {
      assert.equal(controller.messages.some((message) => message.event === "navigate"), false);
    }
  });
}

test("normal close command exits without duplicate EOF cleanup", { timeout: 3000 }, async (t) => {
  const controller = await controllerChild(t, "ready");
  await controller.waitFor("navigate");
  controller.child.stdin.write(`${JSON.stringify({ id: 2, command: "close" })}\n`);
  assert.deepEqual(await controller.exited, { code: 0, signal: null });
  assert.equal(controller.errors(), "");
  assert.equal(controller.messages.filter((message) => message.event === "browser-close").length, 1);
  assert.ok(controller.output().split("\n").filter(Boolean).map(JSON.parse).some(
    (message) => message.event === "reply" && message.id === 2,
  ));
});
