/** Opt-in fault injection against explicitly authorised local test companies.
 * Uses the production recovery transport and real Windows process observations.
 * Educational/licence screens remain a native UI handoff; do not bypass them.
 */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import {
  recoveringTallyRequest, captureTallyProcess, tallyProcessRunning,
  restartTallyProcess, waitForTally, tallyCrashEvents,
  discoverClientContext, commitTallyBill, readTallyBills,
  tallyCompanyNumber,
} from "../connectors/desktop/src/index.js";

const company = process.env.MINKOPS_TALLY_TEST_COMPANY;
const root = process.env.MINKOPS_LIVE_EVIDENCE;
const stage = process.argv[2];
assert.ok(company && root && ["probe", "masters", "vouchers", "preflight", "import", "readback", "ack-applied", "ack-absent", "ack-different"].includes(stage));
await mkdir(root, { recursive: true });
if (process.argv[3] === "--resume") {
  // An explicit operator continuation after Tally's native licence/login handoff.
  // Preserve the original plan and counts; an attempted import is read back only.
  const previous = JSON.parse(await readFile(join(root, `recovery-${stage}.json`), "utf8"));
  assert.equal(previous.stage, stage);
  assert.equal(previous.company, company);
  assert.ok(previous.failure && previous.restarts === 1 && previous.imports <= 1);
  const current = await captureTallyProcess();
  assert.equal(current?.exe, previous.observed.exe);
  let imports = previous.imports;
  const request = async (url, options) => {
    if (/<TALLYREQUEST>Import(?: Data)?<\/TALLYREQUEST>/.test(options.body)) imports++;
    return fetch(url, options);
  };
  let result;
  if (["probe", "masters", "vouchers"].includes(stage)) {
    result = await discoverClientContext({port:9000,period:{from:"2026-10-01",to:"2026-10-02"}}, {request});
    assert.equal(result.partial, false);
    assert.equal(result.companies.length, 2);
    assert.equal(imports, 0);
  } else {
    assert.equal(previous.plan.company, company);
    result = await commitTallyBill(previous.plan, {request, reconciliationOnly: previous.imports > 0});
    assert.ok(["saved", "duplicate"].includes(result.outcome));
    assert.equal(imports, 1, "Explicit resume must never replay an uncertain import.");
    const matches = (await readTallyBills({company})).filter(v=>v.invoice_number===previous.plan.data.invoice_number);
    assert.equal(matches.length, 1);
  }
  await writeFile(join(root, `recovery-${stage}-resumed.json`), JSON.stringify({previous, imports, result, explicit_resume:true}, null, 2));
  console.log(JSON.stringify({stage, explicit_resume:true, imports, outcome:result.outcome ?? "ready"}));
  process.exit(0);
}
const observed = await captureTallyProcess();
assert.ok(observed, "Start one known Tally instance.");
// Match the companion's startup fallback: use identities exported by this
// running instance when the operator loaded companies through Tally's UI.
const initial = await discoverClientContext({port:9000,period:{from:"2026-10-01",to:"2026-10-02"}});
assert.equal(initial.partial,false);
observed.loads = [...new Set([...observed.loads, ...initial.companies.map(c => tallyCompanyNumber(c.identity?.COMPANYNUMBER)).filter(Boolean)])];
assert.ok(observed.loads.length >= 2, "Load both authorised companies before fault injection.");
const diagnostics = [];
let injections = 0, restarts = 0, imports = 0;
process.on("uncaughtException", async (error) => {
  await writeFile(join(root, `recovery-${stage}.json`),JSON.stringify({stage,company,observed,
    injections,restarts,imports,diagnostics,plan,failure:error.message},null,2));
  console.error(error.message);
  process.exitCode = 1;
});
const data = {vendor:"MIN124 Shared Supplier", invoice_number:"MIN124-RECOVERY-" + randomUUID().slice(0,8),
  date:"2026-10-01", purchase_ledger:"MIN124 Purchases", subtotal:123, tax:0, tax_ledger:null, total:123, cost_code:null};
const plan = {company, port:9000, remote_id:randomUUID(), operation:"append", expected:null, data};
if (stage === "ack-different") {
  const first = await commitTallyBill({...plan, data:{...data,subtotal:124,total:124}});
  assert.equal(first.outcome,"saved");
}
const request = recoveringTallyRequest({
  capture: async () => observed, isRunning: tallyProcessRunning,
  restart: async (p) => { restarts++; await restartTallyProcess(p); },
  ready: waitForTally,
  diagnose: async (d) => { diagnostics.push({...d,events:await tallyCrashEvents()}); },
  request: async (url, options) => {
    const write = /<TALLYREQUEST>Import(?: Data)?<\/TALLYREQUEST>/.test(options.body);
    if (write) imports++;
    const trigger = !injections && (
      stage === "probe" && options.body.includes("<ID>MinkopsCompanies</ID>") ||
      stage === "masters" && options.body.includes("<ID>List of Accounts</ID>") ||
      stage === "vouchers" && options.body.includes("<ID>DayBook</ID>") ||
      stage === "preflight" && !write ||
      stage === "readback" && imports > 0 && !write ||
      ["import", "ack-applied", "ack-absent"].includes(stage) && write
    );
    if (!trigger) return fetch(url,options);
    injections++;
    if (["import","ack-applied"].includes(stage)) {
      const response = await fetch(url,options);
      await response.text(); // Simulate losing the acknowledgement after application.
    }
    if (!["ack-applied","ack-absent"].includes(stage)) {
      assert.equal(await tallyProcessRunning(observed),true);
      execFileSync("powershell.exe", ["-NoProfile","-NonInteractive","-Command",
        `Stop-Process -Id ${Number(observed.pid)} -Force -ErrorAction Stop`], {windowsHide:true});
    }
    throw new Error("Controlled MIN124 transport interruption: " + stage);
  },
});
let result;
if (["probe","masters","vouchers"].includes(stage)) {
  result = await discoverClientContext({port:9000,period:{from:"2026-10-01",to:"2026-10-02"}}, {request});
  assert.equal(result.partial,false);
  assert.equal(result.companies.length,2);
} else if (stage === "ack-different") {
  result = await commitTallyBill(plan,{request,reconciliationOnly:true});
  assert.equal(result.outcome,"correction");
} else {
  try { result = await commitTallyBill(plan,{request}); }
  catch (error) {
    assert.equal(error.tallyAmbiguous,true);
    result = await commitTallyBill(plan,{request,reconciliationOnly:true});
  }
  assert.ok(["saved","duplicate","attention"].includes(result.outcome), JSON.stringify(result));
  assert.equal(imports,1,"Unknown imports must not replay automatically.");
  if (stage === "ack-absent") assert.equal(result.outcome,"attention");
  else assert.notEqual(result.outcome,"attention");
  const matches = (await readTallyBills({company})).filter(v=>v.invoice_number===data.invoice_number);
  assert.equal(matches.length,stage === "ack-absent" ? 0 : 1);
}
assert.equal(restarts,["ack-applied","ack-absent","ack-different"].includes(stage) ? 0 : 1);
await writeFile(join(root, `recovery-${stage}.json`),JSON.stringify({stage,company,observed,injections,restarts,imports,diagnostics,result},null,2));
console.log(JSON.stringify({stage,injections,restarts,imports,outcome:result.outcome??"ready"}));
