import type { BillRecord, BillResult } from "./types";

/** One-click bill decisions. The server re-checks every eligibility rule. */
export type BillAction = "guess" | "supplier" | "nothing" | "retry" | "retry_save";

const SETTLED = ["saved", "duplicate", "rejected", "writing"];

export const isPending = (record: BillRecord) => !SETTLED.includes(record.status ?? "");

const isUnresolved = (record: BillRecord, result: BillResult | null) =>
  Boolean(result?.unresolved?.some((i) => i.source_file_id === record.source_file_id));

export const needsAttention = (record: BillRecord, result: BillResult | null) =>
  record.findings.length > 0 || isUnresolved(record, result);

/** A positively new supplier; older runs without codes are recognised by their message. */
export const missingSupplier = (record: BillRecord) =>
  (!record.master_refs || record.master_refs.vendor?.new_supplier === true) &&
  (Boolean(record.exception_codes?.includes("supplier_missing")) ||
    record.findings.some((f) => f.includes("missing from the confirmed Tally ledgers")));

export function billActions(record: BillRecord): BillAction[] {
  if (!isPending(record)) return [];
  // Missing policy fails closed during a rolling deployment; the next poll
  // supplies the authoritative server result. Accounting rules live there.
  return record.allowed_actions ?? [];
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

interface TallyCompanyTarget { company: string; references?: { company_guid?: string | null }; voucher_type?: { NAME: string }; voucher_type_error?: string }
interface TallyTarget { company?: string; company_mode?: string; locked_company_guid?: string | null; companies?: TallyCompanyTarget[]; voucher_type_version?: number }
export interface BillDetails { title: string; rows: [string, string][] }

const money = (value: unknown) => typeof value === "number"
  ? new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value) : String(value ?? "—");
const calendar = (value: unknown) => {
  const date = typeof value === "string" ? new Date(`${value}T00:00:00Z`) : null;
  return date && !Number.isNaN(+date)
    ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(date)
    : String(value ?? "—");
};

/** What one proposal enters in Tally: company, voucher type, ledgers and amounts. */
export function billDetails(record: BillRecord, config: Record<string, unknown>): BillDetails {
  const data = record.data;
  const target = config.tally_target as TallyTarget | undefined;
  const title = record.status === "saved" ? "Saved in Tally" : record.status === "duplicate" ? "Already in Tally"
    : record.operation === "update" ? "Corrects an existing Tally voucher" : "Will be entered in Tally";
  if (!target) return { title: record.status === "saved" ? "Saved" : "Will be entered",
    rows: Object.entries(data).filter(([, value]) => value != null).map(([key, value]) => [key, String(value)]) };
  const guid = target.company_mode === "locked" ? target.locked_company_guid : record.company_guid;
  const company = target.companies?.find((c) => c.references?.company_guid === guid);
  const taxes = record.tax_allocations?.length
    ? record.tax_allocations.map((line): [string, string] => [line.ledger ?? "Pending ledger", money(line.amount)])
    : data.tax ? [[String(data.tax_ledger ?? "Tax"), money(data.tax)] as [string, string]] : [];
  return {
    title,
    rows: [
      ["Company", company?.company ?? record.company_name ?? target.company ?? "—"],
      // Runs started before voucher types were chosen always wrote Purchase.
      ["Voucher type", company?.voucher_type?.NAME ?? (company?.voucher_type_error ? "Not chosen" : "Purchase")],
      ["Date", calendar(data.date)],
      ["Supplier ledger", String(data.vendor ?? "—")],
      ["Invoice number", String(data.invoice_number ?? "—")],
      [String(data.purchase_ledger ?? "Purchase ledger"), money(data.subtotal)],
      ...taxes,
      ["Total", money(data.total)],
    ],
  };
}
