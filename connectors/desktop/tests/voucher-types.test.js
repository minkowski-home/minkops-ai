import test from "node:test";
import assert from "node:assert/strict";
import { commitTallyBill, inspectTallyAttention, purchaseVoucherTypes } from "../src/tally.js";

const envelope = (records) =>
  `<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>${records}</COLLECTION></DATA></BODY></ENVELOPE>`;
const type = (name, { parent = "Purchase", reserved = "", guid = `${name}-guid`, active } = {}) =>
  `<VOUCHERTYPE NAME="${name}" RESERVEDNAME="${reserved}"><GUID>${guid}</GUID><PARENT>${parent}</PARENT>${active ? `<ISACTIVE>${active}</ISACTIVE>` : ""}</VOUCHERTYPE>`;
const PREDEFINED = [
  type("Purchase", { reserved: "Purchase" }),
  type("Journal", { parent: "Journal", reserved: "Journal" }),
  type("Purchase Order", { parent: "Purchase Order", reserved: "Purchase Order" }),
];
const data = {
  invoice_number: "INV-7", vendor: "Supplier", date: "2026-10-01", purchase_ledger: "Purchases",
  subtotal: 100, tax: 18, tax_ledger: "Tax", total: 118, cost_code: null,
};
const ledgers = ["Supplier", "Purchases", "Tax"];
const references = (voucher_type) => ({
  company_guid: "company-guid",
  ledgers: Object.fromEntries(ledgers.map((name) => [name, { GUID: `${name}-guid` }])),
  ...(voucher_type ? { voucher_type } : {}),
});
const plan = (voucher_type, extra = {}) => ({
  company: "Test", port: 9000, data, format_version: 3, operation: "append", expected: null,
  remote_id: "a9867ffb-262d-5f0e-afce-41619ab9d16e", references: references(voucher_type), ...extra,
});
const GST = { NAME: "Purchase GST", GUID: "Purchase GST-guid", PARENT: "Purchase", ALTERID: null };
const voucher = (kind, amount = 118, { reference = "INV-7", masterId = "1" } = {}) =>
  `<VOUCHER><MASTERID>${masterId}</MASTERID><GUID>a9867ffb-262d-5f0e-afce-41619ab9d1${String(masterId).padStart(2, "0")}</GUID><DATE>20261001</DATE><REFERENCE>${reference}</REFERENCE><PARTYLEDGERNAME>Supplier</PARTYLEDGERNAME><VOUCHERTYPENAME>${kind}</VOUCHERTYPENAME><ALLLEDGERENTRIES.LIST><LEDGERNAME>Supplier</LEDGERNAME><AMOUNT>${amount}</AMOUNT></ALLLEDGERENTRIES.LIST><ALLLEDGERENTRIES.LIST><LEDGERNAME>Purchases</LEDGERNAME><AMOUNT>-${amount - 18}</AMOUNT></ALLLEDGERENTRIES.LIST><ALLLEDGERENTRIES.LIST><LEDGERNAME>Tax</LEDGERNAME><AMOUNT>-18</AMOUNT></ALLLEDGERENTRIES.LIST></VOUCHER>`;

/** A fake Tally answering by request, so tests describe state, not call order. */
function tally({ types = PREDEFINED, existing = [], saved = null, reply = "<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>" } = {}) {
  const calls = [];
  let imported = false;
  return {
    calls,
    imports: () => calls.filter((body) => body.includes("Import Data")),
    request: async (_url, { body }) => {
      calls.push(body);
      if (body.includes("Import Data")) {
        imported = true;
        return new Response(reply);
      }
      if (body.includes("MinkopsOpenCompanies") || body.includes("<TYPE>Company</TYPE>"))
        return new Response(envelope('<COMPANY NAME="Test"><GUID>company-guid</GUID></COMPANY>'));
      if (body.includes("<TYPE>Ledger</TYPE>"))
        return new Response(envelope(ledgers.map((name) => `<LEDGER NAME="${name}"><GUID>${name}-guid</GUID></LEDGER>`).join("")));
      if (body.includes("<TYPE>VoucherType</TYPE>")) {
        assert.match(body, /IsActive/, "voucher type reads include activation");
        return new Response(envelope(types.join("")));
      }
      if (body.includes("<TYPE>Voucher</TYPE>"))
        return new Response(envelope((imported && saved ? saved : existing).join("")));
      throw new Error(`Unexpected request ${body.slice(0, 120)}`);
    },
  };
}

test("base types follow reserved names and parent chains, like the server", () => {
  const records = [
    { "@_NAME": "Purchase", "@_RESERVEDNAME": "Purchase", PARENT: "Purchase" },
    { "@_NAME": "Purchase GST", "@_RESERVEDNAME": "", PARENT: { "#text": "Purchase" } },
    { "@_NAME": "Purchase Old", PARENT: "Purchase", ISACTIVE: "No" },
    { "@_NAME": "Purchase GST Mumbai", PARENT: "purchase gst" },
    { "@_NAME": "Purchase Order", "@_RESERVEDNAME": "Purchase Order", PARENT: "Purchase Order" },
    { "@_NAME": "Journal", "@_RESERVEDNAME": "Journal" },
    { "@_NAME": "JV Expenses", PARENT: "Journal" },
    { "@_NAME": "Loop A", PARENT: "Loop B" },
    { "@_NAME": "Loop B", PARENT: "Loop A" },
    { "@_NAME": "Purchases", "@_RESERVEDNAME": "Purchase", PARENT: "Purchases" },
  ];
  const types = purchaseVoucherTypes(records);
  assert.deepEqual([...types.purchase].sort(), ["purchase", "purchase gst", "purchase gst mumbai", "purchase old", "purchases"]);
  assert.deepEqual([...types.journal].sort(), ["journal", "jv expenses"]);
  assert.equal(types.active.has("purchase old"), false);
});

test("a bill is written under the run's pinned purchase voucher type", async () => {
  const io = tally({ types: [...PREDEFINED, type("Purchase GST")], saved: [voucher("Purchase GST")] });
  const result = await commitTallyBill(plan(GST), io);
  assert.equal(result.outcome, "saved");
  assert.equal(result.current.voucher_type, "Purchase GST");
  assert.match(io.imports()[0], /VCHTYPE="Purchase GST"/);
  assert.match(io.imports()[0], /<VOUCHERTYPENAME>Purchase GST<\/VOUCHERTYPENAME>/);
});

test("duplicates are found under every purchase type, including inactive ones", async () => {
  for (const kind of ["Purchase", "Purchase Old"]) {
    const io = tally({
      types: [...PREDEFINED, type("Purchase GST"), type("Purchase Old", { active: "No" })],
      existing: [voucher(kind)],
    });
    assert.equal((await commitTallyBill(plan(GST), io)).outcome, "duplicate");
    assert.equal(io.imports().length, 0);
  }
});

test("orders and other non-purchase vouchers are not mistaken for the bill", async () => {
  const io = tally({ types: [...PREDEFINED, type("Purchase GST")], existing: [voucher("Purchase Order")], saved: [voucher("Purchase GST")] });
  assert.equal((await commitTallyBill(plan(GST), io)).outcome, "saved");
});

test("a bill already recorded as a Journal is held, never altered or repeated", async () => {
  const io = tally({ types: [...PREDEFINED, type("Purchase GST"), type("JV Expenses", { parent: "Journal" })], existing: [voucher("JV Expenses", 150)] });
  const result = await commitTallyBill(plan(GST), io);
  assert.equal(result.outcome, "attention");
  assert.match(result.message, /already records this bill as a JV Expenses voucher/);
  assert.ok(result.message.length <= 300);
  assert.equal(io.imports().length, 0);
});

test("a pinned type that changed in Tally stops the save with an actionable message", async () => {
  for (const types of [
    PREDEFINED, // deleted or renamed
    [...PREDEFINED, type("Purchase GST", { guid: "recreated" })],
    [...PREDEFINED, type("Purchase GST", { active: "No" })],
    [...PREDEFINED, type("Purchase GST", { parent: "Journal" })],
    [...PREDEFINED, type("Purchase GST"), type("purchase gst", { guid: "copy" })],
  ]) {
    const io = tally({ types });
    await assert.rejects(commitTallyBill(plan(GST), io), (error) =>
      error.userSafe === true && /Purchase GST changed in Tally since discovery/.test(error.message));
    assert.equal(io.imports().length, 0);
  }
});

test("a correction keeps the existing voucher's own type", async () => {
  const types = [...PREDEFINED, type("Purchase GST")];
  const first = await commitTallyBill(plan(GST), tally({ types, existing: [voucher("Purchase", 150)] }));
  assert.equal(first.outcome, "correction");
  const io = tally({ types, existing: [voucher("Purchase", 150)], saved: [voucher("Purchase")],
    reply: "<RESPONSE><CREATED>0</CREATED><ALTERED>1</ALTERED><ERRORS>0</ERRORS></RESPONSE>" });
  const corrected = await commitTallyBill(plan(GST, { operation: "update", expected: first.current }), io);
  assert.equal(corrected.outcome, "saved");
  assert.match(io.imports()[0], /VCHTYPE="Purchase"/);
});

test("readback under a different type is never reported as saved", async () => {
  const io = tally({ types: [...PREDEFINED, type("Purchase GST")], saved: [voucher("Purchase")] });
  await assert.rejects(commitTallyBill(plan(GST), io), /readback differs/);
});

test("plans pinned before voucher types still write Purchase after a live check", async () => {
  const io = tally({ saved: [voucher("Purchase")] });
  const { voucher_type: _ignored, ...legacy } = references(null);
  assert.equal((await commitTallyBill({ ...plan(null), format_version: undefined, references: legacy }, io)).outcome, "saved");
  assert.match(io.imports()[0], /VCHTYPE="Purchase"/);
});

test("attention checks see the bill under any purchase type", async () => {
  const io = tally({ types: [...PREDEFINED, type("Purchase GST")], existing: [voucher("Purchase GST")] });
  const observed = await inspectTallyAttention(
    { company: "Test", company_guid: "company-guid", port: 9000, vendor: "Supplier", invoice_number: "INV-7" }, io);
  assert.equal(observed.current.voucher_type, "Purchase GST");
});

// One bill save as the companion runs it: session check, commit, reconcile.
import { classifyRejection, saveTallyBill } from "../src/tally.js";

const session = (io, processes = [{ pid: 1 }]) => ({
  request: io.request, sessionRequest: io.request, processes: async () => processes, pc: "PC1", wait: async () => {},
});
function withOpen(io, companies) {
  return {
    ...io,
    request: async (url, options) =>
      options.body.includes("MinkopsOpenCompanies")
        ? new Response(envelope(companies.map(([name, guid]) => `<COMPANY NAME="${name}"><GUID>${guid}</GUID></COMPANY>`).join("")))
        : io.request(url, options),
  };
}

test("a bill waits, unwritten, until its company is open in Tally", async () => {
  const io = tally({ types: [...PREDEFINED, type("Purchase GST")] });
  const result = await saveTallyBill(plan(GST), session(withOpen(io, [["Other", "other-guid"]])));
  assert.deepEqual(result, { outcome: "attention", hold: "company_not_open", message: "Open Test in Tally on PC1, then try again." });
  assert.equal(io.imports().length, 0);
});

test("a same-named copy of the company is never written to", async () => {
  const io = tally({ types: [...PREDEFINED, type("Purchase GST")] });
  const result = await saveTallyBill(plan(GST), session(withOpen(io, [["Test", "copy-guid"]])));
  assert.equal(result.hold, "company_not_open");
  assert.match(result.message, /A different company named Test is open/);
  assert.equal(io.imports().length, 0);
});

test("a closed Tally holds the bill with its typed action", async () => {
  const closed = async () => {
    throw Object.assign(new TypeError("fetch failed"), { cause: { code: "ECONNREFUSED" } });
  };
  const result = await saveTallyBill(plan(GST), { request: closed, sessionRequest: closed, processes: async () => [], pc: "PC1" });
  assert.equal(result.hold, "not_running");
  assert.match(result.message, /Tally isn't open on PC1/);
});

test("a rejected import is reconciled once and explained by its cause", async () => {
  const io = tally({
    types: [...PREDEFINED, type("Purchase GST")],
    reply: "<RESPONSE><ERRORS>1</ERRORS><LINEERROR>Voucher date is out of the financial year</LINEERROR></RESPONSE>",
  });
  const transport = (await import("../src/tally-session.js")).tallyTransport({ request: io.request, processes: async () => [{ pid: 1 }] });
  const result = await saveTallyBill(plan(GST), { ...session(io), request: transport });
  assert.equal(result.outcome, "attention");
  assert.equal(result.hold, "rejected");
  assert.match(result.message, /voucher date/);
  assert.equal(io.imports().length, 1, "the import is never resent");
});

test("Tally's rejection reasons map to one short action each", () => {
  const cases = {
    "Voucher date is out of the financial year": "date",
    "Date is before Books beginning date": "date",
    "You are not authorised to create Vouchers": "permission",
    "Access denied for this user": "permission",
    "Voucher Type 'Purchase GST' does not exist": "voucher_type",
    "Voucher Number is required": "voucher_number",
    "Ledger 'Supplier' does not exist!": "ledger",
    "Something unusual": "other",
  };
  for (const [reason, code] of Object.entries(cases)) {
    const rejection = classifyRejection(reason);
    assert.equal(rejection.code, code, reason);
    assert.ok(rejection.message.length <= 300);
    assert.doesNotMatch(rejection.message, new RegExp(reason.slice(0, 12)), "native text stays in diagnostics");
  }
});
