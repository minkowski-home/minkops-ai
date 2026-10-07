import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Workflow } from "../api";
import { useAuth } from "../contexts/AuthContext";
import { chooseFolder } from "./localFiles";
import type { Catalog, Run, Source } from "./types";
import { CatalogReview } from "./CatalogReview";
import { desktopBridge } from "../desktop/bridge";

interface Device {
  id: string;
  name: string;
  owner_id: string;
  revoked_at: string | null;
  expires_at: string;
  last_seen_at: string | null;
}
interface Binding {
  source_id: string;
  device_id: string;
}
interface Config {
  destination_mode?: 'excel' | 'tally' | 'both';
  depth: string;
  excel_source_ids: string[];
  tally: { company: string; port: number; categories: string[] } | null;
}
interface Collection {
  category: string;
  status: string;
  count?: number;
  fields?: string[];
  records?: Record<string, unknown>[];
  error?: string;
}
interface Book {
  path: string;
  file_id: string;
  status: string;
  error?: string;
  structure?: {
    sheets: {
      sheet: string;
      columns: number;
      rows: number;
      tables: { name: string }[];
    }[];
  };
}
interface DiscoveredSource {
  key: string;
  tool: string;
  label?: string;
  status: string;
  error?: string;
  workbooks?: Book[];
  snapshot?: { company: string; collections: Collection[] };
}
interface DiscoveryRun {
  id: string;
  task_id: string;
  device_id: string;
  config: Config;
  state: string;
  ready: boolean;
  observations: { key: string; status: string; category?: string }[];
  mapping_run: Run | null;
  catalog: {
    partial: boolean;
    sources: DiscoveredSource[];
    review: { status: string; reused_from: string | null };
    excel_mappings: Catalog | null;
  } | null;
}
const categories = [
  ["company", "Company & tax settings"],
  ["groups", "Account groups"],
  ["ledgers", "Ledgers & supplier tax details"],
  ["voucher_types", "Voucher types"],
  ["stock_items", "Stock items & tax details"],
  ["stock_groups", "Stock groups"],
  ["units", "Units"],
  ["godowns", "Locations"],
  ["cost_centres", "Cost centres"],
  ["cost_categories", "Cost categories"],
  ["currencies", "Currencies"]
];

export function DiscoveryLaunch({
  tenant,
  routeSlug,
  workflow
}: {
  tenant: string;
  routeSlug: string;
  workflow: Workflow;
}) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [devices, setDevices] = useState<Device[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [bindings, setBindings] = useState<Binding[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [destinationMode, setDestinationMode] = useState<'excel' | 'tally' | 'both'>(
    (workflow.config_values.destination_mode ?? 'tally') as 'excel' | 'tally' | 'both'
  );
  const tally = destinationMode !== 'excel';
  const [company, setCompany] = useState("");
  const [port, setPort] = useState(9000);
  const [depth, setDepth] = useState(
    String(workflow.config_values.discovery_depth ?? "business_mappings")
  );
  const [selectedCategories, setCategories] = useState(categories.map((c) => c[0]));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const base = `/api/tenants/${tenant}`;
  async function load() {
    const [dd, ss, bb, latest] = await Promise.all([
      api<Device[]>(base + "/desktop/devices"),
      api<Source[]>(base + "/accounts/sources"),
      api<Binding[]>(base + "/desktop/sources"),
      api<DiscoveryRun | null>(base + "/discovery/latest")
    ]);
    const owned = dd.filter(
      (d) =>
        d.owner_id === user?.id && !d.revoked_at && new Date(d.expires_at) > new Date()
    );
    setDevices(owned);
    setSources(ss);
    setBindings(bb);
    setDeviceId((current) =>
      owned.some((d) => d.id === current)
        ? current
        : owned.some((d) => d.id === latest?.device_id)
          ? latest!.device_id
          : owned[0]?.id || ""
    );
    if (latest) {
      setSelected(latest.config.excel_source_ids);
      setDestinationMode(latest.config.destination_mode ?? (latest.config.tally ? (latest.config.excel_source_ids.length ? 'both' : 'tally') : 'excel'));
      setDepth(latest.config.depth);
      if (latest.config.tally) {
        setCompany(latest.config.tally.company);
        setPort(latest.config.tally.port);
        setCategories(latest.config.tally.categories);
      }
    }
  }
  useEffect(() => {
    void load().catch((e: Error) =>
      setError(e.message)
    ); /* Server-owned setup is restored on any client. */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, user?.id]);
  async function connectFolder() {
    if (!user) return;
    setBusy(true);
    setError("");
    try {
      const s = await chooseFolder(tenant, user.csrf_token);
      await load();
      setSelected((v) => [...new Set([...v, s.id])]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not connect folder.");
    } finally {
      setBusy(false);
    }
  }
  async function launch() {
    if (!user) return;
    setBusy(true);
    setError("");
    try {
      const config: Config = {
        destination_mode: destinationMode,
        depth,
        excel_source_ids: destinationMode === 'tally' ? [] : selected.filter((id) =>
          bindings.some((b) => b.source_id === id && b.device_id === deviceId)
        ),
        tally: tally
          ? { company: company.trim(), port, categories: selectedCategories }
          : null
      };
      const run = await api<DiscoveryRun>(
        base + "/discovery/runs",
        {
          method: "POST",
          body: JSON.stringify({
            device_id: deviceId,
            request_key: crypto.randomUUID(),
            config
          })
        },
        user.csrf_token
      );
      navigate(`/${routeSlug}/tasks/${run.task_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start discovery.");
    } finally {
      setBusy(false);
    }
  }
  const available = sources.filter((s) =>
    bindings.some((b) => b.source_id === s.id && b.device_id === deviceId)
  );
  const selectedFolders = available.filter((s) => selected.includes(s.id));
  return (
    <section className="accounts-panel" aria-label="Source discovery setup">
      <h3>Discover your business sources</h3>
      <p>
        Choose what to read on your PC. Review the results once, then reuse them for your
        workflows.
      </p>
      <label className="config-field">
        PC to use
        <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
          <option value="">Choose a connected PC</option>
          {devices.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
              {!d.last_seen_at || Date.now() - new Date(d.last_seen_at).getTime() > 30000
                ? " · waiting for connection"
                : ""}
            </option>
          ))}
        </select>
      </label>
      <label className="config-field">Sources to discover<select value={destinationMode} onChange={e=>setDestinationMode(e.target.value as typeof destinationMode)}><option value="excel">Excel</option><option value="tally">Tally</option><option value="both">Both · Excel and Tally</option></select></label>
      {!devices.length && (
        <p role="status">
          Open the Windows app and connect this workspace in Connected PCs first.
        </p>
      )}
      <div className="discovery-source-grid">
        <section className="discovery-source-card">
          <h4>Tally</h4>
          <p>Read company settings and the masters used for Bill Entry.</p>
          {tally && (
            <>
              <label className="config-field">
                Open company name
                <input
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  placeholder="Exact company name in Tally"
                />
              </label>
              <details>
                <summary>Connection and reference lists</summary>
                <label className="config-field">
                  Tally port
                  <input
                    type="number"
                    min={1}
                    max={65535}
                    value={port}
                    onChange={(e) => setPort(Number(e.target.value))}
                  />
                </label>
                {categories.map(([key, label]) => (
                  <label className="accounts-check" key={key}>
                    <input
                      type="checkbox"
                      checked={selectedCategories.includes(key)}
                      onChange={(e) =>
                        setCategories((v) =>
                          e.target.checked ? [...v, key] : v.filter((k) => k !== key)
                        )
                      }
                    />
                    {label}
                  </label>
                ))}
              </details>
            </>
          )}
        </section>
        <section className="discovery-source-card">
          <h4>Excel</h4>
          <p>
            Read worksheets, named tables, columns, formulas and reference data from
            selected folders.
          </p>
          <button
            className="button button-ghost"
            disabled={busy || !desktopBridge() || destinationMode === 'tally'}
            onClick={() => void connectFolder()}
          >
            Connect Excel folder
          </button>
          {!desktopBridge() && (
            <p className="quiet-state">
              Connect a folder in the Windows app first. You can then run this workflow
              from the web.
            </p>
          )}
          {available.map((s) => (
            <label className="accounts-check" key={s.id}>
              <input
                type="checkbox"
                checked={selected.includes(s.id)}
                disabled={destinationMode === 'tally'}
                onChange={(e) =>
                  setSelected((v) =>
                    e.target.checked ? [...v, s.id] : v.filter((id) => id !== s.id)
                  )
                }
              />
              {s.label} · {s.files.filter((f) => /\.xlsx$/i.test(f.path)).length}{" "}
              workbooks
            </label>
          ))}
          {!available.length && (
            <p className="quiet-state">No folders connected to this PC yet.</p>
          )}
        </section>
      </div>
      <label className="config-field">
        What should we discover?
        <select value={depth} onChange={(e) => setDepth(e.target.value)}>
          <option value="business_mappings">Everything needed for Bill Entry</option>
          <option value="reference_data">Structure and reference data</option>
          <option value="structure">Structure only</option>
        </select>
      </label>
      <p className="quiet-state">
        Reads happen on the chosen PC. Results are saved securely in your workspace. Up to
        45 Excel workbooks / 8 MB per run; select a focused folder.
      </p>
      {error && (
        <p role="alert" className="form-message">
          {error}
        </p>
      )}
      <button
        className="button button-primary"
        disabled={
          busy ||
          workflow.status !== "active" ||
          !deviceId ||
          (!tally && !selectedFolders.length) ||
          (destinationMode === 'both' && !selectedFolders.length) ||
          (tally && (!company.trim() || !selectedCategories.length))
        }
        onClick={() => void launch()}
      >
        {busy ? "Starting…" : "Discover sources"}
      </button>
    </section>
  );
}

export function DiscoveryReview({ tenant, taskId }: { tenant: string; taskId: string }) {
  const { user } = useAuth();
  const [run, setRun] = useState<DiscoveryRun | null>(null);
  const [edited, setEdited] = useState<Catalog | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("");
  const base = `/api/tenants/${tenant}/discovery`;
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api<DiscoveryRun | null>(base + `/tasks/${taskId}`);
        if (!active) return;
        setRun(next);
        if (next?.mapping_run?.result)
          setEdited((v) => v ?? structuredClone(next.mapping_run?.result as Catalog));
        if (next && !["completed", "failed"].includes(next.state))
          timer = setTimeout(() => void poll(), 2000);
      } catch (e) {
        if (active)
          setError(e instanceof Error ? e.message : "Could not load discovery.");
      }
    };
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [base, taskId]);
  async function confirm() {
    if (!user || !run) return;
    setBusy(true);
    setError("");
    try {
      setRun(
        await api<DiscoveryRun>(
          base + `/runs/${run.id}/confirm`,
          { method: "POST", body: JSON.stringify({ excel_mappings: edited }) },
          user.csrf_token
        )
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not confirm sources.");
    } finally {
      setBusy(false);
    }
  }
  async function saveCatalog() {
    if (!run) return;
    setBusy(true);setError('');
    try { await desktopBridge()?.saveCatalog?.(tenant,run.id); }
    catch(e) {setError(e instanceof Error?e.message:'Could not save source catalog.');}
    finally {setBusy(false);}
  }
  if (!run) return error ? <p role="alert">{error}</p> : null;
  const sources =
    run.catalog?.sources ??
    ([
      ...run.config.excel_source_ids.map((key) => ({
        key,
        tool: "excel",
        status: "waiting"
      })),
      ...(run.config.tally ? [{ key: "tally", tool: "tally", status: "waiting" }] : [])
    ] as DiscoveredSource[]);
  const pending = ["queued", "executing"].includes(run.state);
  return (
    <section className="accounts-panel" aria-label="Discovered sources">
      <h3>
        {run.ready
          ? "Your sources are ready"
          : run.catalog?.partial
            ? "Some sources need attention"
            : pending
              ? "Discovering your sources"
              : "Review your sources"}
      </h3>
      <p>
        {run.ready
          ? run.catalog?.review.reused_from
            ? "No structure or mapping changes. Your confirmation was retained."
            : "Catalog confirmed and saved in your workspace."
          : run.catalog?.partial
            ? "Successful results are saved below. Reconnect unavailable sources and run discovery again before using this catalog."
            : pending
              ? "Keep Minkops running on the selected PC. You can leave this page and come back."
              : "Check the sources and proposed mappings before confirming."}
      </p>
      <div className="discovery-source-grid">
        {sources.map((s) => {
          const observed = run.observations.filter((o) => o.key === s.key);
          const status =
            s.status === "waiting"
              ? (observed.find((o) => !o.category)?.status ?? "waiting")
              : s.status;
          const issues =
            s.snapshot?.collections.filter((c) => c.status !== "ready").length ??
            s.workbooks?.filter((b) => b.status !== "ready").length ??
            0;
          return (
            <section className="discovery-source-card" key={s.key}>
              <h4>
                {s.tool === "tally"
                  ? `Tally · ${s.snapshot?.company ?? run.config.tally?.company}`
                  : (s.label ?? "Excel folder")}
              </h4>
              <strong role="status">
                {issues
                  ? "Partly collected"
                  : ({
                      ready: "Collected",
                      reading: "Reading…",
                      waiting: "Waiting for your PC",
                      unavailable: "Needs attention"
                    }[status] ?? status)}
              </strong>
              {s.error && <p role="alert">{s.error}</p>}
              {s.snapshot?.collections.map((c) => (
                <details key={c.category}>
                  <summary>
                    {categories.find((k) => k[0] === c.category)?.[1] ?? c.category} ·{" "}
                    {c.status === "ready" ? `${c.count} records` : "Needs attention"}
                  </summary>
                  {c.error ? (
                    <p role="alert">{c.error}</p>
                  ) : (
                    <><p className="quiet-state">
                      {c.fields?.length} observed fields. Reference identifiers and nested
                      tax details are included in the catalog.
                    </p><ul>{c.records?.slice(0,50).map((record,index)=>{
                      const name=record['@_NAME'] ?? record.NAME;
                      const label=typeof name==='string'?name:typeof name==='object'&&name?String((name as Record<string,unknown>)['#text']??''):'';
                      return label?<li key={index}>{label}</li>:null;
                    })}</ul>{(c.records?.length ?? 0)>50&&<p className="quiet-state">Showing the first 50 names. The saved catalog contains the complete list.</p>}</>
                  )}
                </details>
              ))}
              {s.workbooks?.map((b) => (
                <details key={b.path}>
                  <summary>
                    {b.path} ·{" "}
                    {b.status === "ready"
                      ? `${b.structure?.sheets.length} sheets`
                      : "Needs attention"}
                  </summary>
                  {b.error ? (
                    <p role="alert">{b.error}</p>
                  ) : (
                    b.structure?.sheets.map((sheet) => (
                      <p key={sheet.sheet}>
                        {sheet.sheet} · {sheet.columns} columns · {sheet.tables.length}{" "}
                        named tables
                      </p>
                    ))
                  )}
                </details>
              ))}
              {!run.catalog &&
                observed
                  .filter((o) => o.category)
                  .map((o) => (
                    <p className="quiet-state" key={o.category}>
                      {categories.find((k) => k[0] === o.category)?.[1]} ·{" "}
                      {o.status === "reading"
                        ? "Reading…"
                        : o.status === "ready"
                          ? "Collected"
                          : "Needs attention"}
                    </p>
                  ))}
            </section>
          );
        })}
      </div>
      {run.state === "failed" && (
        <p role="alert">
          {run.mapping_run?.error ??
            "Collection was interrupted. Check the task timeline, then run discovery again."}
        </p>
      )}
      {run.state === "review" && edited && (
        <>
          <label className="config-field">
            Find a workbook, sheet or table
            <input
              type="search"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </label>
          <CatalogReview
            catalog={edited}
            provenance={
              run.mapping_run?.config.file_provenance as { id: string; path: string }[]
            }
            filter={filter}
            onChange={setEdited}
          />
        </>
      )}
      <div className="accounts-toolbar">
        {run.state === "review" && (
          <button
            className="button button-primary"
            disabled={busy || run.catalog?.partial || Boolean(run.mapping_run && !edited)}
            onClick={() => void confirm()}
          >
            {busy ? "Saving…" : "Confirm sources and mappings"}
          </button>
        )}
        {run.catalog && (desktopBridge()?.saveCatalog ? <button className="button button-ghost" disabled={busy} onClick={()=>void saveCatalog()}>Save source catalog</button> : (
          <a
            className="button button-ghost"
            href={base + `/runs/${run.id}/catalog.json`}
            download
          >
            Download source catalog
          </a>
        ))}
      </div>
      {error && (
        <p role="alert" className="form-message">
          {error}
        </p>
      )}
    </section>
  );
}
