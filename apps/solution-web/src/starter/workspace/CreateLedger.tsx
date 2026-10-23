import { useState } from "react";
import { LoadingIndicator, RetryMessage } from "../components/Feedback";
import { useRead } from "../useRead";
import { LedgerPicker, ROLES, type Choice, type Named } from "./ChooseAndApprove";
import { rupees } from "./review";

/** Create this ledger: the new party ledger laid out as Tally's ledger creation, beside what the source prints, and
below it the entry to be made with it. The server fills the form from the source and the company's books, checks
what the person approves, and creates the ledger only once; the entry is made once Tally's readback matches. */

interface LedgerForm {
  name: string;
  under: string | null;
  groups: string[];
  billwise: boolean | null;
  credit_period: number | null;
  mailing: { address: string[]; state: string | null; country: string; pincode: string | null };
  gst: { registration_type: string; gstin: string | null };
}
interface NewLedger { form: LedgerForm; printed: Record<string, unknown> }

export function CreateLedger({ scope, recordPath, pending, onCreate }: {
  scope: string; recordPath: string; pending: boolean; onCreate: (detail: Record<string, unknown>) => void;
}) {
  const { data, error, loading, refresh } = useRead<{ new_ledger?: NewLedger; choice?: Choice }>(scope, recordPath);
  if (loading) return <LoadingIndicator>Loading the new ledger…</LoadingIndicator>;
  if (!data?.new_ledger || !data.choice) return error ? <RetryMessage onRetry={() => void refresh()}>Could not load the
    new ledger.</RetryMessage> : <p className="form-message">This ledger cannot be created now.</p>;
  return <LedgerFormView key={recordPath} start={data.new_ledger} choice={data.choice} ledgersPath={`${recordPath}/ledgers`}
    pending={pending} onCreate={onCreate} />;
}

function LedgerFormView({ start, choice, ledgersPath, pending, onCreate }: {
  start: NewLedger; choice: Choice; ledgersPath: string; pending: boolean;
  onCreate: (detail: Record<string, unknown>) => void;
}) {
  const bill = Array.isArray(choice.lines);
  const [ledger, setLedger] = useState(start.form);
  const [address, setAddress] = useState(start.form.mailing.address.join("\n"));
  const [type, setType] = useState(choice.voucher_type ?? "");
  const [lines, setLines] = useState((choice.lines ?? []).map((line) => line.ledger));
  const [items, setItems] = useState((choice.items ?? []).map((item) => item.ledger));
  const registered = ledger.gst.registration_type !== "Unregistered";
  const complete = Boolean(ledger.name.trim() && ledger.under && ledger.billwise !== null && type
    && (!registered || ledger.gst.gstin) && lines.every(Boolean) && items.every(Boolean));
  const set = (change: Partial<LedgerForm>) => setLedger((old) => ({ ...old, ...change }));
  const replace = <T,>(list: T[], at: number, value: T) => list.map((old, n) => n === at ? value : old);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!complete || pending) return;
    const lines_ = address.split("\n").map((line) => line.trim()).filter(Boolean);
    onCreate({
      ledger: { name: ledger.name.trim(), under: ledger.under, billwise: ledger.billwise,
        credit_period: ledger.billwise && ledger.credit_period ? ledger.credit_period : null,
        mailing: { ...ledger.mailing, address: lines_ },
        gst: registered ? ledger.gst : { registration_type: "Unregistered", gstin: null } },
      voucher_type: type,
      ...(bill ? { lines: lines.map((l) => l?.guid), ...(items.length ? { items: items.map((i) => i?.guid) } : {}) } : {}),
    });
  }

  const printed = Object.entries(start.printed).filter(([, value]) => value != null && value !== "")
    .map(([key, value]) => `${key.replace(/_/g, " ")}: ${Array.isArray(value) ? value.join(", ") : String(value)}`);
  return <form className="choose-form" aria-label="Create this ledger" onSubmit={submit}>
    <p>Create a ledger in {choice.company} as Tally will hold it. {bill ? "The bill prints" : "The narration prints"}
      {" "}{printed.join(" · ")}.</p>
    <div className="accounts-field-grid">
      <label>Name<input value={ledger.name} maxLength={200} onChange={(event) => set({ name: event.target.value })} /></label>
      <label>Under
        <select value={ledger.under ?? ""} onChange={(event) => set({ under: event.target.value || null })}>
          <option value="" disabled>Choose a group</option>
          {ledger.groups.map((group) => <option key={group} value={group}>{group}</option>)}
        </select>
      </label>
      <label>Maintain balances bill-by-bill
        <select value={ledger.billwise === null ? "" : ledger.billwise ? "yes" : "no"}
          onChange={(event) => set({ billwise: event.target.value === "yes" })}>
          <option value="" disabled>Choose</option><option value="yes">Yes</option><option value="no">No</option>
        </select>
      </label>
      {ledger.billwise && <label>Default credit period (days)
        <input type="number" min={0} max={365} value={ledger.credit_period ?? ""}
          onChange={(event) => set({ credit_period: event.target.value === "" ? null : Number(event.target.value) })} />
      </label>}
      <label>Address
        <textarea rows={3} value={address} onChange={(event) => setAddress(event.target.value)} /></label>
      <label>State<input value={ledger.mailing.state ?? ""} onChange={(event) => set({ mailing: {
        ...ledger.mailing, state: event.target.value || null } })} /></label>
      <label>PIN code<input value={ledger.mailing.pincode ?? ""} inputMode="numeric" maxLength={6}
        onChange={(event) => set({ mailing: { ...ledger.mailing, pincode: event.target.value || null } })} /></label>
      <label>GST registration type
        <select value={ledger.gst.registration_type} onChange={(event) => set({ gst: {
          ...ledger.gst, registration_type: event.target.value } })}>
          {["Regular", "Composition", "Unregistered"].map((kind) => <option key={kind} value={kind}>{kind}</option>)}
        </select>
      </label>
      {registered && <label>GSTIN<input value={ledger.gst.gstin ?? ""} maxLength={15}
        onChange={(event) => set({ gst: { ...ledger.gst, gstin: event.target.value.toUpperCase() || null } })} /></label>}
    </div>
    <p>{bill ? "The bill is then entered with it:" : "The entry is then made with it:"}</p>
    <div className="accounts-field-grid">
      <label>Voucher type
        <select value={type} onChange={(event) => setType(event.target.value)}>
          <option value="" disabled>Choose a voucher type</option>
          {choice.voucher_types.map((t) => <option key={t.guid} value={t.guid}>{t.name}</option>)}
        </select>
      </label>
    </div>
    {bill && <div className="choose-lines">
      {(choice.lines ?? []).map((line, n) => <LedgerPicker key={`line-${n}`} path={ledgersPath} kind={line.picker}
        label={`${ROLES[line.role] ?? line.role} ${rupees(line.amount)} ${line.side === "credit" ? "Cr" : "Dr"}`}
        value={lines[n]} onChange={(chosen: Named | null) => setLines((old) => replace(old, n, chosen))} />)}
      {(choice.items ?? []).map((item, n) => <LedgerPicker key={`item-${n}`} path={ledgersPath} kind="expense"
        label={`${item.item ?? "Item"} ${rupees(item.amount)}, purchase ledger`} value={items[n]}
        onChange={(chosen: Named | null) => setItems((old) => replace(old, n, chosen))} />)}
    </div>}
    <button className="button button-primary" type="submit" disabled={!complete || pending}>
      {pending ? "Confirming…" : "Create ledger and approve"}</button>
  </form>;
}
