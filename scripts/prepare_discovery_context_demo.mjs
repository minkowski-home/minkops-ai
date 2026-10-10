/** Opt-in live fixtures for MIN-124. New objects have the MIN124 prefix.
 * Only the explicitly named test companies are touched; this is not a connector.
 */
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { createRequire } from "node:module";
const { XMLParser, XMLBuilder } = createRequire(new URL("../connectors/desktop/package.json", import.meta.url))("fast-xml-parser");
import { discoverClientContext, readTallyBills, commitTallyBill } from "../connectors/desktop/src/index.js";

const companies = JSON.parse(process.env.MINKOPS_TALLY_TEST_COMPANIES ?? "[]");
assert.ok(companies.length >= 2 && companies.every((c) => typeof c === "string" && c.trim()));
const root = process.env.MINKOPS_LIVE_EVIDENCE;
assert.ok(root);
await mkdir(root, { recursive: true });
const escape = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" })[c]);
const parser = new XMLParser({ ignoreAttributes: false, parseTagValue: false });
async function imported(company, kind, records) {
  const body = `<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>${kind}</REPORTNAME><STATICVARIABLES><SVCURRENTCOMPANY>${escape(company)}</SVCURRENTCOMPANY></STATICVARIABLES></REQUESTDESC><REQUESTDATA><TALLYMESSAGE xmlns:UDF="TallyUDF">${records}</TALLYMESSAGE></REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>`;
  const response = await fetch("http://127.0.0.1:9000", { method: "POST", body, signal: AbortSignal.timeout(20000) });
  assert.ok(response.ok);
  const xml = await response.text();
  await writeFile(join(root, `${companies.indexOf(company)}-${kind}-import.xml`), xml);
  const result = parser.parse(xml).RESPONSE;
  assert.equal(Number(result?.ERRORS), 0, xml);
  assert.equal(Number(result?.EXCEPTIONS ?? 0), 0, xml);
  assert.ok(!result?.LINEERROR, xml);
  assert.ok(Number(result.CREATED) + Number(result.ALTERED) + Number(result.IGNORED) > 0, xml);
}
const before = await discoverClientContext({ port: 9000, period: { from: "2026-10-01", to: "2026-10-02" } });
assert.equal(before.partial, false);
// Author this unit once through Tally's native Unit Creation screen. Reuse its
// exported definition rather than inventing installation-specific required fields.
const unit = before.companies.flatMap(c => c.masters.records).find(r => r.type === "UNIT" && r.data.NAME === "MINTestNos");
assert.ok(unit, "Create the synthetic MINTestNos unit in one test company first.");
const unitData = structuredClone(unit.data);
for (const field of ["GUID", "ALTERID", "#text"]) delete unitData[field];
unitData["@_ACTION"] = "Create";
for (const company of companies) {
  assert.ok(before.companies.some((c) => c.company === company));
  if (!before.companies.find(c => c.company === company).masters.records.some(r => r.type === "UNIT" && r.data.NAME === "MINTestNos"))
    await imported(company, "All Masters", new XMLBuilder({ ignoreAttributes: false }).build({ UNIT: unitData }));
  const masters = [
    '<LEDGER NAME="MIN124 Shared Supplier" ACTION="Create"><NAME>MIN124 Shared Supplier</NAME><PARENT>Sundry Creditors</PARENT><ISBILLWISEON>No</ISBILLWISEON></LEDGER>',
    '<LEDGER NAME="MIN124 Purchases" ACTION="Create"><NAME>MIN124 Purchases</NAME><PARENT>Purchase Accounts</PARENT></LEDGER>',
    '<STOCKGROUP NAME="MIN124 Materials" ACTION="Create"><NAME>MIN124 Materials</NAME><PARENT>&#4; Primary</PARENT></STOCKGROUP>',
    '<STOCKITEM NAME="MIN124 Inventory Cement" ACTION="Create"><NAME>MIN124 Inventory Cement</NAME><PARENT>MIN124 Materials</PARENT><BASEUNITS>MINTestNos</BASEUNITS></STOCKITEM>',
  ];
  for (const master of masters) {
    const name = master.match(/<NAME>([^<]+)<\/NAME>/)[1];
    const existing = before.companies.find(c => c.company === company).masters.records.find(r => r.data["@_NAME"] === name);
    if (!existing)
      await imported(company, "All Masters", master);
    else if (existing.type === "STOCKITEM" && existing.data.BASEUNITS !== "MINTestNos")
      await imported(company, "All Masters", master.replace('ACTION="Create"', 'ACTION="Alter"'));
  }
  if (!(await readTallyBills({ company })).some((v) => v.invoice_number === "MIN124-ACCOUNTING-HISTORY")) {
    const result = await commitTallyBill({company, port:9000,
      remote_id: "12400000-0000-4000-8000-000000000001", operation:"append", expected:null,
      data: {vendor:"MIN124 Shared Supplier", invoice_number:"MIN124-ACCOUNTING-HISTORY",
        date:"2026-10-01", purchase_ledger:"MIN124 Purchases", subtotal:100, tax:0,
        tax_ledger:null, total:100, cost_code:null}});
    assert.ok(["saved", "duplicate"].includes(result.outcome), JSON.stringify(result));
  }
}
const snapshot = await discoverClientContext({ port: 9000, period: { from: "2026-10-01", to: "2026-10-02" } });
assert.equal(snapshot.partial, false);
await writeFile(join(root, "seeded-snapshot.json"), JSON.stringify(snapshot, null, 2));
console.log(JSON.stringify(snapshot.companies.map((c) => ({ company: c.company, guid: c.company_guid, masters: c.masters.count, vouchers: c.vouchers.count }))));
