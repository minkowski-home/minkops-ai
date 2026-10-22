import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useAuth } from "../contexts/AuthContext";
import { LoadingIndicator, RetryMessage, Spinner } from "../components/Feedback";
import { reads } from "../readCache";
import { useRead } from "../useRead";
import { OUTCOME, RECORD_STATUS, recordCounts, recordLine, rupees, settled, settles, type BillReference,
  type RecordAction, type RecordPage, type RecordSummary, type RunStatus } from "./review";

const PAGE = 100;

interface Line { ledger: string; side?: string; amount?: number; amount_cents?: number }
interface Item { item: string; quantity: string; unit: string; rate: string; amount: number; ledger: string; godowns: string[] }
interface RecordDetails extends RecordSummary {
  facts?: Record<string, unknown> & { einvoice?: { status: string; signer: string | null; irn: string; page: number } };
  preview?: { lines: Line[]; items?: Item[]; party?: string; voucher_type?: string };
  lines?: Line[] | null;
  evidence?: { field: string; page: number; quote: string }[] | string | null;
  rules?: { id: string; version: number; text: string }[] | null;
  current?: { voucher_type?: string; date?: string; master_id?: string } | null;
  new_supplier?: Record<string, unknown>;
  exception?: { code: string; detail: string } | null;
}

const actionKey = (record: RecordSummary, choice: RecordAction) =>
  `${record.id}:${choice.action}:${JSON.stringify(choice.detail ?? {})}`;

/** One review surface for every workflow's run: what each record is, why it waits, and the decisions it allows. */
export function RunReview({ tenant, client, run }: { tenant: string; client: string; run: string }) {
  const { user } = useAuth();
  const scope = `${user?.id ?? ""}:${tenant}`;
  const base = `/api/tenants/${encodeURIComponent(tenant)}/clients/${encodeURIComponent(client)}`;
  const runPath = `${base}/runs/${run}`;
  const { data: status } = useRead<RunStatus>(scope, `${runPath}/status`, { interval: (s) => (settled(s) ? 0 : 3000) });
  const [cursors, setCursors] = useState<string[]>([]);
  const after = cursors.at(-1);
  const { data: page, error, loading, refresh } = useRead<RecordPage>(scope,
    `${runPath}/records?limit=${PAGE}${after ? `&after=${encodeURIComponent(after)}` : ""}`);
  const [pending, setPending] = useState("");
  const [notice, setNotice] = useState("");
  const [open, setOpen] = useState("");
  // The entries shown move with the run's activity: read them again whenever it changes.
  const seen = useRef<string | null | undefined>(undefined);
  const activity = status?.activity;
  useEffect(() => {
    if (seen.current !== undefined && activity !== seen.current)
      reads.invalidate(scope, (path) => path.startsWith(`${runPath}/records`) || path.startsWith(`${base}/records/`));
    seen.current = activity;
  }, [activity, scope, base, runPath]);

  // A receipt is authoritative; invalidating also fences reads that started before it.
  const settle = () => reads.invalidate(scope, (path) => path.startsWith(base)
    || path.startsWith(`/api/tenants/${tenant}/tasks/`));

  async function decide(record: RecordSummary, choice: RecordAction) {
    if (!user || pending) return;
    setPending(actionKey(record, choice));
    setNotice("");
    try {
      const receipt = await api<{ status: string }>(`${base}/records/${record.id}/decisions`, {
        method: "POST", body: JSON.stringify({ action: choice.action, version: record.version, detail: choice.detail ?? {} }),
      }, user.csrf_token);
      setNotice(OUTCOME[receipt.status] ?? "Decision recorded.");
    } catch (caught) {
      setNotice(`${caught instanceof Error ? caught.message : "Could not record this decision."} Showing the entry as it is now.`);
    } finally {
      setPending("");
      settle();
    }
  }

  async function saveReady() {
    if (!user || pending) return;
    setPending("ready");
    setNotice("");
    try {
      const { approved } = await api<{ approved: number }>(`${runPath}/approve`, { method: "POST" }, user.csrf_token);
      setNotice(approved ? `${approved} ${approved === 1 ? "entry" : "entries"} approved. Saving in Tally.`
        : "Every ready entry needs your review first: approve each one.");
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : "Could not approve the ready entries.");
    } finally {
      setPending("");
      settle();
    }
  }

  const counts = status ? recordCounts(status.records) : [];
  return <section className="run-review" aria-label="Review">
    <header className="review-heading">
      <div><h3>Review</h3><p>{counts.join(" · ") || "Nothing to review yet."}</p></div>
      {Boolean(status?.records.proposed) && <button className="button button-primary" disabled={Boolean(pending)}
        onClick={() => void saveReady()}>{pending === "ready" && <Spinner />}{pending === "ready" ? "Approving…" : "Save ready entries"}</button>}
    </header>
    {notice && <p role="status" className="form-message">{notice}</p>}
    {error && <RetryMessage onRetry={() => void refresh()}>Could not refresh this run's entries. Showing the last received
      results.</RetryMessage>}
    {loading && <LoadingIndicator>Loading entries…</LoadingIndicator>}
    {page && !page.records.length && <p className="quiet-state">No entries yet. They appear as the inputs are read.</p>}
    <ol className="review-list">
      {page?.records.map((record) => <RecordRow key={record.id} record={record} pending={pending}
        open={open === record.id} onToggle={() => setOpen(open === record.id ? "" : record.id)}
        detailPath={`${base}/records/${record.id}`} scope={scope} onDecide={(choice) => void decide(record, choice)} />)}
    </ol>
    {(cursors.length > 0 || page?.next) && <div className="accounts-toolbar review-pager">
      <button className="button button-ghost" disabled={!cursors.length} onClick={() => setCursors((c) => c.slice(0, -1))}>
        Previous</button>
      <button className="button button-ghost" disabled={!page?.next} onClick={() => page?.next && setCursors((c) =>
        [...c, page.next as string])}>Next</button>
    </div>}
  </section>;
}

function RecordRow({ record, pending, open, onToggle, detailPath, scope, onDecide }: {
  record: RecordSummary; pending: string; open: boolean; onToggle: () => void; detailPath: string; scope: string;
  onDecide: (choice: RecordAction) => void;
}) {
  const line = recordLine(record);
  return <li className={`review-row review-row--${record.status}`}>
    <div className="review-row__main">
      <div className="review-row__heading">
        <span className={`record-status record-status--${record.status}`}>{RECORD_STATUS[record.status] ?? record.status}</span>
        {record.holds?.map((hold) => <span key={hold.code} className="record-hold" title={hold.reason}>{hold.label}</span>)}
      </div>
      <h4>{line.title}</h4>
      {line.detail && <p className="review-row__detail">{line.detail}</p>}
      {record.review?.map((reason, n) => <p key={n} className="review-note">{reason}</p>)}
    </div>
    {line.amount && <span className="review-row__amount">{line.amount}</span>}
    <div className="review-row__actions">
      {record.actions?.map((choice) => {
        const key = actionKey(record, choice);
        return <button key={key} disabled={Boolean(pending)} onClick={() => onDecide(choice)}
          className={choice.action === "approve" ? "button button-primary" : "button button-ghost"}>
          {pending === key && <Spinner />}{pending === key ? "Confirming…" : choice.label}</button>;
      })}
      <button className="button button-ghost" aria-expanded={open} onClick={onToggle}>{open ? "Hide details" : "Details"}</button>
    </div>
    {open && <RecordDetail path={detailPath} scope={scope} />}
  </li>;
}

function RecordDetail({ path, scope }: { path: string; scope: string }) {
  const { data, error, loading, refresh } = useRead<RecordDetails>(scope, path);
  if (loading) return <LoadingIndicator>Loading details…</LoadingIndicator>;
  if (!data) return error ? <RetryMessage onRetry={() => void refresh()}>Could not load these details.</RetryMessage> : null;
  const lines = data.preview?.lines ?? data.lines ?? [];
  const evidence = data.evidence;
  return <div className="review-detail">
    {lines.length > 0 && <table className="review-lines"><caption>The entry Minkops proposes</caption><tbody>
      {lines.map((ln, n) => <tr key={n}><th scope="row">{ln.ledger}</th><td>{ln.side === "credit" ? "Cr" : ln.side ? "Dr" : ""}</td>
        <td>{rupees(ln.amount ?? (ln.amount_cents ?? 0) / 100)}</td></tr>)}
    </tbody></table>}
    {data.preview?.items && <table className="review-lines"><caption>Items</caption><tbody>
      {data.preview.items.map((item, n) => <tr key={n}><th scope="row">{item.item}</th>
        <td>{item.quantity} {item.unit} at {rupees(item.rate)}</td><td>{rupees(item.amount)}</td>
        <td>{item.godowns.join(", ")} · {item.ledger}</td></tr>)}
    </tbody></table>}
    {Boolean(data.bills?.length) && <p>Settles {settles(data.bills as BillReference[])}.</p>}
    {data.facts?.einvoice && <p>E-invoice {data.facts.einvoice.status}{data.facts.einvoice.signer
      ? ` by ${data.facts.einvoice.signer}` : ""}, IRN {data.facts.einvoice.irn}.</p>}
    {typeof evidence === "string" && <p className="review-evidence">{evidence}</p>}
    {Array.isArray(evidence) && evidence.length > 0 && <ul className="review-evidence">{evidence.map((item, n) =>
      <li key={n}>{item.field.replace(/_/g, " ")}: “{item.quote}” (page {item.page})</li>)}</ul>}
    {data.exception && <p className="review-evidence">{data.exception.detail}</p>}
    {data.rules?.map((rule) => <p key={rule.id} className="review-note">Follows the rule “{rule.text}” (version {rule.version}).</p>)}
    {data.new_supplier && <p>New supplier: {Object.entries(data.new_supplier).filter(([, value]) => value)
      .map(([key, value]) => `${key.replace(/_/g, " ")} ${Array.isArray(value) ? value.join(", ") : value}`).join(" · ")}</p>}
    {data.current && <p>In Tally: {[data.current.voucher_type, data.current.date, data.current.master_id
      && `voucher ${data.current.master_id}`].filter(Boolean).join(" · ")}.</p>}
  </div>;
}
