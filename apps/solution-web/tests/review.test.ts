import test from "node:test";
import assert from "node:assert/strict";
import { recordCounts, recordLine, settled, settles } from "../src/starter/workspace/review.ts";

test("a bill reads as its supplier, its particulars and its total in Indian grouping", () => {
  assert.deepEqual(recordLine({ id: "b", version: 2, kind: "bill", status: "proposed", file: "sunrise.pdf", bill: 1,
    supplier: "Sunrise Office Systems", number: "SOS/26/0412", date: "2026-09-01", total: 188800,
    company: "Rehearsal Infra", voucher_type: "Purchase" }), {
    title: "Sunrise Office Systems", detail: "No. SOS/26/0412 · 2026-09-01 · Rehearsal Infra · Purchase",
    amount: "1,88,800.00",
  });
  // A bill not yet read names its place in the file.
  assert.equal(recordLine({ id: "b", version: 1, kind: "bill", status: "pending", file: "scan.pdf", bill: 2 }).title,
    "Bill 2 of scan.pdf");
});

test("a statement row reads as its narration, which way the money went and the bills it settles", () => {
  const paid = recordLine({ id: "r", version: 3, kind: "statement_row", status: "proposed", date: "2026-05-31",
    amount: "-5900.00", narration: "NEFT/QA18 BILLWISE STEEL", bank_ledger: "QA18 Bank Current",
    counter_ledger: "QA18 Billwise Steel", bills: [{ type: "Agst Ref", name: "QA18/BW/102", amount_cents: 590000 }] });
  assert.deepEqual(paid, { title: "NEFT/QA18 BILLWISE STEEL",
    detail: "2026-05-31 · paid to QA18 Billwise Steel · QA18 Bank Current · Agst Ref QA18/BW/102 5,900.00",
    amount: "-5,900.00" });
  const received = recordLine({ id: "r", version: 1, kind: "statement_row", status: "proposed", amount: "118000.00",
    counter_ledger: "Customer A", narration: "RTGS CUSTOMER A" });
  assert.equal(received.detail, "from Customer A");
  assert.equal(settles([{ type: "On Account", amount_cents: 50000 }]), "500.00 on account");
});

test("a run's counts come in the order a reviewer acts on them, and a finished run settles", () => {
  assert.deepEqual(recordCounts({ saved: 4, held: 1, proposed: 2, pending: 0 }),
    ["1 needs a decision", "2 ready to approve", "4 saved in Tally"]);
  assert.deepEqual(recordCounts({ held: 3 }), ["3 need a decision"]);
  const status = (state: string, control_state = "active") => ({ run: { id: "r", task_id: "t", workflow_key: "bill-entry",
    state, control_state }, items: {}, records: {}, blockers: [], activity: null });
  assert.deepEqual([settled(status("review")), settled(status("completed")), settled(status("review", "stopped"))],
    [false, true, true]);
});
