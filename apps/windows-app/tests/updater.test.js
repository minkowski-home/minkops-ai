import test from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { startUpdates } from "../src/updater.js";

function fakes({ fail = false } = {}) {
  const updater = Object.assign(new EventEmitter(), {
    checks: 0, installs: [],
    checkForUpdates() { this.checks++; return fail ? Promise.reject(new Error("offline")) : Promise.resolve(null); },
    quitAndInstall(...args) { this.installs.push(args); },
  });
  const intervals = [];
  const timers = {
    setInterval: (fn, ms) => intervals.push({ fn, ms, active: true }) - 1,
    clearInterval: (id) => { if (intervals[id]) intervals[id].active = false; },
  };
  const tick = (ms) => intervals.filter((t) => t.active && t.ms === ms).forEach((t) => t.fn());
  return { updater, timers, tick };
}

test("development builds never check for updates", () => {
  const { updater, timers } = fakes();
  startUpdates({ updater, timers, isPackaged: false, isIdle: () => true });
  assert.equal(updater.checks, 0);
});

test("a downloaded update installs only once the companion is idle", async () => {
  const { updater, timers, tick } = fakes();
  let idle = false;
  const states = [];
  startUpdates({ updater, timers, isPackaged: true, isIdle: () => idle, onState: (s) => states.push(s) });
  assert.equal(updater.checks, 1);
  assert.equal(updater.autoDownload, true);
  assert.equal(updater.autoInstallOnAppQuit, true);
  tick(60_000);
  assert.equal(updater.installs.length, 0, "nothing to install yet");
  updater.emit("update-downloaded", { version: "0.7.1" });
  assert.deepEqual(states.at(-1), { state: "ready", version: "0.7.1" });
  tick(60_000);
  assert.equal(updater.installs.length, 0, "a claimed job or pending receipt defers installation");
  idle = true;
  tick(60_000);
  tick(60_000);
  assert.deepEqual(updater.installs, [[true, true]], "silent install, relaunch, exactly once");
});

test("update failures are contained and retried on the next check", async () => {
  const { updater, timers, tick } = fakes({ fail: true });
  const states = [];
  startUpdates({ updater, timers, isPackaged: true, isIdle: () => true, onState: (s) => states.push(s) });
  await new Promise((resolve) => setImmediate(resolve));
  updater.emit("error", new Error("bad signature"));
  tick(6 * 3600 * 1000);
  assert.equal(updater.checks, 2);
  assert.ok(states.every((s) => s.state === "error"));
});

test("an explicit restart waits for native work and pending receipts, even with the window focused", () => {
  const { updater, timers, tick } = fakes();
  let safe = false;
  const states = [];
  const control = startUpdates({ updater, timers, isPackaged: true,
    isIdle: () => false, canRestart: () => safe, onState: value => states.push(value) });
  assert.equal(control.requestInstall(), false, "no downloaded update exists");
  updater.emit("update-downloaded", { version: "0.8.1" });
  assert.equal(control.requestInstall(), true);
  tick(60_000);
  assert.equal(updater.installs.length, 0);
  assert.equal(states.at(-1).state, "waiting");
  safe = true;
  tick(60_000);
  tick(60_000);
  assert.deepEqual(updater.installs, [[true, true]]);
});

test("availability and download failure are observable, and a retry can recover", async () => {
  const { updater, timers } = fakes();
  const states = [];
  const control = startUpdates({ updater, timers, isPackaged: true,
    isIdle: () => false, onState: value => states.push(value) });
  updater.emit("update-available", { version: "0.8.1" });
  assert.deepEqual(states.at(-1), { state: "downloading", version: "0.8.1" });
  updater.emit("error", new Error("offline"));
  assert.equal(states.at(-1).state, "error");
  await control.check();
  assert.equal(updater.checks, 2);
});
