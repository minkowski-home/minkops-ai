import test from "node:test";
import assert from "node:assert/strict";
import { commitTallyBill } from "../src/tally.js";

const data = {
  invoice_number: "MOCK-101",
  vendor: "Supplier",
  date: "2026-10-01",
  purchase_ledger: "Purchases",
  subtotal: 100,
  tax: 18,
  tax_ledger: "Tax",
  total: 118,
  cost_code: null,
};
const plan = {
  company: "Test",
  port: 9000,
  data,
  remote_id: "a9867ffb-262d-5f0e-afce-41619ab9d16e",
  operation: "append",
  expected: null,
};
const exportReply = (vouchers = []) =>
  `<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>${vouchers.join("")}</COLLECTION></DATA></BODY></ENVELOPE>`;
const voucher = (amount = 118) =>
  `<VOUCHER><MASTERID>1</MASTERID><GUID>${plan.remote_id}</GUID><DATE>20261001</DATE><REFERENCE>MOCK-101</REFERENCE><PARTYLEDGERNAME>Supplier</PARTYLEDGERNAME><VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME><ALLLEDGERENTRIES.LIST><LEDGERNAME>Supplier</LEDGERNAME><AMOUNT>${amount}</AMOUNT></ALLLEDGERENTRIES.LIST><ALLLEDGERENTRIES.LIST><LEDGERNAME>Purchases</LEDGERNAME><AMOUNT>-${amount - 18}</AMOUNT></ALLLEDGERENTRIES.LIST><ALLLEDGERENTRIES.LIST><LEDGERNAME>Tax</LEDGERNAME><AMOUNT>-18</AMOUNT></ALLLEDGERENTRIES.LIST></VOUCHER>`;
function fake(replies) {
  const calls = [];
  return {
    calls,
    request: async (url, options) => {
      calls.push(options.body);
      return new Response(replies.shift(), { status: 200 });
    },
  };
}

test("lost acknowledgement replay reads existing bill and performs no second import", async () => {
  const io = fake([exportReply([voucher()])]);
  assert.equal((await commitTallyBill(plan, io)).outcome, "duplicate");
  assert.equal(io.calls.length, 1);
});

test("amounts beyond exact native cents are rejected before touching Tally", async () => {
  const io = fake([]);
  await assert.rejects(
    commitTallyBill(
      { ...plan, data: { ...data, subtotal: 1e20, tax: 0, total: 1e20 } },
      io,
    ),
    /Invalid money/,
  );
  assert.equal(io.calls.length, 0);
});
test("correction is handed off before any import", async () => {
  const io = fake([exportReply([voucher(150)])]);
  const result = await commitTallyBill(plan, io);
  assert.equal(result.outcome, "correction");
  assert.ok(result.current.fingerprint);
  assert.equal(io.calls.length, 1);
});
test("create requires readback of every approved amount", async () => {
  const io = fake([
    exportReply(),
    "<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>",
    exportReply([voucher()]),
  ]);
  assert.equal((await commitTallyBill(plan, io)).outcome, "saved");
  assert.match(io.calls[1], /Import Data/);
  assert.match(io.calls[1], /Test/);
});
test("ambiguous existing keys and stale corrections never import", async () => {
  const io = fake([exportReply([voucher(), voucher()])]);
  assert.equal((await commitTallyBill(plan, io)).outcome, "attention");
  const stale = fake([exportReply([voucher(150)])]);
  assert.equal(
    (
      await commitTallyBill(
        { ...plan, operation: "update", expected: { fingerprint: "old" } },
        stale,
      )
    ).outcome,
    "correction",
  );
  assert.equal(stale.calls.length, 1);
});
test("protocol errors and incomplete readback never count as success", async () => {
  await assert.rejects(
    commitTallyBill(
      plan,
      fake(["<ENVELOPE><HEADER><STATUS>0</STATUS></HEADER></ENVELOPE>"]),
    ),
  );
  await assert.rejects(
    commitTallyBill(
      plan,
      fake([
        exportReply(),
        "<RESPONSE><ERRORS>1</ERRORS><LINEERROR>Invalid</LINEERROR></RESPONSE>",
      ]),
    ),
  );
  await assert.rejects(
    commitTallyBill(
      plan,
      fake([
        exportReply(),
        "<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>",
        exportReply(),
      ]),
    ),
  );
});

test("correction selects the observed date and master ID and rejects create responses", async () => {
  const initial = fake([exportReply([voucher(150)])]);
  const held = await commitTallyBill(plan, initial);
  const io = fake([
    exportReply([voucher(150)]),
    "<RESPONSE><CREATED>0</CREATED><ALTERED>1</ALTERED><ERRORS>0</ERRORS></RESPONSE>",
    exportReply([voucher()]),
  ]);
  assert.equal(
    (
      await commitTallyBill(
        { ...plan, operation: "update", expected: held.current },
        io,
      )
    ).outcome,
    "saved",
  );
  assert.match(
    io.calls[1],
    /DATE="20261001" TAGNAME="MASTER ID" TAGVALUE="1" Action="Alter"/,
  );
  await assert.rejects(
    commitTallyBill(
      { ...plan, operation: "update", expected: held.current },
      fake([
        exportReply([voucher(150)]),
        "<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>",
      ]),
    ),
    /created a voucher/,
  );
});

test("correction leaves complex existing allocations for human review", async () => {
  const complex = voucher(150).replace(
    "</VOUCHER>",
    "<ALLINVENTORYENTRIES.LIST><STOCKITEMNAME>Cement</STOCKITEMNAME><AMOUNT>-132</AMOUNT></ALLINVENTORYENTRIES.LIST></VOUCHER>",
  );
  const io = fake([exportReply([complex])]);
  const current = (await commitTallyBill(plan, io)).current;
  const correction = fake([exportReply([complex])]);
  assert.equal(
    (
      await commitTallyBill(
        { ...plan, operation: "update", expected: current },
        correction,
      )
    ).outcome,
    "attention",
  );
  assert.equal(correction.calls.length, 1);
});

test("changed discovered company prevents any financial import", async () => {
  // discoverTally first probes the company list, then collects references.
  const io = fake([
    '<ENVELOPE><BODY><DATA><COLLECTION><COMPANY NAME="Test"/></COLLECTION></DATA></BODY></ENVELOPE>',
    '<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><COMPANY NAME="Test"><GUID>changed</GUID></COMPANY></COLLECTION></DATA></BODY></ENVELOPE>',
    '<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><LEDGER NAME="Supplier"/></COLLECTION></DATA></BODY></ENVELOPE>',
  ]);
  await assert.rejects(
    commitTallyBill(
      { ...plan, references: { company_guid: "original", ledgers: {} } },
      io,
    ),
  );
  assert.ok(io.calls.every((body) => !body.includes("Import Data")));
});
