import { useEffect, useState } from "react";
import { api } from "../api";
import { LoadingIndicator, RetryMessage } from "../components/Feedback";
import { useRead } from "../useRead";
import { rupees } from "./review";

/** Choose and approve: the entry as it will be written, with a ledger the person chooses for each of its parts.

The server sends what it may be (`choice` in the record's detail) and lists the ledgers each part may take,
the ones its session weighed first. Amounts are the source's own and are never edited here; the server checks
the choice with every gate a proposal meets, and a refusal says why. */

export interface Named { guid: string; name: string }
interface Ledger extends Named { group?: string; gstin?: string; suggested?: boolean }
interface Line { role: string; side: string; amount: number; ledger: Named | null; picker: string }
interface Item { item: string | null; amount: number; ledger: Named | null }
export interface Choice {
  company: string;
  voucher_types: Named[];
  voucher_type?: string | null;
  candidates: Named[];
  // A bill: its supplier and each line and item; a statement row: its bank and other side.
  supplier?: string | null;
  party?: Named | null;
  lines?: Line[];
  items?: Item[];
  amount?: string;
  payee?: string | null;
  bank_ledger?: Named | null;
  counter_ledger?: Named | null;
}

export const ROLES: Record<string, string> = {
  expense: "Expense", tax: "Tax", round_off: "Round-off", freight: "Freight", other_charge: "Other charge",
  discount: "Discount", tds: "TDS", retention: "Retention", deposit: "Deposit",
};

export function ChooseAndApprove({ scope, recordPath, pending, onApprove }: {
  scope: string; recordPath: string; pending: boolean; onApprove: (detail: Record<string, unknown>) => void;
}) {
  const { data, error, loading, refresh } = useRead<{ choice?: Choice }>(scope, recordPath);
  if (loading) return <LoadingIndicator>Loading what this entry may be…</LoadingIndicator>;
  if (!data?.choice) return error ? <RetryMessage onRetry={() => void refresh()}>Could not load the choices.</RetryMessage>
    : <p className="form-message">This entry's treatment cannot be chosen now.</p>;
  return <ChoiceForm key={recordPath} choice={data.choice} ledgersPath={`${recordPath}/ledgers`} pending={pending}
    onApprove={onApprove} />;
}

function ChoiceForm({ choice, ledgersPath, pending, onApprove }: {
  choice: Choice; ledgersPath: string; pending: boolean; onApprove: (detail: Record<string, unknown>) => void;
}) {
  const bill = Array.isArray(choice.lines);
  const [type, setType] = useState(choice.voucher_type ?? "");
  const [party, setParty] = useState(choice.party ?? null);
  const [lines, setLines] = useState((choice.lines ?? []).map((line) => line.ledger));
  const [items, setItems] = useState((choice.items ?? []).map((item) => item.ledger));
  const [bank, setBank] = useState(choice.bank_ledger ?? null);
  const [counter, setCounter] = useState(choice.counter_ledger ?? null);
  const complete = Boolean(type) && (bill ? Boolean(party) && lines.every(Boolean) && items.every(Boolean)
    : Boolean(bank) && Boolean(counter));
  const replace = <T,>(list: T[], at: number, value: T) => list.map((old, n) => n === at ? value : old);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!complete || pending) return;
    onApprove(bill ? { voucher_type: type, party: party?.guid, lines: lines.map((l) => l?.guid),
      ...(items.length ? { items: items.map((i) => i?.guid) } : {}) }
      : { voucher_type: type, bank_ledger: bank?.guid, counter_ledger: counter?.guid });
  }

  return <form className="choose-form" aria-label="Choose and approve" onSubmit={submit}>
    <p>Choose where this entry goes in {choice.company}. The amounts are the {bill ? "bill's" : "statement's"} own.
      {choice.candidates.length > 0 && ` Minkops weighed ${choice.candidates.map((c) => c.name).join(" and ")}; they are listed first.`}</p>
    <div className="accounts-field-grid">
      <label>Voucher type
        <select value={type} onChange={(event) => setType(event.target.value)} required>
          <option value="" disabled>Choose a voucher type</option>
          {choice.voucher_types.map((t) => <option key={t.guid} value={t.guid}>{t.name}</option>)}
        </select>
      </label>
      {bill ? <LedgerPicker label={`Supplier${choice.supplier ? ` (prints ${choice.supplier})` : ""}`} path={ledgersPath}
        kind="supplier" value={party} onChange={setParty} />
        : <>
          <LedgerPicker label="Bank ledger" path={ledgersPath} kind="bank" value={bank} onChange={setBank} />
          <LedgerPicker label={`Other side${choice.payee ? ` (narration names ${choice.payee})` : ""}`} path={ledgersPath}
            kind="any" value={counter} onChange={setCounter} />
        </>}
    </div>
    {bill && <div className="choose-lines">
      {(choice.lines ?? []).map((line, n) => <LedgerPicker key={`line-${n}`} path={ledgersPath} kind={line.picker}
        label={`${ROLES[line.role] ?? line.role} ${rupees(line.amount)} ${line.side === "credit" ? "Cr" : "Dr"}`}
        value={lines[n]} onChange={(ledger) => setLines((old) => replace(old, n, ledger))} />)}
      {(choice.items ?? []).map((item, n) => <LedgerPicker key={`item-${n}`} path={ledgersPath} kind="expense"
        label={`${item.item ?? "Item"} ${rupees(item.amount)}, purchase ledger`} value={items[n]}
        onChange={(ledger) => setItems((old) => replace(old, n, ledger))} />)}
    </div>}
    {!bill && choice.amount && <p>Amount {rupees(choice.amount)}, as the statement prints it.</p>}
    <button className="button button-primary" type="submit" disabled={!complete || pending}>
      {pending ? "Confirming…" : "Approve with these ledgers"}</button>
  </form>;
}

/** One part's ledger: the current choice, the ones the session weighed, and what a search finds, of this kind
(the role the server lists ledgers for: supplier, expense, tax, bank or any). */
export function LedgerPicker({ label, path, kind, value, onChange }: {
  label: string; path: string; kind: string; value: Named | null; onChange: (ledger: Named | null) => void;
}) {
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Ledger[]>([]);
  const [problem, setProblem] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api<{ ledgers: Ledger[] }>(`${path}?role=${encodeURIComponent(kind)}&q=${encodeURIComponent(query)}`,
        { signal: controller.signal })
        .then((answer) => { setFound(answer.ledgers); setProblem(""); })
        .catch((caught) => { if (!controller.signal.aborted) setProblem(caught instanceof Error ? caught.message : "Could not search."); });
    }, query ? 250 : 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [path, kind, query]);
  const options = value && !found.some((ledger) => ledger.guid === value.guid) ? [value, ...found] : found;
  return <div className="choose-picker">
    <label>{label}
      <select value={value?.guid ?? ""} onChange={(event) => onChange(options.find((l) => l.guid === event.target.value) ?? null)}>
        <option value="" disabled>Choose a ledger</option>
        {options.map((ledger) => <option key={ledger.guid} value={ledger.guid}>
          {ledger.name}{"group" in ledger && ledger.group ? ` · ${ledger.group}` : ""}{"suggested" in ledger && ledger.suggested ? " · suggested" : ""}
        </option>)}
      </select>
    </label>
    <input type="search" aria-label={`Search ledgers for ${label}`} placeholder="Search ledgers" value={query}
      onChange={(event) => setQuery(event.target.value)} />
    {problem && <p className="form-message">{problem}</p>}
  </div>;
}
