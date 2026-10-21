/** Opt-in rehearsal seeder, not a product connector or a company manager.
 * node scripts/seed_tally_demo.mjs PACKAGE [--apply]
 * Dry-run by default. Requires every pinned company already open/unlocked.
 * Creates only missing QA18 objects, never alters existing data or retries an
 * uncertain import. Re-run explicitly to reconcile after an interruption.
 */
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";
// Reuse the connector's declared dependency; fixtures need no root install.
const { XMLParser, XMLBuilder } = createRequire(new URL("../connectors/desktop/package.json", import.meta.url))("fast-xml-parser");
import { requireOpenCompany, readTallyReferences,
  saveVoucher, tallyTransport, tallyProcesses } from "../connectors/desktop/src/index.js";
import { MASTER_TYPES, readCompanies, readMasters, readVouchers } from "../connectors/desktop/src/sync.js";

const parser = new XMLParser({ignoreAttributes:false,parseTagValue:false,trimValues:true});
const scalar = value => typeof value === "object" && value !== null ? value["#text"] : value;
const list = value => value == null ? [] : Array.isArray(value) ? value : [value];
const escape = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&apos;"})[c]);
const tag = (name, value) => `<${name}>${escape(value)}</${name}>`;
const cents = value => {
  assert.match(String(value), /^-?\d+\.\d{2}$/);
  return BigInt(String(value).replace(".", ""));
};

export function masterXml(master, nativeUnit) {
  const {type,name,parent} = master;
  assert.ok(["GROUP","LEDGER","COSTCATEGORY","COSTCENTRE","UNIT","STOCKGROUP","STOCKCATEGORY","GODOWN","STOCKITEM"].includes(type));
  assert.ok(type === "UNIT" ? /^MKQA[A-Za-z]+$/.test(name) : name.startsWith("QA18 "));
  if (type === "UNIT") {
    assert.ok(nativeUnit && typeof nativeUnit === "object" && scalar(nativeUnit.ISSIMPLEUNIT) === "Yes",
      "A native unit created in this installation is required before import");
    assert.equal(Number(scalar(nativeUnit.ERRKEY) ?? 0),0,"An exception record cannot be a unit template");
    const data = structuredClone(nativeUnit);
    for(const field of ["GUID","ALTERID","MASTERID","REMOTEALTGUID","REMOTEGUID","REMOTEALTERID","ERRKEY","#text"]) delete data[field];
    for(const field of Object.keys(data)) if(field.startsWith("@_")) delete data[field];
    data.NAME = name;
    data.ORIGINALNAME = `QA Test Quantity ${name}`;
    data["@_ACTION"] = "Create";
    return new XMLBuilder({ignoreAttributes:false}).build({UNIT:data});
  }
  let fields = tag("NAME", name);
  if (parent) fields += tag("PARENT", parent);
  if (type === "GROUP") fields += tag("ISSUBLEDGER", "No");
  if (type === "LEDGER") {
    fields += tag("ISBILLWISEON", "No") + tag("ISCOSTCENTRESON", "No");
    if (master.alias) fields += `<LANGUAGENAME.LIST><NAME.LIST TYPE="String">${tag("NAME",name)}${tag("NAME",master.alias)}</NAME.LIST><LANGUAGEID>1033</LANGUAGEID></LANGUAGENAME.LIST>`;
  }
  if (type === "COSTCATEGORY") fields += tag("ALLOCATEREVENUE","Yes") + tag("ALLOCATENONREVENUE","Yes");
  if (type === "COSTCENTRE") fields += tag("CATEGORY",master.category);
  if (type === "STOCKITEM") fields += tag("BASEUNITS", master.unit) + tag("CATEGORY","QA18 Site Consumables");
  return `<${type} NAME="${escape(name)}" ACTION="Create">${fields}</${type}>`;
}

export function voucherXml(voucher) {
  const issued = new Date(voucher.date + "T00:00:00Z");
  if (!/^\d{4}-\d{2}-(01|02|31)$/.test(voucher.date) || !Number.isFinite(+issued)
      || issued.toISOString().slice(0,10) !== voucher.date) throw new Error("Invalid educational voucher date");
  if (voucher.entries.reduce((sum,e) => sum + cents(e.amount),0n) !== 0n) throw new Error("Unbalanced voucher");
  const entries = voucher.inventory ? voucher.entries.filter((_,i) => i !== 1) : voucher.entries;
  let fields = tag("GUID",voucher.guid) + tag("DATE",voucher.date.replaceAll("-",""))
    + tag("VOUCHERTYPENAME",voucher.type) + tag("REFERENCE",voucher.reference)
    + tag("VOUCHERNUMBER",voucher.reference) + tag("PERSISTEDVIEW",voucher.inventory ? "Invoice Voucher View" : "Accounting Voucher View")
    + tag("ISINVOICE",voucher.inventory ? "Yes" : "No")
    + tag("NARRATION",`QA18 synthetic rehearsal history: ${voucher.reference}`);
  if (voucher.party) fields += tag("PARTYLEDGERNAME",voucher.party);
  const entryTag = voucher.inventory ? "LEDGERENTRIES.LIST" : "ALLLEDGERENTRIES.LIST";
  fields += entries.map(e => `<${entryTag}>${tag("LEDGERNAME",e.ledger)}${tag("ISDEEMEDPOSITIVE",cents(e.amount)<0n?"Yes":"No")}${tag("AMOUNT",e.amount)}</${entryTag}>`).join("");
  if (voucher.inventory) {
    const allocation = voucher.entries[1];
    const amount = allocation.amount;
    // A single stock-kit line preserves item, quantity and batch allocation.
    fields += `<ALLINVENTORYENTRIES.LIST>${tag("STOCKITEMNAME",voucher.stock_item)}<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE><RATE>${escape(amount.slice(1))}/MKQANos</RATE><ACTUALQTY>1 MKQANos</ACTUALQTY><BILLEDQTY>1 MKQANos</BILLEDQTY>${tag("AMOUNT",amount)}<BATCHALLOCATIONS.LIST><GODOWNNAME>QA18 Central Stores</GODOWNNAME><BATCHNAME>Primary Batch</BATCHNAME>${tag("AMOUNT",amount)}<ACTUALQTY>1 MKQANos</ACTUALQTY><BILLEDQTY>1 MKQANos</BILLEDQTY></BATCHALLOCATIONS.LIST><ACCOUNTINGALLOCATIONS.LIST>${tag("LEDGERNAME",allocation.ledger)}<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>${tag("AMOUNT",amount)}</ACCOUNTINGALLOCATIONS.LIST></ALLINVENTORYENTRIES.LIST>`;
  }
  return `<VOUCHER REMOTEID="${escape(voucher.guid)}" VCHTYPE="${escape(voucher.type)}" ACTION="Create" OBJVIEW="${voucher.inventory ? "Invoice Voucher View" : "Accounting Voucher View"}">${fields}</VOUCHER>`;
}

export function checkImport(xml, expected) {
  const r = parser.parse(xml).RESPONSE;
  if (!r || Number(r.CREATED) !== expected || Number(r.ALTERED ?? 0) !== 0 || Number(r.ERRORS ?? 0) !== 0
      || Number(r.EXCEPTIONS ?? 0) !== 0 || r.LINEERROR || Number(r.IGNORED ?? 0) !== 0)
    throw new Error("Reconcile Tally before another import: " + xml.slice(0,1500));
}

const recordName = record => String(scalar(record?.["@_NAME"] ?? record?.NAME) ?? "").trim();
const recordEntries = (record, inventory) => list(inventory ? record["LEDGERENTRIES.LIST"] : record["ALLLEDGERENTRIES.LIST"])
  .map(e => [scalar(e.LEDGERNAME), cents(String(scalar(e.AMOUNT)).trim())]);
/** The protocol-5 plan the server would approve for a fixture purchase bill:
 * the adapter proof saves it once, then replays it as a duplicate. */
export function proofPlan(company, voucher, ledgers, purchase) {
  const identity = new Map(ledgers.map(record => [recordName(record), record]));
  const lines = voucher.entries.map(entry => {
    const amount = cents(entry.amount);
    return {ledger:entry.ledger, side:amount > 0n ? "credit" : "debit", amount_cents:Number(amount < 0n ? -amount : amount), allocation:null};
  });
  const year = Number(voucher.date.slice(0,4)) - (Number(voucher.date.slice(5,7)) < 4 ? 1 : 0);
  return {format_version:5, family:"purchase", operation:"append", fence:"retry_after_read",
    company:company.company, company_guid:company.company_guid, port:9000, remote_id:voucher.guid,
    voucher_type:{NAME:recordName(purchase), GUID:scalar(purchase.GUID)},
    header:{date:voucher.date, reference:voucher.reference, party_ledger:voucher.party,
      narration:`Minkops reviewed bill ${voucher.reference}`, tag:null},
    lines,
    references:{company_guid:company.company_guid, ledgers:Object.fromEntries(lines.map(({ledger}) => {
      const record = identity.get(ledger);
      return [ledger, {GUID:scalar(record?.GUID), PARENT:scalar(record?.PARENT), ALTERID:scalar(record?.ALTERID)}];
    }))},
    duplicate:{strategy:"document", families:["purchase","journal"], party_ledger:voucher.party, number:voucher.reference,
      number_fields:["REFERENCE"], window:{from:`${year}-04-01`, to:`${year + 1}-03-31`}},
    expected:null};
}

export function verifyVoucher(expected, actual) {
  assert.equal(scalar(actual.DATE), expected.date.replaceAll("-",""));
  assert.equal(scalar(actual.VOUCHERTYPENAME),expected.type);
  // Invoice ALLLEDGERENTRIES also contains the derived stock accounting lines.
  const found = recordEntries(actual,expected.inventory);
  for (const inventory of list(actual["ALLINVENTORYENTRIES.LIST"] ?? actual["INVENTORYENTRIES.LIST"])) {
    // Native full exports represent an empty repeated section as whitespace.
    if (typeof inventory === "string" && !inventory.trim()) continue;
    assert.equal(scalar(inventory.STOCKITEMNAME),expected.stock_item);
    assert.match(String(scalar(inventory.ACTUALQTY)), /^\s*1(?:\.0+)?\s+MKQANos\s*$/);
    for (const e of list(inventory["ACCOUNTINGALLOCATIONS.LIST"])) found.push([scalar(e.LEDGERNAME),cents(String(scalar(e.AMOUNT)).trim())]);
  }
  const norm = entries => entries.map(([name,amount]) => `${name}:${amount}`).sort();
  assert.deepEqual(norm(found),norm(expected.entries.map(e => [e.ledger,cents(e.amount)])));
  assert.equal(scalar(actual.ISINVOICE), expected.inventory ? "Yes" : "No");
}
function verifyMaster(expected, actual) {
  assert.equal(recordName(actual),expected.name);
  if (expected.parent) assert.equal(scalar(actual.PARENT),expected.parent);
  if (expected.unit) assert.equal(scalar(actual.BASEUNITS),expected.unit);
  if (expected.category) assert.equal(scalar(actual.CATEGORY),expected.category);
  if (expected.type === "UNIT") {
    assert.equal(scalar(actual.ISSIMPLEUNIT),"Yes");
    assert.equal(String(scalar(actual.DECIMALPLACES)).trim(),"3");
  }
}

async function main() {
  const [directory, option] = process.argv.slice(2);
  assert.ok(directory && (!option || option === "--apply"), "Usage: node scripts/seed_tally_demo.mjs PACKAGE [--apply]");
  const root = resolve(directory);
  const plan = JSON.parse(await readFile(join(root,"evidence/seed-plan.json"),"utf8"));
  assert.equal(plan.prefix,"QA18");
  assert.ok(plan.companies.length > 0 && new Set(plan.companies.map(c=>c.company_guid)).size === plan.companies.length);
  // Preflight the complete plan before the first native write.
  for(const c of plan.companies) {
    c.masters.filter(m=>m.type !== "UNIT").forEach(masterXml);
    c.vouchers.forEach(voucherXml);
    await requireOpenCompany(c);
  }
  const config = {port:9000,period:{from:"2026-04-01",to:"2026-10-31"}};
  const diagnostics = [];
  const request = tallyTransport({diagnose: async event => diagnostics.push(event)});
  // The sync's own readers: every master of each mirrored type, and the period's vouchers, per open company.
  const discover = async () => {
    const companies = [];
    for (const open of await readCompanies({port:config.port,request})) {
      const masters = [];
      for (const type of MASTER_TYPES) masters.push(...await readMasters({port:config.port,company:open.name,type,request}));
      const vouchers = await readVouchers({port:config.port,company:open.name,...config.period,request});
      companies.push({company:open.name,company_guid:open.guid,masters:{records:masters,count:masters.length},
        vouchers:{records:vouchers.map(data=>({data})),count:vouchers.length}});
    }
    return {companies};
  };
  const started = await discover();
  const nativeUnit = started.companies.flatMap(c=>c.masters.records)
    .find(r=>r.type === "UNIT" && recordName(r.data) === "MKQANos")?.data;
  if (option === "--apply") assert.ok(nativeUnit,
    "Create the simple MKQANos unit in Tally first; use this installation's native definition.");
  if (nativeUnit) for(const company of plan.companies)
    company.masters.filter(m=>m.type === "UNIT").forEach(m=>masterXml(m,nativeUnit));
  await writeFile(join(root,"evidence",`preflight-${Date.now()}.json`),JSON.stringify(started,null,2));
  const imports = [];
  async function imported(company, report, records, label) {
    if (!records.length) return;
    await requireOpenCompany(company);
    const body = `<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC>${tag("REPORTNAME",report)}<STATICVARIABLES>${tag("SVCURRENTCOMPANY",company.company)}</STATICVARIABLES></REQUESTDESC><REQUESTDATA>${records.map(record=>`<TALLYMESSAGE xmlns:UDF="TallyUDF">${record}</TALLYMESSAGE>`).join("")}</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>`;
    // Persist intent before sending; no automatic resubmission on any failure.
    const attempt = `${company.slug}-${label}-${Date.now()}`;
    await writeFile(join(root,"evidence",`${attempt}-request.xml`),body,{flag:"wx"});
    const response = await request("http://127.0.0.1:9000",{method:"POST",body,
      headers:{"Content-Type":"text/xml; charset=utf-8"},signal:AbortSignal.timeout(60000)});
    const xml = await response.text();
    await writeFile(join(root,"evidence",`${attempt}-response.xml`),xml,{flag:"wx"});
    checkImport(xml,records.length);
    imports.push({company:company.company,kind:label,created:records.length});
  }
  const proofs = [];
  for (const company of plan.companies) {
    let current = started.companies.find(c=>c.company_guid === company.company_guid);
    assert.ok(current);
    const existingMasters = new Map(current.masters.records.map(r=>[`${r.type}:${recordName(r.data)}`,r.data]));
    const missingMasters = company.masters.filter(m=>{
      const found = existingMasters.get(`${m.type}:${m.name}`);
      if (found) verifyMaster(m,found);
      return !found;
    });
    const existingVouchers = new Map(current.vouchers.records.map(r=>[scalar(r.data.REFERENCE),r.data]));
    for(const v of company.vouchers)
      assert.ok(current.vouchers.records.filter(r=>scalar(r.data.REFERENCE)===v.reference).length <= 1,
        `Ambiguous existing voucher ${v.reference}`);
    for(const v of company.vouchers) if(existingVouchers.has(v.reference)) verifyVoucher(v,existingVouchers.get(v.reference));
    console.log(JSON.stringify({company:company.company,mode:option??"dry-run",missing_masters:missingMasters.length,
      missing_vouchers:company.vouchers.filter(v=>!existingVouchers.has(v.reference)).length}));
    if (option !== "--apply") continue;
    const units = missingMasters.filter(m=>m.type === "UNIT");
    // Verify the native unit boundary separately before dependent stock masters.
    await imported(company,"All Masters",units.map(m=>masterXml(m,nativeUnit)),"units");
    if (units.length) {
      const check = await readTallyReferences({company:company.company,port:9000,categories:["units"]},{request});
      const names = check.collections[0].records.map(recordName);
      for(const unit of units) assert.equal(names.filter(name=>name === unit.name).length,1,unit.name);
    }
    await imported(company,"All Masters",missingMasters.filter(m=>m.type !== "UNIT").map(masterXml),"masters");
    const refs = await readTallyReferences({company:company.company,port:9000,categories:["company","ledgers","voucher_types"]},{request});
    assert.ok(refs.collections.every(c=>c.status === "ready"));
    const ledgers = refs.collections.find(c=>c.category === "ledgers").records;
    const purchase = refs.collections.find(c=>c.category === "voucher_types").records.find(r=>recordName(r)==="Purchase");
    assert.ok(purchase);
    const first = company.vouchers[0];
    const approved = proofPlan(company, first, ledgers, purchase);
    const proof = await saveVoucher(approved,{request});
    assert.ok(["saved","duplicate"].includes(proof.outcome),JSON.stringify(proof));
    const replay = await saveVoucher(approved,{request});
    assert.equal(replay.outcome,"duplicate");
    proofs.push({company:company.company,first_save:proof.outcome,replay:replay.outcome});
    await writeFile(join(root,"evidence/adapter-proofs.json"),JSON.stringify(proofs,null,2));
    const rest = company.vouchers.filter(v=>v.reference !== first.reference && !existingVouchers.has(v.reference));
    await imported(company,"Vouchers",rest.map(voucherXml),"vouchers");
    console.log(JSON.stringify({company:company.company,seeded:true,adapter_save:proof.outcome,replay:replay.outcome}));
  }
  if (option !== "--apply") return;
  const after = await discover();
  await writeFile(join(root,"evidence/seeded-snapshot.json"),JSON.stringify(after,null,2));
  for (const company of plan.companies) {
    const actual = after.companies.find(c=>c.company_guid === company.company_guid);
    for (const master of company.masters) {
      const matches = actual.masters.records.filter(r=>r.type===master.type && recordName(r.data)===master.name);
      assert.equal(matches.length,1,master.name);
      verifyMaster(master,matches[0].data);
    }
    for (const voucher of company.vouchers) {
      const matches = actual.vouchers.records.filter(r=>scalar(r.data.REFERENCE)===voucher.reference);
      assert.equal(matches.length,1,voucher.reference);
      verifyVoucher(voucher,matches[0].data);
    }
    const byName = new Map(actual.masters.records.filter(r=>r.type === "LEDGER").map(r=>[recordName(r.data),r.data]));
    for (const bill of company.bills) {
      bill.master_guids = {vendor:scalar(byName.get(bill.supplier)?.GUID),purchase_ledger:scalar(byName.get(bill.purchase_ledger)?.GUID)};
      for(const t of bill.tax_allocations) t.guid = scalar(byName.get(t.ledger)?.GUID);
    }
    await writeFile(join(root,company.slug,"evidence/expected-bills.json"),JSON.stringify(company.bills,null,2));
  }
  // Real negative checks: no closing, switching, starting or restarting Tally.
  const first = plan.companies[0];
  for(const target of [{company:"QA18 company deliberately not open",company_guid:"absent"},
    {company:first.company,company_guid:"wrong-company-guid"}]) {
    await assert.rejects(requireOpenCompany(target),{tallyState:"company_not_open"});
  }
  const summary = {verified_at:new Date().toISOString(),imports,adapter_proofs:proofs,diagnostics,
    processes:await tallyProcesses(),companies:after.companies.map(c=>({company:c.company,guid:c.company_guid,
      exported_masters:c.masters.count,vouchers:c.vouchers.count})),negative_checks:["closed company held","same-name wrong GUID held"]};
  await writeFile(join(root,"evidence/verification.json"),JSON.stringify(summary,null,2));
  console.log(JSON.stringify(summary,null,2));
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href)
  main().catch(error=>{console.error(error);process.exitCode=1;});
