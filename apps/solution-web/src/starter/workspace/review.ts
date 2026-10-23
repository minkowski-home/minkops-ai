/** A run's records as a reviewer reads them: one line per bill or statement row, with its holds and actions.

The server owns every field and action: each workflow's handler summarizes its
records, and a record offers only the one-click decisions its holds allow. This
module only words them. */

export interface Hold { code: string; label: string; reason: string }
/** A decision the server offers; `detail` travels back with it, such as which settlement was chosen. */
export interface RecordAction { action: string; label: string; detail?: Record<string, unknown> }
export interface BillReference { type: string; name?: string; amount_cents: number }

export interface RecordSummary {
  id: string;
  version: number;
  kind: string;
  status: string;
  file?: string;
  bill?: number;
  supplier?: string;
  number?: string;
  date?: string;
  total?: number | string;
  company?: string;
  voucher_type?: string;
  sheet?: string;
  row?: number;
  amount?: string;
  narration?: string;
  bank_ledger?: string;
  counter_ledger?: string;
  bills?: BillReference[];
  holds?: Hold[];
  review?: string[];
  actions?: RecordAction[];
}

export interface RecordPage { records: RecordSummary[]; next: string | null }

export interface RunStatus {
  run: { id: string; task_id: string; workflow_key: string; state: string; control_state: string };
  items: Record<string, number>;
  records: Record<string, number>;
  blockers: { kind: string; ref: string; items: number }[];
  activity: string | null;
}

export const RECORD_STATUS: Record<string, string> = {
  pending: "Being read", proposed: "Ready to approve", held: "Needs a decision", approved: "Approved",
  writing: "Saving", saved: "Saved in Tally", duplicate: "Already in Tally", deferred: "Left as is",
};

/** What a decision's receipt means for the record, said once it is applied. */
export const OUTCOME: Record<string, string> = {
  writing: "Approved. Saving it in Tally.", approved: "Approved.", deferred: "Left as is.",
  pending: "Reading it again.", held: "Still needs a decision.", proposed: "Ready to approve.",
  saved: "Saved in Tally.", duplicate: "Already in Tally.",
};

/** Money in rupees with two decimals, grouped as Indian accounts are. */
export function rupees(value: number | string): string {
  const amount = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(amount)) return String(value);
  return amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** The bills a statement row settles, as a reviewer reads them. */
export function settles(bills: BillReference[] = []): string {
  return bills.map((bill) => bill.type === "On Account" ? `${rupees(bill.amount_cents / 100)} on account`
    : `${bill.type} ${bill.name} ${rupees(bill.amount_cents / 100)}`).join(", ");
}

/** The record in one line: what it is, its particulars, and its amount. */
export function recordLine(record: RecordSummary): { title: string; detail: string; amount: string | null } {
  if (record.kind === "bill") {
    return {
      title: record.supplier ?? `Bill ${record.bill ?? 1} of ${record.file ?? "this file"}`,
      detail: [record.number && `No. ${record.number}`, record.date, record.company, record.voucher_type]
        .filter(Boolean).join(" · ") || (record.file ?? ""),
      amount: record.total == null ? null : rupees(record.total),
    };
  }
  if (record.kind === "statement_sheet") {
    return { title: record.sheet ? `${record.file} · ${record.sheet}` : record.file ?? "Statement", detail: "Statement sheet",
      amount: null };
  }
  const amount = Number(record.amount);
  const counter = record.counter_ledger && (amount < 0 ? `paid to ${record.counter_ledger}` : `from ${record.counter_ledger}`);
  return {
    title: record.narration ?? `Row ${record.row ?? ""} of ${record.file ?? "the statement"}`,
    detail: [record.date, counter, record.bank_ledger, record.bills?.length && settles(record.bills)]
      .filter(Boolean).join(" · "),
    amount: record.amount == null ? null : rupees(record.amount),
  };
}

/** Each status as a count says it, one and many, in the order a reviewer acts on them. */
const COUNTED: [string, string, string][] = [
  ["held", "needs a decision", "need a decision"], ["proposed", "ready to approve", "ready to approve"],
  ["pending", "being read", "being read"], ["approved", "approved", "approved"], ["writing", "saving", "saving"],
  ["saved", "saved in Tally", "saved in Tally"], ["duplicate", "already in Tally", "already in Tally"],
  ["deferred", "left as is", "left as is"],
];

/** The run's records by status, as short counts. */
export function recordCounts(records: Record<string, number>): string[] {
  return COUNTED.filter(([status]) => records[status])
    .map(([status, one, many]) => `${records[status]} ${records[status] === 1 ? one : many}`);
}

/** Whether nothing more will change without a person: a finished run, or one stopped. */
export function settled(status: RunStatus | undefined): boolean {
  return Boolean(status && (["completed", "failed"].includes(status.run.state) || status.run.control_state === "stopped"));
}
