import test from "node:test";
import assert from "node:assert/strict";
import { CompanionWorker } from "../../../platform/desktop-runtime/src/worker.js";
import { collectSources, reportDiscoveryProgress } from "../../../platform/desktop-runtime/src/discovery.js";

test("busy collection, receipt delivery and archiving keep presence without claiming another job", async () => {
  let release, entered, pending = null, claims = 0, beats = 0, archives = 0;
  const started = () => new Promise(resolve => { entered = resolve; });
  const block = () => { entered(); return new Promise(resolve => { release = resolve; }); };
  const worker = new CompanionWorker({
    request: async path => { if (path.endsWith("/claim")) { claims++; return {id: "job", claim_token: "token"}; } await block(); },
    execute: block,
    pending: () => pending,
    savePending: async value => { pending = value; },
    heartbeat: async () => { beats++; },
    afterTick: async () => { archives++; await block(); },
  });
  let ready = started();
  const first = worker.tick();
  for (let phase = 0; phase < 3; phase++) {
    await ready;
    await worker.tick();
    assert.equal(claims, 1);
    assert.equal(beats, phase + 1);
    ready = started();
    release({sources: []});
  }
  await first;
  assert.equal(archives, 1);
  assert.equal(worker.busy, false);
  assert.equal(pending, null);
});

test("overlapping presence requests are bounded and a failed receipt stays durable", async () => {
  let release, beats = 0, pending = {id: "job", receipt: {claim_token: "token"}};
  const worker = new CompanionWorker({
    request: async () => { throw new Error("offline"); },
    execute: async () => { throw new Error("must not execute again"); },
    pending: () => pending, savePending: async value => { pending = value; },
    heartbeat: () => { beats++; return new Promise(resolve => { release = resolve; }); },
  });
  // A retry reports presence before attempting to deliver its durable receipt.
  const first = worker.tick();
  await worker.tick();
  assert.equal(beats, 1);
  release();
  await assert.rejects(first, /offline/);
  assert.equal(pending.id, "job");
  assert.equal(worker.busy, false);
});

test("discovery pauses at a read boundary, renews observations, and resumes once", async () => {
  const states = ["paused", "paused", "active"];
  let waits = 0, reads = 0;
  await reportDiscoveryProgress(async () => ({ control_state: states[reads++] }), {
    wait: async ms => { assert.equal(ms, 2000); waits++; }
  });
  assert.equal(waits, 2); assert.equal(reads, 3);
  await reportDiscoveryProgress(async () => ({})); // An older API remains compatible.
  await assert.rejects(reportDiscoveryProgress(async () => ({ control_state: "stopped" })), { code: "TASK_STOPPED" });
});

test("a discovery Stop is never mistaken for an unavailable source or followed by more reads", async () => {
  let reads = 0;
  await assert.rejects(collectSources({ config: {}, sources: [{key: "excel", tool: "excel"}, {key: "second", tool: "excel"}] }, {
    folderFor: () => "folder", inventory: async () => [{path: "one.xlsx", content: Buffer.from("x").toString("base64")}],
    excelSchemaBytes: async b => b, inspectExcel: async () => { reads++; return {}; },
    onProgress: async (_key, _status, _category, progress) => { if (progress?.completed === 1) throw Object.assign(new Error("Stopped"), {code: "TASK_STOPPED"}); }
  }), { code: "TASK_STOPPED" });
  assert.equal(reads, 1);
});

test("a network failure cannot release an acknowledged pause", async () => {
  let calls = 0, waits = 0;
  await reportDiscoveryProgress(async () => {
    calls++;
    if (calls === 2) throw new Error("Offline");
    return {control_state: calls === 1 ? "paused" : "active"};
  }, {wait: async () => { waits++; }});
  assert.equal(calls, 3); assert.equal(waits, 2);
});

test("discovery continues after a missing folder and reports a separate Tally result", async () => {
  const events = [];
  const result = await collectSources(
    {
      config: { depth: "client_context", tally: {} },
      sources: [
        { key: "missing", tool: "excel" },
        { key: "tally", tool: "tally" },
      ],
    },
    {
      folderFor: () => {
        throw new Error("Missing");
      },
      inventory: async () => [],
      inspectExcel: async () => {},
      discoverClientContext: async () => ({ companies: [] }),
      onProgress: async (...args) => events.push(args),
    },
  );
  assert.deepEqual(
    result.sources.map((s) => s.status),
    ["unavailable", "ready"],
  );
  assert.equal(events.at(-1)[0], "tally");
});

test("discovery forwards native measurements and reports one workbook activity at a time", async () => {
  const events = [];
  const measurement = { completed: 2, total: 7, activity: "Collected masters", item: "A" };
  await collectSources({ config: { tally: {} }, sources: [{ key: "tally", tool: "tally" }, { key: "excel", tool: "excel" }] }, {
    folderFor: () => "folder", inventory: async () => ["one.xlsx", "two.xlsx"].map(path => ({ path, content: Buffer.from("bytes").toString("base64") })),
    excelSchemaBytes: async bytes => bytes, inspectExcel: async () => ({ sheets: [] }),
    discoverClientContext: async (_config, { onProgress }) => { await onProgress("A", "reading", measurement); return { companies: [] }; },
    onProgress: async (...args) => events.push(args)
  });
  assert.ok(events.some(event => event[0] === "tally" && event[3] === measurement));
  const excel = events.filter(event => event[0] === "excel" && event[3]);
  assert.equal(excel.at(-1)[3].completed, 2);
  assert.equal(excel.at(-1)[3].total, 2);
  assert.equal(excel.at(-1)[3].item, "two.xlsx");
});

test("a rejected receipt becomes an observable failure instead of an endless read retry", async () => {
  let pending = null;
  let rejected = false;
  let accepted;
  const worker = new CompanionWorker({
    pending: () => pending,
    savePending: async (p) => {
      pending = p;
    },
    execute: async () => ({ sources: [] }),
    request: async (path, body) => {
      if (path.endsWith("/claim"))
        return {
          id: "job",
          claim_token: "token",
          operation: "sources.discover",
        };
      if (!rejected) {
        rejected = true;
        const e = new Error("Invalid receipt");
        e.status = 422;
        throw e;
      }
      accepted = body;
    },
  });
  await worker.tick();
  assert.equal(accepted.result, null);
  assert.match(accepted.error, /could not be accepted/);
  assert.equal(pending, null);
});
import {
  trustedOrigin,
  validateSender,
  validateFolderReconnect,
} from "../src/policy.js";

test("only approved server origins are accepted", () => {
  assert.equal(
    trustedOrigin("https://app.minkops.com/path"),
    "https://app.minkops.com",
  );
  assert.throws(() => trustedOrigin("http://example.com"));
  assert.throws(() => trustedOrigin("file:///C:/test"));
  assert.throws(() => trustedOrigin("https://user:secret@app.minkops.com"));
  assert.throws(() => trustedOrigin("http://127.0.0.1:3000"));
  assert.equal(
    trustedOrigin("http://127.0.0.1:3000", true),
    "http://127.0.0.1:3000",
  );
});

test("reconnecting grants permits recovery but never silently changes a known folder or owner", () => {
  assert.doesNotThrow(() =>
    validateFolderReconnect(undefined, "explicitly selected folder", "owner"),
  );
  const previous = { root: "original folder", owner_id: "owner" };
  assert.doesNotThrow(() =>
    validateFolderReconnect(previous, previous.root, "owner"),
  );
  assert.throws(() =>
    validateFolderReconnect(previous, "another folder", "owner"),
  );
  assert.throws(() =>
    validateFolderReconnect(previous, previous.root, "someone else"),
  );
});

test("native calls reject iframe, another window and off-origin senders", () => {
  const frame = { url: "https://app.minkops.com/workspace" };
  const contents = { mainFrame: frame };
  const window = { webContents: contents };
  const event = { sender: contents, senderFrame: frame };
  assert.doesNotThrow(() =>
    validateSender(event, window, "https://app.minkops.com"),
  );
  assert.throws(() =>
    validateSender(
      { ...event, senderFrame: { url: frame.url } },
      window,
      "https://app.minkops.com",
    ),
  );
  assert.throws(() =>
    validateSender({ ...event, sender: {} }, window, "https://app.minkops.com"),
  );
  frame.url = "https://example.com";
  assert.throws(() => validateSender(event, window, "https://app.minkops.com"));
});

test("a financial save receipt survives worker recreation and cleanup follows acceptance", async () => {
  const persisted = {
    id: "saved",
    receipt: {
      claim_token: "claim",
      result: { content: "saved bytes" },
      error: null,
    },
  };
  let pending = persisted;
  let cleaned = false;
  const worker = new CompanionWorker({
    request: async (path, body) => {
      assert.equal(path, "/api/desktop/worker/jobs/saved/finish");
      assert.deepEqual(body, persisted.receipt);
    },
    execute: async () =>
      assert.fail("A saved financial operation must not execute again"),
    pending: () => pending,
    savePending: async (value) => {
      assert.equal(cleaned, true);
      pending = value;
    },
    acknowledge: async () => {
      cleaned = true;
    },
  });
  await worker.tick();
  assert.equal(pending, null);
});

test("superseded receipts are discarded without executing again", async () => {
  let pending = { id: "old", receipt: {} };
  const worker = new CompanionWorker({
    request: async () => {
      const error = new Error();
      error.status = 409;
      throw error;
    },
    execute: async () => assert.fail("No second execution"),
    pending: () => pending,
    savePending: async (value) => {
      pending = value;
    },
  });
  await assert.rejects(worker.tick());
  assert.equal(pending, null);
});

test("worker retries a pending receipt without executing the operation twice", async () => {
  let executions = 0;
  let finishes = 0;
  let pending;
  const job = {
    id: "job",
    operation: "tally.probe",
    input: {},
    claim_token: "claim",
  };
  const worker = new CompanionWorker({
    request: async (path) => {
      if (path.endsWith("/claim")) return job;
      finishes++;
      if (finishes === 1) throw new Error("connection interrupted");
      return {};
    },
    execute: async () => {
      executions++;
      return { available: true, companies: [] };
    },
    pending: () => pending,
    savePending: async (value) => {
      pending = value;
    },
  });
  await assert.rejects(worker.tick());
  await worker.tick();
  assert.equal(executions, 1);
  assert.equal(finishes, 2);
  assert.equal(pending, null);
});

test("worker serializes overlapping ticks and records actionable failure", async () => {
  let claims = 0;
  let resolve;
  let pending;
  const worker = new CompanionWorker({
    request: async (path) => {
      if (path.endsWith("/claim")) {
        claims++;
        await new Promise((r) => {
          resolve = r;
        });
        return {
          id: "job",
          operation: "tally.probe",
          input: {},
          claim_token: "claim",
        };
      }
      return {};
    },
    execute: async () => {
      throw new Error("private filesystem details");
    },
    pending: () => pending,
    savePending: async (value) => {
      pending = value;
    },
  });
  const first = worker.tick();
  await worker.tick();
  resolve();
  await first;
  assert.equal(claims, 1);
  assert.equal(pending, null);
});

async function failedReceipt(operation, error) {
  let pending;
  const finished = [];
  const worker = new CompanionWorker({
    request: async (path, body) => {
      if (path.endsWith("/claim")) return { id: "job", operation, input: {}, claim_token: "claim" };
      finished.push(body);
      return {};
    },
    execute: async () => { throw error; },
    pending: () => pending,
    savePending: async (value) => { pending = value; },
  });
  await worker.tick();
  return finished[0];
}

test("write failures direct reconciliation to Tally without folder instructions", async () => {
  const receipt = await failedReceipt("tally.write", new Error("private error"));
  assert.match(receipt.error, /Tally/);
  assert.match(receipt.error, /Retry save/);
  assert.doesNotMatch(receipt.error, /folder|private/);
});

test("a typed Tally state reaches the user verbatim instead of a generic guess", async () => {
  const typed = Object.assign(new Error("Tally isn't open on PRAHLAD-GADHWAL. Open it and your companies, then try again."), {
    userSafe: true, tallyState: "not_running",
  });
  for (const operation of ["tally.probe", "tally.save", "sources.discover"])
    assert.equal((await failedReceipt(operation, typed)).error, typed.message);
  const long = Object.assign(new Error("x".repeat(400)), { userSafe: true });
  assert.equal((await failedReceipt("tally.probe", long)).error.length, 300);
});

test("untyped failures keep their safe fallback and never leak internal details", async () => {
  const receipt = await failedReceipt("tally.probe", new Error("ECONNRESET at C:\\Users\\private"));
  assert.doesNotMatch(receipt.error, /private|ECONNRESET|not responding/);
  assert.match(receipt.error, /Send diagnostics/);
});

test("a typed Tally failure names its action on the Tally source", async () => {
  const typed = Object.assign(new Error("Two open companies are named Sachin Infra. Close one in Tally on PC1, then try again."), { userSafe: true });
  const result = await collectSources(
    { config: { tally: {} }, sources: [{ key: "tally", tool: "tally" }] },
    { discoverClientContext: async () => { throw typed; }, onProgress: async () => {} },
  );
  assert.equal(result.sources[0].status, "unavailable");
  assert.equal(result.sources[0].error, typed.message);
});

test("a job's local diagnostic travels with its receipt, success or failure", async () => {
  for (const execute of [async () => ({ available: true, companies: [] }), async () => { throw new Error("x"); }]) {
    let pending;
    const finished = [];
    const worker = new CompanionWorker({
      request: async (path, body) => {
        if (path.endsWith("/claim")) return { id: "job-1", operation: "tally.probe", input: {}, claim_token: "claim" };
        finished.push(body);
        return {};
      },
      execute,
      diagnosticFor: (job) => (job.id === "job-1" ? { state: "busy", cause: "TimeoutError" } : null),
      pending: () => pending,
      savePending: async (value) => { pending = value; },
    });
    await worker.tick();
    assert.deepEqual(finished[0].diagnostic, { state: "busy", cause: "TimeoutError" });
  }
});
