import test from "node:test";
import assert from "node:assert/strict";
import { XMLParser } from "fast-xml-parser";
import { buildLedger, createLedger, readLedger, validLedgerPlan } from "../src/tally.js";

const gst = {registration_type: "Regular", gstin: "08AABCM1256F1ZR", state: "Rajasthan", applicable_from: "2026-04-01"};
const mailing = {address: ["Synthetic Industrial Road", "Sikar"], state: "Rajasthan", country: "India", pincode: "332001"};
const plan = {kind: "ledger", protocol: 8, company: "Test", company_guid: "company-guid", port: 9000, shape: "dated",
  ledger: {name: "New & Sons <Synthetic>", under: "Sundry Creditors", billwise: true, credit_period: 30,
    applicable_from: "2026-04-01", mailing, gst}};
const parse = source => new XMLParser({ignoreAttributes: false, parseTagValue: false}).parse(source).LEDGER;

test("a ledger carries exactly the approved fields, in the dated shape this Tally keeps", () => {
  const ledger = parse(buildLedger(plan));
  assert.deepEqual(ledger, {"@_NAME": "New & Sons <Synthetic>", "@_ACTION": "Create", NAME: "New & Sons <Synthetic>",
    PARENT: "Sundry Creditors", ISBILLWISEON: "Yes", BILLCREDITPERIOD: "30 Days",
    "LEDGSTREGDETAILS.LIST": {APPLICABLEFROM: "20260401", GSTREGISTRATIONTYPE: "Regular", GSTIN: "08AABCM1256F1ZR",
      PLACEOFSUPPLY: "Rajasthan"},
    "LEDMAILINGDETAILS.LIST": {APPLICABLEFROM: "20260401", MAILINGNAME: "New & Sons <Synthetic>", STATE: "Rajasthan",
      COUNTRY: "India", PINCODE: "332001", "ADDRESS.LIST": {"@_TYPE": "String", ADDRESS: ["Synthetic Industrial Road", "Sikar"]}}});
});

test("an older Tally gets the older fields, and a party with no GST or address gets none", () => {
  const legacy = parse(buildLedger({...plan, shape: "legacy"}));
  assert.deepEqual([legacy.PARTYGSTIN, legacy.GSTREGISTRATIONTYPE, legacy.PLACEOFSUPPLY, legacy.LEDSTATENAME, legacy.PINCODE],
    ["08AABCM1256F1ZR", "Regular", "Rajasthan", "Rajasthan", "332001"]);
  assert.equal(legacy["LEDGSTREGDETAILS.LIST"], undefined);
  const payee = parse(buildLedger({...plan, ledger: {...plan.ledger, name: "Ramesh Kumar", under: "Staff Advances",
    billwise: false, credit_period: null, mailing: null, gst: null}}));
  assert.deepEqual(payee, {"@_NAME": "Ramesh Kumar", "@_ACTION": "Create", NAME: "Ramesh Kumar", PARENT: "Staff Advances",
    ISBILLWISEON: "No"});
});

test("a plan the companion cannot vouch for is refused before anything is written", () => {
  for (const ledger of [{...plan.ledger, credit_period: 30, billwise: false}, {...plan.ledger, credit_period: 400},
    {...plan.ledger, gst: {...gst, gstin: "08AABCM1256F1ZA"}}, {...plan.ledger, name: "Bad\nName"},
    {...plan.ledger, mailing: {...mailing, pincode: "12345"}}, {...plan.ledger, under: ""}])
    assert.throws(() => validLedgerPlan({...plan, ledger}));
  assert.throws(() => validLedgerPlan({...plan, protocol: 7}));
});

const envelope = records => `<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>${records}</COLLECTION></DATA></BODY></ENVELOPE>`;
const company = guid => `<COMPANY NAME="Test"><NAME>Test</NAME><GUID>${guid}</GUID><COMPANYNUMBER>100000</COMPANYNUMBER></COMPANY>`;
const created = '<LEDGER NAME="New &amp; Sons &lt;Synthetic&gt;"><GUID>ledger-guid</GUID><PARENT>Sundry Creditors</PARENT><ALTERID>9</ALTERID><ISBILLWISEON>Yes</ISBILLWISEON><BILLCREDITPERIOD>30 Days</BILLCREDITPERIOD></LEDGER>';
function native({exists = false, wrongBefore = false, loseAck = false} = {}) {
  let imported = false; const calls = [];
  return {calls, request: async (_url, options) => {
    const body = options.body; calls.push(body);
    if (body.includes("<TALLYREQUEST>Import")) {
      imported = true;
      if (loseAck) throw new Error("Lost acknowledgement");
      return new Response("<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>");
    }
    if (body.includes("MinkopsOpenCompanies")) return new Response(envelope(company("company-guid")));
    const records = body.includes("<TYPE>Ledger</TYPE>") || body.includes("MinkopsLedger") ? (exists || imported ? created : "")
      : body.includes("<TYPE>Voucher</TYPE>") ? "" : company(wrongBefore ? "wrong-guid" : "company-guid");
    return new Response(envelope(records));
  }};
}

test("a ledger is read before it is imported, imported once, and read back in full for the server to verify", async () => {
  const io = native();
  const observed = await createLedger(plan, io);
  assert.equal(observed.company_guid, "company-guid");
  assert.deepEqual([observed.ledger.GUID, observed.ledger.BILLCREDITPERIOD], ["ledger-guid", "30 Days"]);
  const imports = io.calls.filter(c => c.includes("<TALLYREQUEST>Import"));
  assert.equal(imports.length, 1);
  assert.match(imports[0], /<PARENT>Sundry Creditors<\/PARENT>/);
  // A ledger that already has the name is read back as it is, never created twice.
  const existing = native({exists: true});
  assert.equal((await createLedger(plan, existing)).ledger.GUID, "ledger-guid");
  assert.equal(existing.calls.some(c => c.includes("<TALLYREQUEST>Import")), false);
});

test("another company open, or a lost acknowledgement, never leads to a second import", async () => {
  const wrong = native({wrongBefore: true});
  await assert.rejects(createLedger(plan, wrong), /company changed/);
  assert.equal(wrong.calls.filter(c => c.includes("<TALLYREQUEST>Import")).length, 0);
  const lost = native({loseAck: true});
  await assert.rejects(createLedger(plan, lost), /Lost acknowledgement/);
  // The person's next Create this ledger finds the one the lost acknowledgement created.
  assert.equal((await createLedger(plan, lost)).ledger.GUID, "ledger-guid");
  assert.equal(lost.calls.filter(c => c.includes("<TALLYREQUEST>Import")).length, 1);
});

test("a readback is a company-scoped, GUID-filtered collection that refuses another company's ledger", async () => {
  const request = async (_url, options) => {
    if (options.body.includes("MinkopsOpenCompanies")) return new Response(envelope(company("company-guid")));
    assert.ok(options.body.includes("<SVCURRENTCOMPANY>Test</SVCURRENTCOMPANY>"));
    assert.ok(options.body.includes('$GUID = "expected-guid"'));
    return new Response(envelope('<LEDGER NAME="Existing"><GUID>wrong-company-guid</GUID></LEDGER>'));
  };
  await assert.rejects(() => readLedger(plan, "Existing", {request, identity: {GUID: "expected-guid"}}), /missing or ambiguous/);
});
