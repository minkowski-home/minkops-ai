import { useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../contexts/AuthContext";
import { LoadingIndicator, RetryMessage, Spinner } from "../components/Feedback";
import { useRead } from "../useRead";

interface Entry {
  id: string;
  kind: string;
  subject: string;
  value: Record<string, unknown>;
  status: string;
  uses: number;
  company: string | null;
  evidence: { kind?: string }[];
}
interface Rule {
  id: string;
  version: number;
  text: string;
  status: string;
  workflow: string | null;
  company: string | null;
  company_id: string | null;
}
interface MemoryPage { can_edit: boolean; entries: Entry[]; rules: Rule[] }
interface Named { id: string; slug?: string; name: string }

const STATUS: Record<string, string> = {
  confirmed: "Confirmed", demoted: "Changed in Tally since", disabled: "Disabled",
};
const WORKFLOWS: Record<string, string> = { "bill-entry": "Bill entry", "statement-entry": "Statement entry" };
const KINDS: Record<string, string> = {
  booking: "How the supplier's bills are booked", routing: "How the payee's bank rows are booked",
  practice: "How the books are kept",
};

const words = (key: string) => key.replace(/_/g, " ").replace(/^./, (first) => first.toUpperCase());

/** An entry's value as plain key-values, the way the employee reads it. */
function describe(value: Record<string, unknown>) {
  return Object.entries(value)
    .map(([key, item]) => `${words(key)}: ${Array.isArray(item) ? item.join(", ") : item ?? "none"}`)
    .join(" · ");
}

function source(entry: Entry) {
  if (entry.evidence.some((item) => item.kind === "answer")) return "answered by a person";
  const approved = entry.evidence.filter((item) => item.kind === "outcome").length;
  const saves = entry.kind === "routing" ? ["an approved row", "approved rows"] : ["an approved bill", "approved bills"];
  return approved ? `learnt from ${approved === 1 ? saves[0] : `${approved} ${saves[1]}`}` : "settled by the books";
}

/** A client's memory for the Accounts desk. Every member who can reach the client reads it; admins change it. */
export function MemoryScreen({ tenant }: { tenant: string }) {
  const { user } = useAuth();
  const scope = `${user?.id ?? ""}:${tenant}`;
  const { data: clients = [], loading: loadingClients } = useRead<Named[]>(scope, `/api/tenants/${tenant}/clients`);
  const [chosen, setChosen] = useState("");
  const client = chosen || clients[0]?.slug || "";
  const base = `/api/tenants/${tenant}/clients/${client}/memory`;
  const { data: page, error, loading, refresh } = useRead<MemoryPage>(scope, base, { enabled: Boolean(client) });
  const { data: companies = [] } = useRead<Named[]>(scope, `/api/tenants/${tenant}/clients/${client}/companies`,
    { enabled: Boolean(client) });
  const [draft, setDraft] = useState({ text: "", workflow: "", company: "" });
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  async function change(key: string, path: string, method: string, body?: object, done = "Saved.") {
    if (!user || busy) return false;
    setBusy(key);
    setNotice("");
    try {
      await api(base + path, { method, ...(body ? { body: JSON.stringify(body) } : {}) }, user.csrf_token);
      setNotice(done);
      await refresh();
      return true;
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : "Could not save this change.");
      return false;
    } finally { setBusy(""); }
  }
  async function add(event: FormEvent) {
    event.preventDefault();
    if (await change("add", "/rules", "POST", { text: draft.text, workflow_key: draft.workflow || null,
      company_id: draft.company || null }, "Rule added.")) setDraft({ text: "", workflow: "", company: "" });
  }
  async function save(event: FormEvent, rule: Rule) {
    event.preventDefault();
    if (editing && await change(rule.id, `/rules/${rule.id}`, "PUT", { text: editing.text,
      workflow_key: rule.workflow, company_id: rule.company_id }, "Rule updated.")) setEditing(null);
  }
  const working = (key: string) => busy === key && <Spinner />;

  return <section className="route-screen">
    <header className="route-heading"><div><h2>Memory</h2>
      <p>What the Accounts desk learnt about a client's books, and the rules people wrote for its work.</p></div>
    </header>
    {clients.length > 1 && <label className="config-field">Client business
      <select aria-label="Client business" value={client} onChange={(event) => setChosen(event.target.value)}>
        {clients.map((item) => <option key={item.slug} value={item.slug}>{item.name}</option>)}
      </select></label>}
    {!client && !loadingClients && <p className="quiet-state">No client businesses yet.</p>}
    {loading && <LoadingIndicator>Loading memory…</LoadingIndicator>}
    {error && <RetryMessage onRetry={() => void refresh()}>Could not load this client's memory.</RetryMessage>}
    {notice && <p role="status" className="form-message">{notice}</p>}
    {page && <>
      <section className="related-panel"><h3>Learnt from the books</h3>
        {page.entries.length ? page.entries.map((entry) => <article className="accounts-item" key={entry.id}>
          <strong>{entry.kind === "practice" ? words(entry.subject) : entry.subject}</strong>
          <span> · {KINDS[entry.kind] ?? words(entry.kind)}
            {entry.company ? ` · ${entry.company}` : ""}</span>
          <p>{describe(entry.value)}</p>
          <small>{STATUS[entry.status] ?? entry.status} · {source(entry)}
            {entry.uses ? ` · used ${entry.uses} ${entry.uses === 1 ? "time" : "times"}` : ""}</small>
          {page.can_edit && <div className="accounts-toolbar">
            <button className="button button-ghost" disabled={Boolean(busy)} onClick={() => void change(entry.id,
              `/entries/${entry.id}`, "PATCH", { status: entry.status === "disabled" ? "confirmed" : "disabled" })}>
              {working(entry.id)}{entry.status === "disabled" ? "Enable" : "Disable"}</button>
            <button className="button button-ghost" disabled={Boolean(busy)} onClick={() => void change(`${entry.id}:delete`,
              `/entries/${entry.id}`, "PATCH", { status: "retired" }, "Deleted.")}>
              {working(`${entry.id}:delete`)}Delete</button>
          </div>}
        </article>) : <p className="quiet-state">Nothing learnt yet. Entries appear as bills are approved and saved, and
          as the books settle how they are kept.</p>}
      </section>
      <section className="related-panel"><h3>Rules</h3>
        {page.rules.map((rule) => <article className="accounts-item" key={rule.id}>
          {editing?.id === rule.id
            ? <form onSubmit={(event) => void save(event, rule)}>
              <label className="config-field">Rule<textarea required maxLength={2000} value={editing.text}
                onChange={(event) => setEditing({ id: rule.id, text: event.target.value })} /></label>
              <div className="accounts-toolbar">
                <button className="button button-primary" disabled={Boolean(busy)}>{working(rule.id)}Save</button>
                <button type="button" className="button button-ghost" onClick={() => setEditing(null)}>Cancel</button>
              </div>
            </form>
            : <p>{rule.text}</p>}
          <small>{rule.workflow ? WORKFLOWS[rule.workflow] ?? rule.workflow : "Every workflow"}
            {rule.company ? ` · ${rule.company}` : ""} · version {rule.version}
            {rule.status === "disabled" ? " · Disabled" : ""}</small>
          {page.can_edit && editing?.id !== rule.id && <div className="accounts-toolbar">
            <button className="button button-ghost" disabled={Boolean(busy)}
              onClick={() => setEditing({ id: rule.id, text: rule.text })}>Edit</button>
            <button className="button button-ghost" disabled={Boolean(busy)} onClick={() => void change(`${rule.id}:status`,
              `/rules/${rule.id}`, "PATCH", { status: rule.status === "disabled" ? "active" : "disabled" })}>
              {working(`${rule.id}:status`)}{rule.status === "disabled" ? "Enable" : "Disable"}</button>
            <button className="button button-ghost" disabled={Boolean(busy)} onClick={() => void change(`${rule.id}:delete`,
              `/rules/${rule.id}`, "DELETE", undefined, "Rule deleted.")}>{working(`${rule.id}:delete`)}Delete</button>
          </div>}
        </article>)}
        {!page.rules.length && <p className="quiet-state">No rules yet.</p>}
        {page.can_edit && <form className="config-panel" onSubmit={(event) => void add(event)}><h4>Add a rule</h4>
          <label className="config-field">Rule<textarea required maxLength={2000} value={draft.text}
            onChange={(event) => setDraft({ ...draft, text: event.target.value })} /></label>
          <label className="config-field">Workflow<select aria-label="Workflow" value={draft.workflow}
            onChange={(event) => setDraft({ ...draft, workflow: event.target.value })}>
            <option value="">Every workflow</option>
            {Object.entries(WORKFLOWS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select></label>
          <label className="config-field">Company<select aria-label="Company" value={draft.company}
            onChange={(event) => setDraft({ ...draft, company: event.target.value })}>
            <option value="">Every company</option>
            {companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}
          </select></label>
          <button className="button button-primary" disabled={Boolean(busy)}>{working("add")}Add rule</button>
        </form>}
      </section>
    </>}
  </section>;
}
