import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../contexts/AuthContext";

interface Item {
  id: string;
  task_id: string;
  identifier: string;
  label: string;
  status: string;
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
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const value = await api<Item[]>(base + query);
        if (active) setItems(value);
      } catch {
        if (active) setNotice("Could not load attention items");
      }
      if (active) timer = setTimeout(() => void poll(), 5000);
    };
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [base, query]);
  async function action(path: string) {
    if (!user) return;
    setBusy(true);
    setNotice("");
    try {
      const result = await api<{ queued?: number }>(
        base + path,
        { method: "POST" },
        user.csrf_token
      );
      setNotice(
        result.queued !== undefined
          ? `${result.queued} check${result.queued === 1 ? "" : "s"} queued`
          : "Marked done"
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
      <div className="accounts-toolbar">
        <button
          className="button button-ghost"
          disabled={busy}
          onClick={() => void action("/refresh")}
        >
          Refresh pending items
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
                {i.status === "pending" ? (
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
      {!items.length && <p>No items</p>}
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
