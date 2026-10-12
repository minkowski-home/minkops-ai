import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Workflow } from "../api";
import { useAuth } from "../contexts/AuthContext";
import { chooseFolder } from "./localFiles";
import type { Catalog, Source } from "./types";
import { CatalogReview } from "./CatalogReview";
import { desktopBridge } from "../desktop/bridge";
import { TaskProgress } from "../workspace/TaskProgress";
import { Spinner } from "../components/Feedback";
import { discoveryProgress, type Config, type DiscoveryRun } from "./discoveryView";
import { DiscoveryResults } from "./DiscoveryResults";

import { DestinationPCPicker } from '../desktop/DestinationPC';
import { destinationAvailable, destinationDevices, type DestinationDevice as Device } from '../desktop/destinationPCs';

interface Binding { source_id: string; device_id: string }

export function DiscoveryLaunch({ tenant, routeSlug, workflow }: { tenant: string; routeSlug: string; workflow: Workflow }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [devices, setDevices] = useState<Device[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [bindings, setBindings] = useState<Binding[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [aiContext, setAiContext] = useState(true);
  const [destinationMode, setDestinationMode] = useState<"excel" | "tally" | "both">((workflow.config_values.destination_mode ?? "tally") as "excel" | "tally" | "both");
  const tally = destinationMode !== "excel";
  const excel = destinationMode !== "tally";
  const [periodFrom, setPeriodFrom] = useState(new Date(Date.now() - 90 * 86400000).toISOString().slice(0, 10));
  const [periodTo, setPeriodTo] = useState(new Date().toISOString().slice(0, 10));
  const [port, setPort] = useState(9000);
  const [busy, setBusy] = useState<"launch" | "folder" | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState("");
  const base = `/api/tenants/${tenant}`;
  const load = useCallback(async () => {
    const [dd, ss, bb, latest] = await Promise.all([
      api<Device[]>(base + "/desktop/devices"), api<Source[]>(base + "/accounts/sources"),
      api<Binding[]>(base + "/desktop/sources"), api<DiscoveryRun | null>(base + "/discovery/latest")
    ]);
    return { devices: destinationDevices(dd, user?.id ?? ''), sources: ss, bindings: bb, latest };
  }, [base, user?.id]);
  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    void load().then(({ devices: owned, sources: ss, bindings: bb, latest }) => {
      if (!active) return;
      setDevices(owned); setSources(ss); setBindings(bb);
      setDeviceId(owned.find(d => d.id === latest?.device_id)?.id ?? owned.find(d => destinationAvailable(d))?.id ?? "");
      if (latest) {
        setAiContext(latest.config.ai_context ?? true);
        setSelected(latest.config.excel_source_ids);
        setDestinationMode(latest.config.destination_mode ?? (latest.config.tally ? latest.config.excel_source_ids.length ? "both" : "tally" : "excel"));
        if (latest.config.tally) {
          setPeriodFrom(latest.config.tally.period.from); setPeriodTo(latest.config.tally.period.to);
          setPort(latest.config.tally.port);
        }
      }
    }).catch((e: Error) => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [load, attempt]);
  async function connectFolder() {
    if (!user) return;
    setBusy("folder"); setError("");
    try {
      const source = await chooseFolder(tenant, user.csrf_token, undefined, true);
      const next = await load();
      setDevices(next.devices); setSources(next.sources); setBindings(next.bindings);
      setSelected(current => [...new Set([...current, source.id])]);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not connect folder."); }
    finally { setBusy(null); }
  }
  async function launch() {
    if (!user) return;
    setBusy("launch"); setError("");
    try {
      if (desktopBridge() && !desktopBridge()?.discoveryPackages) throw new Error("Update Minkops to version 0.5.0 for complete discovery packages.");
      const config: Config = {
        destination_mode: destinationMode, depth: "client_context",
        ai_context: aiContext,
        excel_source_ids: excel ? selected.filter(id => bindings.some(b => b.source_id === id && b.device_id === deviceId)) : [],
        tally: tally ? { port, period: { from: periodFrom, to: periodTo } } : null
      };
      const run = await api<DiscoveryRun>(base + "/discovery/runs", { method: "POST", body: JSON.stringify({ device_id: deviceId, request_key: crypto.randomUUID(), config }) }, user.csrf_token);
      navigate(`/${routeSlug}/tasks/${run.task_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start discovery."); }
    finally { setBusy(null); }
  }
  const available = sources.filter(s => bindings.some(b => b.source_id === s.id && b.device_id === deviceId));
  const selectedFolders = available.filter(s => selected.includes(s.id));
  const validPeriod = periodFrom && periodTo && periodFrom <= periodTo;
  if (loading) return <section className="accounts-panel discovery-panel"><p className="discovery-loading" role="status"><Spinner /> Loading connected sources…</p></section>;
  return <form className="accounts-panel discovery-panel discovery-setup" aria-label="Source discovery setup" onSubmit={event => { event.preventDefault(); void launch(); }}>
    <header className="discovery-panel-heading"><h3>Discover your business sources</h3><p>Choose your PC and sources. Review once, reuse in your workflows.</p></header>
    <div className="discovery-setup-controls">
      <DestinationPCPicker devices={devices} value={deviceId} onChange={setDeviceId} busy={Boolean(busy)} />
      <fieldset className="discovery-source-choice"><legend>Sources to discover</legend>
        <div>{([ ["tally", "Tally"], ["excel", "Excel"], ["both", "Tally + Excel"] ] as const).map(([value, label]) => <label key={value} className={destinationMode === value ? "is-selected" : ""}>
          <input type="radio" name="discovery-source-mode" value={value} checked={destinationMode === value} disabled={Boolean(busy)} onChange={() => setDestinationMode(value)} />{label}
        </label>)}</div>
      </fieldset>
    </div>
    {!devices.length && <p className="quiet-state">Connect this workspace in the Windows app to get started. <Link to={`/${routeSlug}/connections`}>Connected PCs</Link></p>}
    <div className={`discovery-setup-sources${tally && excel ? " has-both" : ""}`}>
      {tally && <section className="discovery-config-source" aria-label="Tally options">
        <h4>Tally</h4><p>All configured companies and full masters.</p>
        <div className="discovery-date-range">
          <label className="config-field">Vouchers from<input type="date" required value={periodFrom} disabled={Boolean(busy)} onChange={event => setPeriodFrom(event.target.value)} /></label>
          <label className="config-field">Through<input type="date" required min={periodFrom} value={periodTo} disabled={Boolean(busy)} onChange={event => setPeriodTo(event.target.value)} /></label>
        </div>
        <details className="discovery-connection"><summary>Connection settings</summary>
          <label className="config-field">Tally port<input type="number" required min={1} max={65535} step={1} value={port} disabled={Boolean(busy)} onChange={event => setPort(Number(event.target.value))} /></label>
        </details>
      </section>}
      {excel && <section className="discovery-config-source" aria-label="Excel options">
        <h4>Excel</h4><p>Workbook headers, tables and formula definitions.</p>
        <button type="button" className="button button-ghost" disabled={Boolean(busy) || !desktopBridge()} onClick={() => void connectFolder()}>{busy === "folder" && <Spinner />}{busy === "folder" ? "Connecting folder…" : "Connect Excel folder"}</button>
        {!desktopBridge() && <p className="quiet-state">Connect folders in the Windows app, then select them here.</p>}
        <div className="discovery-folder-list">{available.map(source => <label className="accounts-check" key={source.id}>
          <input type="checkbox" checked={selected.includes(source.id)} disabled={Boolean(busy)} onChange={event => setSelected(current => event.target.checked ? [...current, source.id] : current.filter(id => id !== source.id))} />
          <span>{source.label}<small>{source.files.filter(file => /\.xlsx$/i.test(file.path)).length} workbooks</small></span>
        </label>)}</div>
        {!available.length && <p className="quiet-state">No folders connected to this PC yet.</p>}
        <p className="discovery-limit">Up to 45 workbooks / 8 MB per run.</p>
      </section>}
    </div>
    <label className="accounts-check discovery-ai-context">
      <input type="checkbox" checked={aiContext} disabled={Boolean(busy)} onChange={event => setAiContext(event.target.checked)} />
      <span>AI context analysis<small>{excel ? "Find client conventions and propose Excel column mappings. When off, save structure only; no new Excel entry mappings are created." : "Find client conventions and exceptions. Turn off to review collected sources directly."}</small></span>
    </label>
    {error && <p role="alert" className="form-message">{error} {!devices.length && <button type="button" className="button button-ghost" onClick={() => setAttempt(value => value + 1)}>Retry loading</button>}</p>}
    <footer className="discovery-setup-footer"><button type="submit" className="button button-primary" disabled={Boolean(busy) || workflow.status !== "active" || !destinationAvailable(devices.find(d => d.id === deviceId)) || (excel && !selectedFolders.length) || (tally && (!validPeriod || !Number.isInteger(port) || port < 1 || port > 65535))}>
      {busy === "launch" && <Spinner />}{busy === "launch" ? "Starting discovery…" : "Discover sources"}
    </button><p>Read on your PC. Saved on your PC and in this workspace.</p></footer>
  </form>;
}

export function DiscoveryReview({ tenant, taskId, controlState = "active" }: { tenant: string; taskId: string; controlState?: string }) {
  const { user } = useAuth();
  const [run, setRun] = useState<DiscoveryRun | null>(null);
  const [edited, setEdited] = useState<Catalog | null>(null);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState<"confirm" | "export" | null>(null);
  const [filter, setFilter] = useState("");
  const [attempt, setAttempt] = useState(0);
  const base = `/api/tenants/${tenant}/discovery`;
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    const poll = async () => {
      try {
        const next = await api<DiscoveryRun | null>(base + `/tasks/${taskId}`);
        if (!active) return;
        if (!next) throw new Error("This discovery run could not be found.");
        failures = 0; setLoadError(""); setRun(current => current?.ready ? current : next);
        if (next.mapping_run?.result) setEdited(current => current ?? structuredClone(next.mapping_run!.result as Catalog));
        if (!["completed", "failed", "stopped"].includes(next.state)) timer = setTimeout(() => void poll(), 2000);
      } catch (e) {
        if (!active) return;
        setLoadError(e instanceof Error ? e.message : "Could not load discovery.");
        // Preserve the last results and resume after transient network failures.
        timer = setTimeout(() => void poll(), Math.min(15000, 2000 * 2 ** Math.min(failures++, 3)));
      }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [base, taskId, attempt, controlState]);
  async function confirm() {
    if (!user || !run) return;
    setBusy("confirm"); setError("");
    try { setRun(await api<DiscoveryRun>(base + `/runs/${run.id}/confirm`, { method: "POST", body: JSON.stringify({ excel_mappings: edited }) }, user.csrf_token)); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not confirm sources."); }
    finally { setBusy(null); }
  }
  async function saveCatalog() {
    if (!run) return;
    setBusy("export"); setError("");
    try { await desktopBridge()?.saveCatalog?.(tenant, run.id); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not save source catalog."); }
    finally { setBusy(null); }
  }
  const retry = <button className="button button-ghost" onClick={() => setAttempt(value => value + 1)}>Retry now</button>;
  if (!run) return <section className="accounts-panel discovery-panel">
    {loadError ? <><p role="alert">{loadError}</p>{retry}</> : <p className="discovery-loading" role="status"><Spinner /> Loading discovery progress…</p>}
  </section>;
  const pending = ["queued", "executing"].includes(run.state);
  return <>
    <TaskProgress view={discoveryProgress(controlState === "active" ? run : { ...run, state: controlState, ready: false })} stale={Boolean(loadError)} />
    {loadError && <p role="alert" className="form-message">Could not refresh discovery. Retrying automatically. {retry}</p>}
    <section className="accounts-panel discovery-panel" aria-label="Discovered sources">
      <header className="discovery-panel-heading"><h3>{controlState === "paused" ? "Discovery paused" : controlState === "stopped" ? "Discovery stopped" : run.ready ? "Your sources are ready" : run.catalog?.partial ? "Some sources need attention" : pending ? run.catalog ? "Sources collected" : "Discovering your sources" : run.state === "failed" ? "Discovery needs attention" : "Review your sources"}</h3>
        <p>{run.ready ? run.catalog?.review.reused_from ? "No changes. Your previous confirmation was retained." : "Confirmed and saved for your workflows."
          : controlState === "paused" ? "Resume to continue. An operation already underway may finish."
            : controlState === "stopped" ? run.catalog ? "Remaining work stopped. Collected results are available below." : "Remaining work stopped. Start a new run when you’re ready."
          : run.catalog?.partial ? "Resolve unavailable sources in the original tools, then run again."
            : pending ? run.catalog ? "Checking client context and workbook mappings before review." : "You can leave this page and return. Collection continues on your PC."
              : run.state === "failed" ? "Check source access on your PC, then run discovery again." : "Check the collected counts and mappings, then confirm."}</p></header>
      {run.catalog?.sources.map(source => source.snapshot?.scope_error && <p role="alert" className="form-message" key={source.key}>{source.snapshot.scope_error}</p>)}
      {run.catalog?.context_error && <p role="alert" className="form-message">{run.catalog.context_error}</p>}
      {run.catalog && run.config.ai_context === false && <p className="quiet-state">AI analysis is off. Review the collected sources{run.config.excel_source_ids.length ? "; Excel structure is saved without entry mappings" : ""}.</p>}
      <DiscoveryResults run={controlState === "active" ? run : { ...run, state: controlState }} />
      {run.state === "review" && edited && edited.sheets.length > 0 && <div className="discovery-mapping-review">
        <label className="config-field">Find a workbook, sheet or table<input type="search" value={filter} onChange={event => setFilter(event.target.value)} /></label>
        <CatalogReview catalog={edited} provenance={run.mapping_run?.config.file_provenance as { id: string; path: string }[]} filter={filter} onChange={setEdited} />
      </div>}
      {run.catalog?.context_notes?.length ? <details className="discovery-notes"><summary>Client conventions and edge cases <span>{run.catalog.context_notes.length}</span></summary>
        <ul>{run.catalog.context_notes.map((note, index) => <li key={index}>
          <strong>{run.catalog?.sources.flatMap(source => source.snapshot?.companies ?? []).find(company => company.company_guid === note.company_guid)?.company ?? note.company_guid}</strong>
          <p>{note.observation} · {note.certainty}</p><p className="quiet-state">Evidence: {note.evidence_ids.join(", ")}</p>
        </li>)}</ul></details> : null}
      <div className="accounts-toolbar discovery-review-actions">
        {run.state === "review" && <button className="button button-primary" disabled={controlState !== "active" || Boolean(busy) || Boolean(loadError) || run.catalog?.partial || Boolean(run.mapping_run && !edited)} onClick={() => void confirm()}>
          {busy === "confirm" && <Spinner />}{busy === "confirm" ? "Confirming sources…" : "Confirm sources"}
        </button>}
        {run.catalog && (desktopBridge()?.saveCatalog ? <button className="button button-ghost" disabled={Boolean(busy)} onClick={() => void saveCatalog()}>{busy === "export" && <Spinner />}{busy === "export" ? "Saving catalog…" : "Save source catalog"}</button>
          : <a className="button button-ghost" href={base + `/runs/${run.id}/catalog.json`} download>Download source catalog</a>)}
      </div>
      {error && <p role="alert" className="form-message">{error}</p>}
    </section>
  </>;
}
