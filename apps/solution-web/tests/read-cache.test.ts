import assert from "node:assert/strict";
import test from "node:test";
import { ReadCache, readKey } from "../src/starter/readCache.ts";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

test("shared readers deduplicate and cancel only when the last reader leaves", async () => {
  const cache = new ReadCache();
  const key = readKey("alice:tenant", "/attention");
  const request = deferred<string[]>(); let calls = 0, signal: AbortSignal | undefined;
  const load = (current: AbortSignal) => { calls++; signal = current; return request.promise; };
  const first = cache.subscribe(key, () => {}), second = cache.subscribe(key, () => {});
  const a = cache.refresh(key, load), b = cache.refresh(key, load);
  assert.equal(calls, 1);
  first(); assert.equal(signal?.aborted, false);
  second(); assert.equal(signal?.aborted, true);
  request.resolve(["obsolete"]); await Promise.all([a, b]);
  assert.equal(cache.snapshot(key).data, undefined);
});

test("a committed mutation cannot be undone by an earlier poll", async () => {
  const cache = new ReadCache(), key = readKey("alice:tenant", "/attention");
  const request = deferred<string[]>();
  const pending = cache.refresh(key, () => request.promise);
  cache.put(key, ["confirmed"]);
  request.resolve(["pending"]); await pending;
  assert.deepEqual(cache.snapshot(key).data, ["confirmed"]);
});

test("failed refresh preserves cached data and reports the refresh error", async () => {
  const cache = new ReadCache(), key = readKey("alice:tenant", "/attention");
  cache.put(key, ["existing"]);
  await cache.refresh(key, () => Promise.reject(new Error("Offline")));
  assert.deepEqual(cache.snapshot(key).data, ["existing"]);
  assert.equal(cache.snapshot(key).error, "Offline");
});

test("an authoritative access denial discards the cached private response", async () => {
  const cache = new ReadCache(), key = readKey("alice:tenant", "/run");
  cache.put(key, { invoice: "private" });
  await cache.refresh(key, () => Promise.reject(Object.assign(new Error("Access denied"), {status:403})));
  assert.equal(cache.snapshot(key).data, undefined);
  assert.equal(cache.snapshot(key).error, "Access denied");
});

test("invalidation refetches observed resources and fences prior results", async () => {
  const cache = new ReadCache(), key = readKey("alice:tenant", "/attention");
  const old = deferred<string[]>(); let count = 0;
  const unsubscribe = cache.subscribe(key, () => {});
  const initial = cache.refresh(key, () => ++count === 1 ? old.promise : Promise.resolve(["new"]));
  cache.invalidate("alice:tenant");
  old.resolve(["old"]); await initial;
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(count, 2); assert.deepEqual(cache.snapshot(key).data, ["new"]);
  unsubscribe();
});

test("keys isolate users and tenants; clearing removes private data", () => {
  const cache = new ReadCache();
  const a = readKey("alice:one", "/run"), b = readKey("alice:two", "/run"), c = readKey("bob:one", "/run");
  cache.put(a, "private");
  assert.equal(cache.snapshot(b).data, undefined); assert.equal(cache.snapshot(c).data, undefined);
  cache.clear(); assert.equal(cache.snapshot(a).data, undefined);
});

test("bounded cache evicts old unobserved resources while retaining active readers", () => {
  const cache = new ReadCache(2), a = readKey("alice:one", "/a");
  cache.put(a, "active"); const unsubscribe = cache.subscribe(a, () => {});
  const b = readKey("alice:one", "/b"), c = readKey("alice:one", "/c");
  cache.put(b, "old"); cache.put(c, "new");
  assert.equal(cache.snapshot(a).data, "active"); assert.equal(cache.snapshot(b).data, undefined);
  unsubscribe();
});
