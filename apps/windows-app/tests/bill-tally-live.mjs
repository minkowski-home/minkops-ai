/** Opt-in synthetic company test. Creates/updates only a uniquely named mock bill. */
import assert from "node:assert/strict";
import {
  commitTallyBill,
  readTallyBills,
} from "../../../connectors/desktop/src/tally.js";
if (!process.env.MINKOPS_TALLY_TEST_COMPANY)
  throw new Error("Set the explicitly authorized test company.");
const plan = {
  company: process.env.MINKOPS_TALLY_TEST_COMPANY,
  port: 9000,
  remote_id: "d7ba511e-eec8-5d45-9956-c41691511901",
  operation: "append",
  expected: null,
  data: {
    vendor: "Minkops Demo Supplier",
    invoice_number: "MINKOPS-MIN119-SEED-100",
    date: "2026-10-01",
    purchase_ledger: "Minkops Demo Purchases",
    subtotal: 100,
    tax: 18,
    tax_ledger: "Minkops Demo Tax",
    total: 118,
    cost_code: null,
  },
};
let first = await commitTallyBill(plan);
if (first.outcome === "correction") {
  // A preceding run deliberately left the corrected amount. Restore only the
  // observed synthetic voucher, with the same compare-before-write contract.
  first = await commitTallyBill({
    ...plan,
    operation: "update",
    expected: first.current,
  });
}
assert.ok(["saved", "duplicate"].includes(first.outcome));
assert.equal((await commitTallyBill(plan)).outcome, "duplicate");
const correction = {
  ...plan,
  data: { ...plan.data, subtotal: 200, tax: 36, total: 236 },
};
const handoff = await commitTallyBill(correction);
assert.equal(handoff.outcome, "correction");
assert.equal(
  (
    await commitTallyBill({
      ...correction,
      operation: "update",
      expected: handoff.current,
    })
  ).outcome,
  "saved",
);
assert.equal((await commitTallyBill(correction)).outcome, "duplicate");
assert.equal(
  (await readTallyBills(plan)).filter(
    (v) => v.invoice_number === plan.data.invoice_number,
  ).length,
  1,
);
console.log(
  "Live Tally create, duplicate replay, correction handoff, approved update and unique readback passed.",
);
