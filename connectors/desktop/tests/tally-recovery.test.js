import test from "node:test";
import assert from "node:assert/strict";
import { recoveringTallyRequest, tallyCompanyNumber } from "../src/tally-recovery.js";

test("observed numeric company loads accept Tally typed whitespace without accepting arbitrary arguments", () => {
  assert.equal(tallyCompanyNumber({ "#text": " 100000", "@_TYPE": "Number" }), "100000");
  assert.equal(tallyCompanyNumber(" 00123 "), "00123");
  for (const value of [undefined, "company-guid", "1 /TDL:evil", "12345678901", { nested: "100000" }, { "#text": "100000", nested: "unexpected" }])
    assert.equal(tallyCompanyNumber(value), null);
});

test("a failed read restarts only a disappeared process, then repeats the read once", async () => {
  let attempts = 0,
    restarts = 0;
  const request = recoveringTallyRequest({
    request: async () => {
      if (!attempts++) throw new Error("connection reset");
      return new Response("ok");
    },
    capture: async () => ({ exe: "known" }),
    isRunning: async () => false,
    restart: async () => {
      restarts++;
    },
    ready: async () => {},
    diagnose: async () => {},
  });
  const result = await request("http://127.0.0.1:9000", {
    body: "<TALLYREQUEST>Export</TALLYREQUEST>",
  });
  assert.equal(await result.text(), "ok");
  assert.equal(restarts, 1);
  assert.equal(attempts, 2);
});
test("lost import acknowledgement is never resent, even after successful restart", async () => {
  let attempts = 0,
    restarts = 0;
  const request = recoveringTallyRequest({
    request: async () => {
      attempts++;
      throw new Error("lost acknowledgement");
    },
    capture: async () => ({ exe: "known" }),
    isRunning: async () => false,
    restart: async () => {
      restarts++;
    },
    ready: async () => {},
    diagnose: async () => {},
  });
  await assert.rejects(
    request("http://127.0.0.1:9000", {
      body: "<TALLYREQUEST>Import Data</TALLYREQUEST>",
    }),
    /Reconcile/,
  );
  assert.equal(attempts, 1);
  assert.equal(restarts, 1);
});
test("a live or unknown process never causes a second instance or request replay", async () => {
  for (const running of [true, null]) {
    let restarts = 0;
    const request = recoveringTallyRequest({
      request: async () => {
        throw new Error("offline");
      },
      capture: async () => ({ exe: "known" }),
      isRunning: async () => running,
      restart: async () => {
        restarts++;
      },
      diagnose: async () => {},
    });
    await assert.rejects(
      request("http://127.0.0.1:9000", {
        body: "<TALLYREQUEST>Export</TALLYREQUEST>",
      }),
    );
    assert.equal(restarts, 0);
  }
});
test("an import stays ambiguous when restart readiness requires a handoff", async () => {
  let attempts=0,restarts=0;
  const request=recoveringTallyRequest({
    request:async()=>{attempts++;throw new Error("lost acknowledgement");},
    capture:async()=>({exe:"known"}),isRunning:async()=>false,
    restart:async()=>{restarts++;},ready:async()=>{throw new Error("Complete login");},
    diagnose:async()=>{},
  });
  await assert.rejects(request("http://127.0.0.1:9000",{body:"<TALLYREQUEST>Import Data</TALLYREQUEST>"}),
    error=>error.tallyAmbiguous===true && /Complete login/.test(error.message));
  assert.equal(attempts,1);assert.equal(restarts,1);
});
test("XML errors are diagnosed even when fetch resolves; imports are never resent", async () => {
  let attempts = 0,
    diagnostics = 0;
  const request = recoveringTallyRequest({
    request: async () => {
      attempts++;
      return new Response(
        "<RESPONSE><LINEERROR>bad import</LINEERROR></RESPONSE>",
      );
    },
    capture: async () => ({ exe: "known" }),
    isRunning: async () => false,
    restart: async () => {},
    ready: async () => {},
    diagnose: async () => {
      diagnostics++;
    },
  });
  await assert.rejects(
    request("http://127.0.0.1:9000", {
      body: "<TALLYREQUEST>Import Data</TALLYREQUEST>",
    }),
    /Reconcile/,
  );
  assert.equal(diagnostics, 1);
  assert.equal(attempts, 1);
});

test("a second read failure is diagnosed without another restart", async () => {
  let attempts = 0,
    restarts = 0,
    diagnostics = 0;
  const request = recoveringTallyRequest({
    request: async () => {
      attempts++;
      throw new Error("connection reset");
    },
    capture: async () => ({ exe: "known" }),
    isRunning: async () => false,
    restart: async () => {
      restarts++;
    },
    ready: async () => {},
    diagnose: async () => {
      diagnostics++;
    },
  });
  await assert.rejects(
    request("http://127.0.0.1:9000", {
      body: "<TALLYREQUEST>Export</TALLYREQUEST>",
    }),
    /connection reset/,
  );
  assert.equal(attempts, 2);
  assert.equal(restarts, 1);
  assert.equal(diagnostics, 2);
});

test("unknown JSON or action requests are never replayed after acknowledgement loss", async () => {
  for (const body of [
    JSON.stringify({ tallyrequest: "Import" }),
    "<TALLYREQUEST>Export</TALLYREQUEST><TYPE>Function</TYPE>",
  ]) {
    let attempts = 0;
    const request = recoveringTallyRequest({
      request: async () => {
        attempts++;
        throw new Error("lost");
      },
      capture: async () => ({ exe: "known" }),
      isRunning: async () => false,
      restart: async () => {},
      ready: async () => {},
      diagnose: async () => {},
    });
    await assert.rejects(
      request("http://127.0.0.1:9000", { body }),
      /Reconcile/,
    );
    assert.equal(attempts, 1);
  }
});

test("JSON failure responses are diagnosed without replay", async () => {
  let attempts = 0,
    diagnostics = 0;
  const request = recoveringTallyRequest({
    request: async () => {
      attempts++;
      return Response.json({ status: "0" });
    },
    capture: async () => null,
    diagnose: async () => {
      diagnostics++;
    },
  });
  await assert.rejects(
    request("http://127.0.0.1:9000", {
      body: JSON.stringify({ tallyrequest: "Import" }),
    }),
    /Reconcile/,
  );
  assert.equal(attempts, 1);
  assert.equal(diagnostics, 1);
});
