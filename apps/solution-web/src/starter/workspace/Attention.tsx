import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../contexts/AuthContext";
import { LoadingIndicator, RetryMessage, Spinner } from "../components/Feedback";

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
  const [items, setItems] = useState<Item[]>([]),
    [status, setStatus] = useState("pending");
  const [group, setGroup] = useState<"workflow" | "employee" | "status">("workflow");
  const [sort, setSort] = useState("newest"),
    [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const base = `/api/tenants/${tenant}/attention`;
  const query = `?status=${status}&offset=${offset}&group=${group}&sort=${sort}`;
  const [loading, setLoading] = useState(true), [loadError, setLoadError] = useState(""), [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    setLoading(true);
    const poll = async () => {
      try {
        const value = await api<Item[]>(base + query);
        if (active) { setItems(value); setLoadError(""); }
      } catch {
        if (active) setLoadError("Could not refresh attention items. Retrying automatically.");
      }
      if (active) { setLoading(false); timer = setTimeout(() => void poll(), 5000); }
    };
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [base, query, attempt]);
  async function action(path: string, body?: Record<string, string>) {
    if (!user) return;
    setBusy(true);
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
          : result.status === "active" ? "Pattern confirmed; waiting bills continue"
          : result.status ? "Bills left for entry in Tally" : "Marked done"
      );
      setItems(await api<Item[]>(base + query));
    } catch {
      setNotice("Action unavailable");
    } finally {
      setBusy(false);
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
      {loadError && <RetryMessage onRetry={() => setAttempt(value => value + 1)}>{loadError}</RetryMessage>}
      <div className="accounts-toolbar">
        <button
          className="button button-ghost"
          disabled={busy}
          onClick={() => void action("/refresh")}
        >
          {busy && <Spinner />}Refresh pending items
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
              <article className="accounts-bill" key={i.id}>
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
                      <button key={answer} className={answer === "nothing" ? "button button-ghost" : "button"} disabled={busy}
                        onClick={() => void action(`/${i.id}/profile`, { action: answer })}>
                        {{ dmy: "Day first", mdy: "Month first", confirm: "Confirm", nothing: "Do nothing" }[answer] ?? answer}
                      </button>
                    ))}
                  </div>
                ) : i.status === "pending" && i.profile ? (
                  <div className="accounts-toolbar">
                    <button className="button" disabled={busy}
                      onClick={() => void action(`/${i.id}/profile`, { action: "confirm" })}>Confirm</button>
                    <button className="button button-ghost" disabled={busy}
                      onClick={() => void action(`/${i.id}/profile`, { action: "nothing" })}>Do nothing</button>
                  </div>
                ) : i.status === "pending" ? (
                  <div className="accounts-toolbar">
                    <button
                      className="button button-ghost"
                      disabled={busy}
                      onClick={() => void action(`/${i.id}/done`)}
                    >
                      Mark as Done
                    </button>
                    <button
                      className="button button-ghost"
                      disabled={busy}
                      onClick={() => void action(`/${i.id}/refresh`)}
                    >
                      Refresh
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
