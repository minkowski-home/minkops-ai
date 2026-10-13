import test from "node:test";
import assert from "node:assert/strict";
import { inputsWithoutProposal } from "../src/starter/accounts/billView.ts";
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
