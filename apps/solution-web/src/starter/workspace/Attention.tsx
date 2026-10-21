import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../contexts/AuthContext";
import { LoadingIndicator, RetryMessage, Spinner } from "../components/Feedback";
import { useRead } from "../useRead";
import { reads } from "../readCache";

interface Item {
  id: string;
  task_id: string;
  identifier: string;
  label: string;
  reason: string;
  status: string;
  kind?: string;
  /** A company's derived posting pattern awaiting one confirmation. */
  profile?: { company: string; summary: string[]; waiting: number };
  /** A new statement format: one date-order answer, or sample rows to confirm. */
  layout?: { prompt: string; actions: string[]; samples: { date: string; amount_cents: number; account: string; narration: string }[] };
  workflow: string;
  employee: string;
  updated_at: string;
}

/** Shared list across workflows. Detailed diagnostics stay in the audit store. */
export function Attention({ tenant, routeSlug }: { tenant: string; routeSlug: string }) {
  const { user } = useAuth();
  const [status, setStatus] = useState("pending");
  const [group, setGroup] = useState<"workflow" | "employee" | "status">("workflow");
  const [sort, setSort] = useState("newest"),
    [offset, setOffset] = useState(0);
  const [pending, setPending] = useState<Set<string>>(new Set());
  const base = `/api/tenants/${tenant}/attention`;
  const query = `?status=${status}&offset=${offset}&group=${group}&sort=${sort}`;
  const scope = `${user?.id ?? ""}:${tenant}`;
  const { data: items = [], error: loadError, loading, refresh, setData: setItems } = useRead<Item[]>(scope, base + query, { interval: 5000 });
  const { data: notice = "", setData: setNotice } = useRead<string>(scope, base + "#notice", { enabled: false });
  const busy = pending.size > 0;
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (id) document.getElementById(id)?.scrollIntoView({ block: "center" });
  }, [items]);
  const actionKey = (path: string, body?: Record<string, string>) => path + (body?.action ?? "");
  const itemBusy = (id: string) => [...pending].some(key => key.startsWith(`/${id}/`));
  async function action(path: string, body?: Record<string, string>, itemId?: string) {
    if (!user) return;
    const key = actionKey(path, body);
    if (pending.has(key)) return;
    setPending(current => new Set(current).add(key));
    setNotice("");
    try {
      const result = await api<{ queued?: number; status?: string }>(
        base + path,
        { method: "POST", ...(body ? { body: JSON.stringify(body) } : {}) },
        user.csrf_token
      );
      setNotice(
        result.queued !== undefined
          ? `${result.queued} check${result.queued === 1 ? "" : "s"} queued`
          : result.status === "active" ? "Confirmed; waiting work continues"
          : result.status ? "Left for manual handling" : "Marked done"
      );
      if (itemId && !path.endsWith("/refresh")) {
        setItems(current => status === "pending" ? (current ?? []).filter(item => item.id !== itemId)
          : (current ?? []).map(item => item.id === itemId ? { ...item, status: "done" } : item));
      }
      // A receipt is already authoritative. Refresh failures retain that result;
      // invalidation also fences polls started before the committed decision.
      reads.invalidate(scope, resource => !resource.endsWith("#notice"));
    } catch (caught) {
      let receipt: { action: string; status: string } | null = null;
      if (itemId && path.endsWith("/profile")) {
        try { receipt = await api(`${base}/${itemId}/decision`); } catch { /* An unreadable receipt remains uncertain. */ }
      }
      setNotice(receipt && receipt.action === body?.action
        ? receipt.status === "active" ? "Confirmed; waiting work continues" : "Decision recorded; left for manual handling"
        : `${caught instanceof Error ? caught.message : "Could not confirm this action."} The outcome is not yet confirmed. Refresh the current item before trying again.`);
      if (receipt && receipt.action === body?.action && itemId && status === "pending") setItems(current => (current ?? []).filter(item => item.id !== itemId));
      reads.invalidate(scope, resource => !resource.endsWith("#notice"));
    } finally {
      setPending(current => { const next = new Set(current); next.delete(key); return next; });
    }
  }
  const ordered = [...items].sort((a, b) =>
    sort === "name"
      ? a.identifier.localeCompare(b.identifier)
      : b.updated_at.localeCompare(a.updated_at)
  );
  const groups = [...new Set(ordered.map((i) => i[group] || "Other"))].sort();
  return (
    <section className="route-screen">
      <h2>Attention items</h2>
      {loading && <LoadingIndicator>Loading attention items…</LoadingIndicator>}
      {loadError && <RetryMessage onRetry={() => void refresh()}>Could not refresh attention items. Showing the last received results; retrying automatically.</RetryMessage>}
      <div className="accounts-toolbar">
        <button
          className="button button-ghost"
          disabled={busy}
          onClick={() => void action("/refresh")}
        >
          {pending.has("/refresh") && <Spinner />}{pending.has("/refresh") ? "Refreshing…" : "Refresh pending items"}
        </button>
        <label className="config-field">
          Status
          <select
            aria-label="Status"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
          >
            <option value="pending">Pending</option>
            <option value="done">Done</option>
            <option value="all">All</option>
          </select>
        </label>
        <label className="config-field">
          Group by
          <select
            aria-label="Group by"
            value={group}
            onChange={(e) => {
              setGroup(e.target.value as typeof group);
              setOffset(0);
            }}
          >
            {["workflow", "employee", "status"].map((v) => (
              <option key={v} value={v}>
                {v[0].toUpperCase() + v.slice(1)}
              </option>
            ))}
          </select>
        </label>
        <label className="config-field">
          Sort
          <select
            aria-label="Sort"
            value={sort}
            onChange={(e) => {
              setSort(e.target.value);
              setOffset(0);
            }}
          >
            <option value="newest">Newest</option>
            <option value="name">Name</option>
          </select>
        </label>
      </div>
      {notice && <p role="status">{notice}</p>}
      {groups.map((g) => (
        <section key={g}>
          <h3>{g}</h3>
          {ordered
            .filter((i) => (i[group] || "Other") === g)
            .map((i) => (
              <article className="accounts-bill" key={i.id} id={`attention-${i.id}`}>
                <Link to={`/${routeSlug}/tasks/${i.task_id}`}>{i.identifier}</Link>
                <span> · {i.label}</span>
                <p>{i.reason || "This item needs attention in the original system."}</p>
                {i.profile && (
                  <div>
                    <p>How Minkops will post bills for {i.profile.company}
                      {i.profile.waiting ? ` (${i.profile.waiting} bill${i.profile.waiting === 1 ? "" : "s"} waiting)` : ""}:</p>
                    <ul>{i.profile.summary.map((line) => <li key={line}>{line}</li>)}</ul>
                  </div>
                )}
                {i.layout && (
                  <div>
                    <p>{i.layout.prompt}</p>
                    <ul>{i.layout.samples.map((row, n) => (
                      <li key={n}>{row.date} · {(row.amount_cents / 100).toFixed(2)}{row.account ? ` · ${row.account}` : ""}{row.narration ? ` · ${row.narration}` : ""}</li>
                    ))}</ul>
                  </div>
                )}
                {i.status === "pending" && i.layout ? (
                  <div className="accounts-toolbar">
                    {i.layout.actions.map((answer) => (
                      <button key={answer} className={answer === "nothing" ? "button button-ghost" : "button"} disabled={itemBusy(i.id)}
                        onClick={() => void action(`/${i.id}/profile`, { action: answer }, i.id)}>
                        {pending.has(actionKey(`/${i.id}/profile`, { action: answer })) && <Spinner />}
                        {pending.has(actionKey(`/${i.id}/profile`, { action: answer })) ? "Confirming…" : ({ dmy: "Day first", mdy: "Month first", confirm: "Confirm", nothing: "Do nothing" }[answer] ?? answer)}
                      </button>
                    ))}
                  </div>
                ) : i.status === "pending" && i.profile ? (
                  <div className="accounts-toolbar">
                    <button className="button" disabled={itemBusy(i.id)}
                      onClick={() => void action(`/${i.id}/profile`, { action: "confirm" }, i.id)}>
                      {pending.has(actionKey(`/${i.id}/profile`, { action: "confirm" })) && <Spinner />}
                      {pending.has(actionKey(`/${i.id}/profile`, { action: "confirm" })) ? "Confirming…" : "Confirm"}</button>
                    <button className="button button-ghost" disabled={itemBusy(i.id)}
                      onClick={() => void action(`/${i.id}/profile`, { action: "nothing" }, i.id)}>
                      {pending.has(actionKey(`/${i.id}/profile`, { action: "nothing" })) ? "Applying…" : "Do nothing"}</button>
                  </div>
                ) : i.status === "pending" ? (
                  <div className="accounts-toolbar">
                    <button
                      className="button button-ghost"
                      disabled={itemBusy(i.id)}
                      onClick={() => void action(`/${i.id}/done`, undefined, i.id)}
                    >
                      {pending.has(`/${i.id}/done`) && <Spinner />}{pending.has(`/${i.id}/done`) ? "Marking done…" : "Mark as Done"}
                    </button>
                    <button
                      className="button button-ghost"
                      disabled={itemBusy(i.id)}
                      onClick={() => void action(`/${i.id}/refresh`, undefined, i.id)}
                    >
                      {pending.has(`/${i.id}/refresh`) && <Spinner />}{pending.has(`/${i.id}/refresh`) ? "Refreshing…" : "Refresh"}
                    </button>
                  </div>
                ) : (
                  <span> · Done</span>
                )}
              </article>
            ))}
        </section>
      ))}
      {!items.length && !loading && !loadError && <p className="quiet-state">No items</p>}
      <button
        className="button button-ghost"
        disabled={busy || offset === 0}
        onClick={() => setOffset(Math.max(0, offset - 200))}
      >
        Previous
      </button>
      <button
        className="button button-ghost"
        disabled={busy || items.length < 200}
        onClick={() => setOffset(offset + 200)}
      >
        Next
      </button>
    </section>
  );
}
