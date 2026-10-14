import test from "node:test";
import assert from "node:assert/strict";
import * as session from "../src/tally-session.js";
import {
  checkTally,
  classifyTallyFailure,
  openCompanyScope,
  readOpenCompanies,
  tallyTransport,
  TallyUnavailable,
} from "../src/tally-session.js";

const companiesXml = (companies) =>
  `<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>${companies
    .map(
      (c) =>
        `<COMPANY NAME="${c.name}" RESERVEDNAME=""><NAME TYPE="String">${c.name}</NAME><GUID TYPE="String">${c.guid}</GUID><COMPANYNUMBER TYPE="Number"> ${c.number}</COMPANYNUMBER>${c.books ? `<BOOKSFROM TYPE="Date">${c.books}</BOOKSFROM>` : ""}</COMPANY>`,
    )
    .join("")}</COLLECTION></DATA></BODY></ENVELOPE>`;
const refused = () =>
  Object.assign(new TypeError("fetch failed"), {
    cause: Object.assign(new Error("connect ECONNREFUSED 127.0.0.1:9000"), {
      code: "ECONNREFUSED",
    }),
  });
const timedOut = () => new DOMException("The operation timed out.", "TimeoutError");
const noWait = async () => {};
const sachin = { name: "Sachin Infra (2026-27)", guid: "86e14a9b", number: "100000", books: "20260401" };

test("open companies come from one fixed read-only Company collection", async () => {
  const sent = [];
  const companies = await readOpenCompanies({
    port: 9000,
    request: async (url, options) => {
      sent.push({ url, body: options.body });
      return new Response(companiesXml([sachin]));
    },
  });
  assert.deepEqual(companies, [
    {
      company: "Sachin Infra (2026-27)",
      company_guid: "86e14a9b",
      company_number: "100000",
      books_from: "2026-04-01",
    },
  ]);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].url, "http://127.0.0.1:9000");
  assert.match(sent[0].body, /<TYPE>Company<\/TYPE>/);
  assert.doesNotMatch(sent[0].body, /Company on Disk|Import/i);
});

test("companies opened from different data folders may share a company number", () => {
  const scope = openCompanyScope([
    { company: "Sachin Infra (2026-27)", company_guid: "g1", company_number: "100000" },
    { company: "Other Client (2026-27)", company_guid: "g2", company_number: "100000" },
  ]);
  assert.deepEqual(scope.map((c) => c.company_guid), ["g2", "g1"]);
});

test("duplicate open names or GUIDs block because requests address companies by name", () => {
  for (const pair of [
    [{ company: "Copy", company_guid: "a" }, { company: "copy", company_guid: "b" }],
    [{ company: "Original", company_guid: "a" }, { company: "Backup", company_guid: "a" }],
  ])
    assert.throws(
      () => openCompanyScope(pair, { pc: "PRAHLAD-GADHWAL" }),
      (error) =>
        error instanceof TallyUnavailable &&
        error.tallyState === "duplicate_company" &&
        /Close one in Tally on PRAHLAD-GADHWAL/.test(error.message),
    );
});

test("an empty or oversized open scope is a typed state, not a crash", () => {
  assert.throws(() => openCompanyScope([]), { tallyState: "no_company" });
  const many = Array.from({ length: 51 }, (_, i) => ({ company: `C${i}`, company_guid: `g${i}` }));
  assert.throws(() => openCompanyScope(many), { tallyState: "too_many" });
});

test("refused connections distinguish a closed Tally from a closed port", async () => {
  const closed = await classifyTallyFailure(refused(), { processes: async () => [], pc: "PC1" });
  assert.equal(closed.tallyState, "not_running");
  assert.match(closed.message, /Tally isn't open on PC1/);
  const port = await classifyTallyFailure(refused(), {
    processes: async () => [{ pid: 1 }],
    pc: "PC1",
    port: 9000,
  });
  assert.equal(port.tallyState, "port_closed");
  assert.match(port.message, /port 9000/);
  const unknown = await classifyTallyFailure(refused(), { processes: async () => null });
  assert.equal(unknown.tallyState, "not_running");
  assert.match(unknown.message, /port 9000/);
});

test("a busy Tally is retried twice before asking the user to finish a prompt", async () => {
  let attempts = 0;
  await assert.rejects(
    checkTally({
      request: async () => {
        attempts++;
        throw timedOut();
      },
      processes: async () => [{ pid: 1 }],
      pc: "PC1",
      wait: noWait,
    }),
    (error) => error.tallyState === "busy" && /password prompt/.test(error.message),
  );
  assert.equal(attempts, 3);
});

test("a closed Tally is reported at once without retries", async () => {
  let attempts = 0;
  await assert.rejects(
    checkTally({
      request: async () => {
        attempts++;
        throw refused();
      },
      processes: async () => [],
      wait: noWait,
    }),
    { tallyState: "not_running" },
  );
  assert.equal(attempts, 1);
});

test("invalid and failed responses are typed, never parsed as companies", async () => {
  for (const body of [
    "<ENVELOPE><HEADER><STATUS>0</STATUS></HEADER></ENVELOPE>",
    "<ENVELOPE><BODY>",
    "<!DOCTYPE x><ENVELOPE/>",
    "<ENVELOPE><LINEERROR>Unknown request</LINEERROR></ENVELOPE>",
  ])
    await assert.rejects(
      checkTally({ request: async () => new Response(body), processes: async () => [{ pid: 1 }], wait: noWait }),
      { tallyState: "invalid_response" },
    );
});

test("a ready check lists companies and warns about a second Tally", async () => {
  const ready = await checkTally({
    request: async () => new Response(companiesXml([sachin])),
    processes: async () => [{ pid: 1 }, { pid: 2 }],
    pc: "PC1",
    wait: noWait,
  });
  assert.equal(ready.state, "ready");
  assert.deepEqual(ready.companies.map((c) => c.company), ["Sachin Infra (2026-27)"]);
  assert.deepEqual(ready.warnings.map((w) => w.state), ["multiple_instances"]);
});

test("every typed message fits a job receipt and names the PC", async () => {
  const pc = "X".repeat(80);
  for (const error of [
    await classifyTallyFailure(refused(), { processes: async () => [], pc }),
    await classifyTallyFailure(refused(), { processes: async () => [{ pid: 1 }], pc }),
    await classifyTallyFailure(timedOut(), { processes: async () => [{ pid: 1 }], pc }),
    (() => { try { openCompanyScope([], { pc }); } catch (e) { return e; } })(),
  ]) {
    assert.ok(error.message.length <= 300, error.message);
    assert.ok(error.message.includes(pc));
    assert.equal(error.userSafe, true);
  }
});

test("the session module exposes no way to start, close or restart Tally", () => {
  for (const name of Object.keys(session))
    assert.doesNotMatch(name, /start|close|restart|install|wait/i);
});

const read = { body: "<ENVELOPE><HEADER><TALLYREQUEST>Export</TALLYREQUEST></HEADER></ENVELOPE>" };
const write = { body: "<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER></ENVELOPE>" };

test("transport retries a timed-out read, then reports a busy Tally", async () => {
  let attempts = 0;
  const diagnostics = [];
  const transport = tallyTransport({
    request: async () => {
      attempts++;
      throw timedOut();
    },
    processes: async () => [{ pid: 1 }],
    diagnose: async (record) => diagnostics.push(record),
    wait: noWait,
  });
  await assert.rejects(transport("http://127.0.0.1:9000", read), { tallyState: "busy" });
  assert.equal(attempts, 3);
  assert.equal(diagnostics.length, 3);
  assert.equal(diagnostics[0].cause, "TimeoutError");
  assert.equal(typeof diagnostics[0].elapsed_ms, "number");
});

test("transport never resends a write and keeps its outcome ambiguous", async () => {
  for (const failure of [refused, timedOut]) {
    let attempts = 0;
    const transport = tallyTransport({
      request: async () => {
        attempts++;
        throw failure();
      },
      processes: async () => [],
      diagnose: async () => {},
      wait: noWait,
    });
    await assert.rejects(
      transport("http://127.0.0.1:9000", write),
      (error) => error.tallyAmbiguous === true && error.tallyState === "not_running",
    );
    assert.equal(attempts, 1);
  }
});

test("unknown JSON or action requests are treated as writes", async () => {
  for (const body of [
    JSON.stringify({ tallyrequest: "Import" }),
    "<TALLYREQUEST>Export</TALLYREQUEST><TYPE>Function</TYPE>",
  ]) {
    let attempts = 0;
    const transport = tallyTransport({
      request: async () => {
        attempts++;
        throw timedOut();
      },
      processes: async () => [{ pid: 1 }],
      diagnose: async () => {},
      wait: noWait,
    });
    await assert.rejects(transport("http://127.0.0.1:9000", { body }), { tallyAmbiguous: true });
    assert.equal(attempts, 1);
  }
});

test("a rejected import keeps Tally's reason for classification and diagnosis", async () => {
  const diagnostics = [];
  const transport = tallyTransport({
    request: async () =>
      new Response("<RESPONSE><ERRORS>1</ERRORS><LINEERROR>Voucher date is missing</LINEERROR></RESPONSE>"),
    processes: async () => [{ pid: 1 }],
    diagnose: async (record) => diagnostics.push(record),
  });
  await assert.rejects(
    transport("http://127.0.0.1:9000", write),
    (error) => error.tallyAmbiguous === true && error.tallyLineError === "Voucher date is missing",
  );
  assert.equal(diagnostics[0].line_error, "Voucher date is missing");
});

test("JSON failure responses are diagnosed without replay", async () => {
  let attempts = 0;
  const transport = tallyTransport({
    request: async () => {
      attempts++;
      return Response.json({ status: "0" });
    },
    processes: async () => [],
    diagnose: async () => {},
  });
  await assert.rejects(
    transport("http://127.0.0.1:9000", { body: JSON.stringify({ tallyrequest: "Import" }) }),
    /Reconcile/,
  );
  assert.equal(attempts, 1);
});

test("a read that succeeds after a retry returns the response body", async () => {
  let attempts = 0;
  const transport = tallyTransport({
    request: async () => {
      if (++attempts === 1) throw timedOut();
      return new Response("<ENVELOPE/>");
    },
    processes: async () => [{ pid: 1 }],
    diagnose: async () => {},
    wait: noWait,
  });
  assert.equal(await (await transport("http://127.0.0.1:9000", read)).text(), "<ENVELOPE/>");
});

test("only whitelisted tally.ini settings are read for diagnostics", async () => {
  const { parseTallyIni, readTallyIni } = await import("../src/tally-session.js");
  const ini = [
    ";;TallyPrime workstation specific parameters file", "[TALLY]",
    "Tally Gateway Server=PRAHLAD-GADHWAL:9999", "User TDL=Yes", "Default Companies=Yes", "Load=100000",
    "Data=D:\\TALLY PRIME\\SACHIN INFRA ORIGINAL DATA", "Client Server=None", "ServerPort=9000",
    "Enable ODBC Server=Yes", "LicTimeout=", "Tally Gold License Server=secret-host", "Export Path=F:\\PRAHLAD\\BLR",
  ].join("\r\n");
  assert.deepEqual(parseTallyIni(ini), {
    "Tally Gateway Server": "PRAHLAD-GADHWAL:9999", "User TDL": "Yes", "Default Companies": "Yes", Load: "100000",
    Data: "D:\\TALLY PRIME\\SACHIN INFRA ORIGINAL DATA", "Client Server": "None", ServerPort: "9000",
    "Enable ODBC Server": "Yes",
  });
  assert.equal(await readTallyIni(null), null);
  assert.equal(await readTallyIni("C:\\missing\\tally.exe", { read: async () => { throw new Error("ENOENT"); } }), null);
});
