import test from "node:test";
import assert from "node:assert/strict";
import { createExecutor, uploadWithRetry } from "../../../platform/desktop-runtime/src/jobs.js";

const job = (operation, input = {}) => ({ id: "job-1", claim_token: "claim-1", operation, input });

function executor({ request, connectors = {}, recorded = [] }) {
  return createExecutor({
    connectors, request, pc: "TEST-PC", planVersion: 5, transportFor: () => "tally-transport",
    grantFor: () => ({ root: "/granted" }), durableIntent: () => async () => true,
    recordDiagnostic: (j, record) => recorded.push([j.id, record]),
  });
}

test("a sync uploads numbered pages against its own claim through the native collector", async () => {
  const posted = [];
  const request = async (path, body) => {
    if (path.includes("/plan?claim_token=claim-1")) return { protocol: 1, port: 9000 };
    posted.push([path, body]);
    return { instructions: [] };
  };
  const runSync = async (plan, { request: transport, upload, pc }) => {
    assert.deepEqual([plan.port, transport, pc], [9000, "tally-transport", "TEST-PC"]);
    await upload("companies", { companies: [] });
    await upload("counts", { company: "c", counts: {} });
    return { protocol: 1, companies: [] };
  };
  const result = await executor({ request, connectors: { runSync } })(job("tally.sync"));
  assert.deepEqual(result, { protocol: 1, companies: [] });
  assert.deepEqual(posted.map(([path, body]) => [path, body.seq, body.kind, body.claim_token]), [
    ["/api/desktop/worker/jobs/job-1/sync", 0, "companies", "claim-1"],
    ["/api/desktop/worker/jobs/job-1/sync", 1, "counts", "claim-1"]]);
});

test("a page is resent with the same sequence after a transport failure, never after an answer", async () => {
  const seen = [];
  let failures = 1;
  const send = async (page) => {
    seen.push(page.seq);
    if (failures-- > 0) throw new TypeError("fetch failed");
    return { ok: true };
  };
  assert.deepEqual(await uploadWithRetry(send, { seq: 4 }, { wait: async () => {} }), { ok: true });
  assert.deepEqual(seen, [4, 4]);
  const refused = Object.assign(new Error("This sync page was already received with different content."), { status: 409 });
  let calls = 0;
  await assert.rejects(uploadWithRetry(async () => { calls++; throw refused; }, { seq: 5 }, { wait: async () => {} }),
    { status: 409 });
  assert.equal(calls, 1);
});

test("a voucher plan newer than this companion executes is refused before Tally is touched", async () => {
  let saved = false;
  const request = async () => ({ format_version: 6 });
  await assert.rejects(executor({ request, connectors: { saveVoucher: async () => { saved = true; } } })(job("tally.write")),
    /Unsupported voucher plan/);
  assert.equal(saved, false);
});

test("a run's write saves its stored plan behind the durable local fence", async () => {
  const plan = { format_version: 5, remote_id: "4f1c2f4e-0d63-5b5e-9d3a-2a51f0f4a001", fence: "strict" };
  const fenced = [];
  const request = async (path) => {
    assert.match(path, /\/jobs\/job-1\/plan\?claim_token=claim-1/);
    return plan;
  };
  const saveVoucher = async (voucher, { beforeImport, pc }) => {
    assert.deepEqual([voucher, pc], [plan, "TEST-PC"]);
    fenced.push(await beforeImport(voucher));
    return { outcome: "saved", current: { guid: "g-1" } };
  };
  const result = await executor({ request, connectors: { saveVoucher } })(job("tally.write", { write_id: "w-1" }));
  assert.deepEqual([result, fenced], [{ outcome: "saved", current: { guid: "g-1" } }, [true]]);
});

test("an approved ledger is created by the fixed master operation, never through a voucher import", async () => {
  const plan = { kind: "ledger", protocol: 8, company: "Rehearsal Infra", company_guid: "c-1", ledger: { name: "Cabin Services" } };
  const calls = [];
  const request = async (path) => {
    assert.match(path, /\/jobs\/job-1\/plan\?claim_token=claim-1/);
    return plan;
  };
  const createLedger = async (given, options) => {
    calls.push([given, options]);
    return { company_guid: "c-1", ledger: { GUID: "g-new" } };
  };
  const saveVoucher = async () => { throw new Error("A ledger write must not import a voucher."); };
  const current = createExecutor({ connectors: { createLedger, saveVoucher }, request, pc: "TEST-PC", planVersion: 8,
    transportFor: () => "tally-transport", grantFor: () => ({}), durableIntent: () => async () => true });
  const result = await current(job("tally.ledger", { write_id: "w-2" }));
  assert.deepEqual(result, { company_guid: "c-1", ledger: { GUID: "g-new" } });
  assert.deepEqual(calls, [[plan, { request: "tally-transport" }]]);
  // A companion that writes an older protocol refuses the plan before Tally is touched.
  await assert.rejects(executor({ request, connectors: { createLedger, saveVoucher } })(
    job("tally.ledger", { write_id: "w-3" })), /Unsupported ledger plan/);
  assert.equal(calls.length, 1);
});

test("a failed connection check leaves a diagnostic for the receipt", async () => {
  const recorded = [];
  const checkTally = async () => { throw Object.assign(new Error("Tally isn't open on TEST-PC."), { tallyState: "not_running" }); };
  await assert.rejects(executor({ request: async () => ({}), connectors: { checkTally }, recorded })(job("tally.probe")));
  assert.deepEqual(recorded.map(([id, r]) => [id, r.state]), [["job-1", "not_running"]]);
});

test("a connection check reads this PC's own Tally port", async () => {
  const ports = [];
  const checkTally = async ({ port, pc }) => {
    ports.push([port, pc]);
    return { companies: [{ company: "Minkops Test" }] };
  };
  const check = executor({ request: async () => ({}), connectors: { checkTally } });
  assert.deepEqual(await check({ ...job("tally.probe"), tally_port: 9101 }), { available: true, companies: ["Minkops Test"] });
  // A server that names no port means Tally's default.
  await check(job("tally.probe"));
  assert.deepEqual(ports, [[9101, "TEST-PC"], [9000, "TEST-PC"]]);
});

test("unknown operations are refused", async () => {
  await assert.rejects(executor({ request: async () => ({}) })(job("shell.run")), /Unsupported local operation/);
});
