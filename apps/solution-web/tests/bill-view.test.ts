import test from "node:test";
import assert from "node:assert/strict";
import { billActions, billOutcome, inputsWithoutProposal } from "../src/starter/accounts/billView.ts";
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

test("bill decisions come only from the server and settled records have no buttons", () => {
  assert.deepEqual(billActions(record("held", { status: "held", allowed_actions: ["retry_save", "nothing"] })), ["retry_save", "nothing"]);
  assert.deepEqual(billActions(record("unclear", { allowed_actions: ["nothing", "retry"] })), ["nothing", "retry"]);
  assert.deepEqual(billActions(record("new", { allowed_actions: ["supplier", "nothing"] })), ["supplier", "nothing"]);
  assert.deepEqual(billActions(record("no-policy", { findings: ["Unclear handwriting"] })), []);
  assert.deepEqual(billActions(record("saved", { status: "saved", allowed_actions: ["guess"] })), []);
});

import { billDetails } from "../src/starter/accounts/billView.ts";
const tallyConfig = (extra = {}) => ({
  tally_target: {
    company_mode: "locked", locked_company_guid: "b",
    companies: [
      { company: "Sachin Infra (2025-26)", references: { company_guid: "a" }, voucher_type: { NAME: "Purchase" } },
      { company: "Sachin Infra (2026-27)", references: { company_guid: "b" }, voucher_type: { NAME: "Purchase GST" } },
    ],
    ...extra,
  },
});
const proposal = (extra: Partial<BillRecord> = {}) => record("bill", {
  data: { vendor: "Ultratech Cement", invoice_number: "UC-104", date: "2026-10-01", purchase_ledger: "Cement Purchases",
    subtotal: 100000, tax: 18000, tax_ledger: null, total: 118000 },
  tax_allocations: [{ ref: "r1", ledger: "CGST 9%", amount: 9000, evidence: "" }, { ref: "r2", ledger: "SGST 9%", amount: 9000, evidence: "" }],
  ...extra,
});

test("details show exactly what will be entered in Tally", () => {
  const details = billDetails(proposal(), tallyConfig());
  assert.equal(details.title, "Will be entered in Tally");
  assert.deepEqual(details.rows, [
    ["Company", "Sachin Infra (2026-27)"],
    ["Voucher type", "Purchase GST"],
    ["Date", "1 Oct 2026"],
    ["Supplier ledger", "Ultratech Cement"],
    ["Invoice number", "UC-104"],
    ["Cement Purchases", "1,00,000.00"],
    ["CGST 9%", "9,000.00"],
    ["SGST 9%", "9,000.00"],
    ["Total", "1,18,000.00"],
  ]);
});

test("details name the outcome and the routed company for inferred runs", () => {
  const inferred = tallyConfig({ company_mode: "infer", locked_company_guid: null });
  assert.equal(billDetails(proposal({ company_guid: "a" }), inferred).rows[0][1], "Sachin Infra (2025-26)");
  assert.equal(billDetails(proposal({ status: "saved" }), tallyConfig()).title, "Saved in Tally");
  assert.equal(billDetails(proposal({ status: "duplicate" }), tallyConfig()).title, "Already in Tally");
  assert.equal(billDetails(proposal({ operation: "update" }), tallyConfig()).title, "Corrects an existing Tally voucher");
  const single = proposal({ tax_allocations: undefined, data: { ...proposal().data, tax_ledger: "Input GST" } });
  assert.deepEqual(billDetails(single, tallyConfig()).rows.slice(6, 7), [["Input GST", "18,000.00"]]);
  const older = { tally_target: { company: "Test" } };
  assert.equal(billDetails(proposal(), older).rows[1][1], "Purchase", "runs before voucher-type choice wrote Purchase");
});

test("voucher previews list every proposed line with its side, whatever the voucher family", () => {
  const preview = { company: "Sachin Infra (2026-27)", voucher_type: "Debit Note", family: "debit_note", date: "2026-10-14",
    number: "CN-7", party: "Ultratech Cement", total: 1180.4,
    lines: [{ ledger: "Ultratech Cement", side: "debit" as const, amount: 1180.4 },
      { ledger: "Purchase Returns 18%", side: "credit" as const, amount: 1000 },
      { ledger: "Input IGST 18%", side: "credit" as const, amount: 180 },
      { ledger: "Round Off", side: "credit" as const, amount: 0.4 }] };
  const details = billDetails(record("note", { preview, data: {} }), tallyConfig());
  assert.deepEqual(details.rows, [
    ["Company", "Sachin Infra (2026-27)"], ["Voucher type", "Debit Note"], ["Date", "14 Oct 2026"],
    ["Supplier ledger", "Ultratech Cement"], ["Invoice number", "CN-7"],
    ["Purchase Returns 18%", "1,000.00 Cr"], ["Input IGST 18%", "180.00 Cr"], ["Round Off", "0.40 Cr"],
    ["Total", "1,180.40"],
  ]);
});

test("write outcomes take precedence over findings and retain attention", () => {
  assert.equal(billOutcome('saved', true), 'Saved and verified · check Attention');
  assert.equal(billOutcome('saved', false), 'Saved and verified');
  assert.equal(billOutcome('duplicate', true), 'Duplicate skipped · check Attention');
  assert.equal(billOutcome('writing', true), 'Saving and checking');
  assert.equal(billOutcome('held', true), 'Needs attention');
});
