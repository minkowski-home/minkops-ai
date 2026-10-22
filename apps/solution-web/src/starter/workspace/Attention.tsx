import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Client } from "../api";
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
  /** A question card: a statement format's date order, or how a company keeps its books. The server labels each answer. */
  question?: {
    prompt: string;
    options: { action: string; label: string }[];
    samples?: { date: string; amount_cents: number; account: string; narration: string }[];
  };
  workflow: string;
  employee: string;
  /** The client business whose work it is; none for a tenant's own items. */
  client: string | null;
  updated_at: string;
  /** A newly found company, shown to those who reach every client: the client's company it continues, if any. */
  card?: CompanyCard;
}

interface CompanyCard {
  company_id: string;
  name: string;
  device: string;
  /** Another connected PC holds these books for a client: they are not added here. */
  held_on?: string;
  /** The client's company these books continue, from a PC that is disconnected. */
  continues?: { client: string; client_name: string; device: string };
}

/** Shared list across workflows. Detailed diagnostics stay in the audit store. */
export function Attention({ tenant, routeSlug }: { tenant: string; routeSlug: string }) {
  const { user } = useAuth();
  const [status, setStatus] = useState("pending");
  const [group, setGroup] = useState<"workflow" | "employee" | "status" | "client">("client");
  const [sort, setSort] = useState("newest"),
    [offset, setOffset] = useState(0);
  const [pending, setPending] = useState<Set<string>>(new Set());
  const base = `/api/tenants/${tenant}/attention`;
  const query = `?status=${status}&offset=${offset}&group=${group}&sort=${sort}`;
  const scope = `${user?.id ?? ""}:${tenant}`;
  const { data: items = [], error: loadError, loading, refresh, setData: setItems } = useRead<Item[]>(scope, base + query, { interval: 5000 });
  const { data: notice = "", setData: setNotice } = useRead<string>(scope, base + "#notice", { enabled: false });
  const admin = Boolean(user?.is_platform_admin || user?.memberships.some((m) => m.slug === tenant && m.role === "admin"));
  const deciding = admin && items.some((item) => item.kind === "company" && item.card && item.status === "pending");
  const { data: clients = [] } = useRead<Client[]>(scope, `/api/tenants/${tenant}/clients`, { enabled: deciding });
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const busy = pending.size > 0;
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (id) document.getElementById(id)?.scrollIntoView({ block: "center" });
  }, [items]);
  const actionKey = (path: string, body?: Record<string, string>) => path + (body?.action ?? "");
  const itemBusy = (id: string) => [...pending].some(key => key.startsWith(`/${id}/`));
  /** Post one action on an item. `url` sends it elsewhere than the item, such as a company decision, saying `done`. */
  async function action(path: string, body?: Record<string, string>, itemId?: string, to?: { url: string; done: string }) {
    if (!user) return;
    const key = actionKey(path, body);
    if (pending.has(key)) return;
    setPending(current => new Set(current).add(key));
    setNotice("");
    try {
      const result = await api<{ status?: string }>(
        to?.url ?? base + path,
        { method: "POST", ...(body ? { body: JSON.stringify(body) } : {}) },
        user.csrf_token
      );
      setNotice(to ? to.done : ["active", "answered"].includes(result.status ?? "") ? "Confirmed; waiting work continues"
        : result.status === "done" ? "Marked done" : "Left for manual handling");
      if (itemId) {
        setItems(current => status === "pending" ? (current ?? []).filter(item => item.id !== itemId)
          : (current ?? []).map(item => item.id === itemId ? { ...item, status: "done" } : item));
      }
      // A receipt is already authoritative. Refresh failures retain that result;
      // invalidation also fences polls started before the committed decision.
      reads.invalidate(scope, resource => !resource.endsWith("#notice"));
    } catch (caught) {
      if (to) {
        // A company decision is refused with its reason, such as books another PC holds; nothing changed.
        setNotice(caught instanceof Error ? caught.message : "Could not decide this company. Refresh and try again.");
        reads.invalidate(scope, resource => !resource.endsWith("#notice"));
        return;
      }
      let receipt: { action: string; status: string } | null = null;
      if (itemId && path.endsWith("/decision")) {
        try { receipt = await api(`${base}/${itemId}/decision`); } catch { /* An unreadable receipt remains uncertain. */ }
      }
      setNotice(receipt && receipt.action === body?.action
        ? ["active", "answered"].includes(receipt.status) ? "Confirmed; waiting work continues"
          : "Decision recorded; left for manual handling"
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
  // Items of no client, such as a company found on a PC, belong to the workspace itself.
  const groupOf = (i: Item) => i[group] || (group === "client" ? "Workspace" : "Other");
  const groups = [...new Set(ordered.map(groupOf))].sort();
  return (
    <section className="route-screen">
      <h2>Attention items</h2>
      {loading && <LoadingIndicator>Loading attention items…</LoadingIndicator>}
      {loadError && <RetryMessage onRetry={() => void refresh()}>Could not refresh attention items. Showing the last received results; retrying automatically.</RetryMessage>}
      <div className="accounts-toolbar">
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
            {["client", "workflow", "employee", "status"].map((v) => (
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
            .filter((i) => groupOf(i) === g)
            .map((i) => (
              <article className="accounts-item" key={i.id} id={`attention-${i.id}`}>
                <Link to={`/${routeSlug}/tasks/${i.task_id}`}>{i.identifier}</Link>
                <span> · {i.label}</span>
                {i.client && group !== "client" && <span> · {i.client}</span>}
                <p>{i.reason || "This item needs attention in the original system."}</p>
                {i.question && (
                  <div>
                    <p>{i.question.prompt}</p>
                    {!!i.question.samples?.length && <ul>{i.question.samples.map((row, n) => (
                      <li key={n}>{row.date} · {(row.amount_cents / 100).toFixed(2)}{row.account ? ` · ${row.account}` : ""}{row.narration ? ` · ${row.narration}` : ""}</li>
                    ))}</ul>}
                  </div>
                )}
                {i.status === "pending" && i.kind === "company" ? (
                  <CompanyChoices item={i} admin={admin} clients={clients} chosen={chosen[i.id] ?? ""}
                    choose={(slug) => setChosen((current) => ({ ...current, [i.id]: slug }))}
                    busy={itemBusy(i.id)} pending={(path) => pending.has(path)}
                    decide={(path, url, done, body) => void action(path, body, i.id, { url: `/api/tenants/${tenant}${url}`, done })} />
                ) : i.status === "pending" && i.question ? (
                  <div className="accounts-toolbar">
                    {i.question.options.map(({ action: answer, label }) => (
                      <button key={answer} className={answer === "nothing" ? "button button-ghost" : "button"} disabled={itemBusy(i.id)}
                        onClick={() => void action(`/${i.id}/decision`, { action: answer }, i.id)}>
                        {pending.has(actionKey(`/${i.id}/decision`, { action: answer })) && <Spinner />}
                        {pending.has(actionKey(`/${i.id}/decision`, { action: answer })) ? "Confirming…" : label}
                      </button>
                    ))}
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

/**
 * A newly found company's decision, for admins: continue the client's company these books were (keeping what was
 * learnt, rules and history), add them to a client, or keep them out of every client's books. Marking the card done
 * would leave the company undecided, so it is not offered.
 */
function CompanyChoices({ item, admin, clients, chosen, choose, busy, pending, decide }: {
  item: Item;
  admin: boolean;
  clients: Client[];
  chosen: string;
  choose: (slug: string) => void;
  busy: boolean;
  pending: (path: string) => boolean;
  decide: (path: string, url: string, done: string, body?: Record<string, string>) => void;
}) {
  const card = item.card;
  if (!admin || !card) return <p className="quiet-state">A workspace admin decides whose books these are.</p>;
  const id = card.company_id, continues = card.continues;
  // Adding the books to the client they continue is the continuation itself, offered on its own button.
  const others = clients.filter((c) => c.slug !== continues?.client);
  const client = chosen || others[0]?.slug || "";
  const named = others.find((c) => c.slug === client)?.name ?? client;
  const paths = { continue: `/${item.id}/company/continue`, add: `/${item.id}/company/add`,
    decline: `/${item.id}/company/decline` };
  const label = (path: string, idle: string, working: string) => (
    <>{pending(path) && <Spinner />}{pending(path) ? working : idle}</>
  );
  return (
    <div className="accounts-toolbar">
      {continues && (
        <button className="button" disabled={busy}
          onClick={() => decide(paths.continue, `/companies/${id}/authorise`, `Continued ${continues.client_name}'s books on ${card.device}`, { client: continues.client })}>
          {label(paths.continue, `Continue ${continues.client_name}'s books here`, "Continuing…")}
        </button>
      )}
      {!card.held_on && others.length > 0 && (
        <>
          <label className="config-field">
            {continues ? "Another client" : "Client"}
            <select aria-label={`Client for ${card.name}`} value={client} disabled={busy} onChange={(e) => choose(e.target.value)}>
              {others.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
            </select>
          </label>
          <button className={continues ? "button button-ghost" : "button"} disabled={busy || !client}
            onClick={() => decide(paths.add, `/companies/${id}/authorise`, `Added to ${named}`, { client })}>
            {label(paths.add, `Add to ${named}`, "Adding…")}
          </button>
        </>
      )}
      {!card.held_on && !continues && !clients.length && (
        <p className="quiet-state">Add a client business before adding its companies.</p>
      )}
      <button className="button button-ghost" disabled={busy}
        onClick={() => decide(paths.decline, `/companies/${id}/decline`, "Kept out of every client's books")}>
        {label(paths.decline, "Not a client's books", "Keeping out…")}
      </button>
    </div>
  );
}
