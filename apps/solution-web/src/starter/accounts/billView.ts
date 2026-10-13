import type { BillRecord, BillResult } from "./types";

/** One-click bill decisions. The server re-checks every eligibility rule. */
export type BillAction = "guess" | "supplier" | "nothing" | "retry" | "retry_save";

const SETTLED = ["saved", "duplicate", "rejected", "writing"];

export const isPending = (record: BillRecord) => !SETTLED.includes(record.status ?? "");

export const isUnresolved = (record: BillRecord, result: BillResult | null) =>
  Boolean(result?.unresolved?.some((i) => i.source_file_id === record.source_file_id));

export const needsAttention = (record: BillRecord, result: BillResult | null) =>
  record.findings.length > 0 || isUnresolved(record, result);

export const missingSupplier = (record: BillRecord) =>
  (!record.master_refs || record.master_refs.vendor?.new_supplier === true) &&
  record.findings.some((f) => f.includes("missing from the confirmed Tally ledgers"));

export function billActions(record: BillRecord, result: BillResult | null): BillAction[] {
  if (!isPending(record)) return [];
  // A destination refusal is fixed in the original system; the same approved
  // plan is then retried. Reinterpreting it as a best guess would add review.
  if (record.save_hold) return ["retry_save", "nothing"];
  const write: BillAction[] = missingSupplier(record) ? (record.data.tax === 0 ? ["supplier"] : []) : ["guess"];
  return [...write, "nothing", ...(isUnresolved(record, result) ? ["retry" as const] : [])];
}

/** Inputs with no proposal: awaiting a decision, or deferred to manual handling. */
export function inputsWithoutProposal(result: BillResult | null) {
  const records = result?.records ?? [];
  const proposed = (id: string) => records.some((r) => r.source_file_id === id);
  return {
    unresolved: (result?.unresolved ?? []).filter((i) => !proposed(i.source_file_id)),
    deferred: (result?.deferred ?? []).filter((i) => !proposed(i.source_file_id)),
  };
}
