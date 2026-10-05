import test from "node:test";
import assert from "node:assert/strict";
import { CompanionWorker } from "../../../platform/desktop-runtime/src/worker.js";
import { collectSources } from "../../../platform/desktop-runtime/src/discovery.js";

test("discovery continues after a missing folder and reports a separate Tally result", async () => {
  const events = [];
  const result = await collectSources(
    {
      config: { depth: "structure", tally: {} },
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
      discoverTally: async () => ({ collections: [] }),
      onProgress: async (...args) => events.push(args),
    },
  );
  assert.deepEqual(
    result.sources.map((s) => s.status),
    ["unavailable", "ready"],
  );
  assert.equal(events.at(-1)[0], "tally");
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

test("superseded receipts are discarded without deleting a recovery backup", async () => {
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
    acknowledge: async () => assert.fail("Unverified backup must remain"),
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
