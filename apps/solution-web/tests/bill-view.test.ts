import test from "node:test";
import assert from "node:assert/strict";
import { billActions, inputsWithoutProposal } from "../src/starter/accounts/billView.ts";
import type { BillRecord, BillResult } from "../src/starter/accounts/types.ts";

const record = (source_file_id: string, extra: Partial<BillRecord> = {}): BillRecord => ({
  source_file_id, destination_file_id: "discovery", sheet: "Purchase", operation: "append",
  data: { tax: 18 }, evidence: [], findings: [], ...extra,
});

test("inputs without a proposal stay visible as unresolved or deferred", () => {
  const result: BillResult = {
    records: [record("with-proposal", { status: "rejected" })],
    findings: [],
    unresolved: [{ source_file_id: "unreadable", reason: "Blank page" }],
    deferred: [{ source_file_id: "with-proposal" }, { source_file_id: "skipped" }],
  };
  assert.deepEqual(inputsWithoutProposal(result), {
    unresolved: [{ source_file_id: "unreadable", reason: "Blank page" }],
    deferred: [{ source_file_id: "skipped" }],
  });
  assert.deepEqual(inputsWithoutProposal(null), { unresolved: [], deferred: [] });
});

test("held saves offer Retry save instead of Best guess write", () => {
  const result: BillResult = { records: [], findings: [], unresolved: [{ source_file_id: "unclear", reason: "Unclear" }] };
  const newSupplier = { vendor: { ref: null, evidence: "No match.", new_supplier: true }, purchase_ledger: null, tax_ledger: null };
  const missing = ["Supplier 'New' is missing from the confirmed Tally ledgers. Add or map the supplier."];
  assert.deepEqual(billActions(record("rejected", { status: "held", save_hold: "Tally rejected the voucher date." }), result), ["retry_save", "nothing"]);
  assert.deepEqual(billActions(record("unclear", { findings: ["Unclear handwriting"] }), result), ["guess", "nothing", "retry"]);
  assert.deepEqual(billActions(record("new", { findings: missing, data: { tax: 0 }, master_refs: newSupplier }), result), ["supplier", "nothing"]);
  assert.deepEqual(billActions(record("taxed", { findings: missing, master_refs: newSupplier }), result), ["nothing"]);
  assert.deepEqual(billActions(record("saved", { status: "saved" }), result), []);
});
