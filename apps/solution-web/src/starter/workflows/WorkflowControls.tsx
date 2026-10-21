/** Product adapters around the same installed workflow lifecycle. */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Workflow } from "../api";
import { AccountsLaunch, AccountsQuickRun } from "../accounts/AccountsLaunch";
import { AccountsReview } from "../accounts/AccountsReview";
import type { Source } from "../accounts/types";
import { useAuth } from "../contexts/AuthContext";
import { DestinationPCPicker, useDestinationPC, type DestinationPCState } from '../desktop/DestinationPC';
import { RunSettings, type RunSettingsProps } from "./RunSettings";
import { presentationFor } from "./presentation";
import { LoadingIndicator, Spinner, RetryMessage } from "../components/Feedback";

type LaunchProps = RunSettingsProps & { routeSlug: string; destination?: DestinationPCState };

/** Schema-driven fallback for reviewed proposals using existing file grants. */
function ProposalLaunch({ tenant, routeSlug, workflow, destination, onConfigChange, settings }: LaunchProps) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [sources, setSources] = useState<Source[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const values = { ...workflow.run_defaults, ...workflow.config_values };
  const setValues = (update: (current: typeof values) => typeof values) => onConfigChange?.(update(values) as Workflow["config_values"]);
  const [loading, setLoading] = useState(true), [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    void api<Source[]>(`/api/tenants/${tenant}/accounts/sources`).then((loaded) => {
      if (active) setSources(loaded);
    }).catch((e: Error) => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [tenant, attempt]);
  const properties = (workflow.run_schema?.properties ?? {}) as Record<string, { type?: string; title?: string; enum?: string[] }>;
  const fields = Object.entries(properties).filter(([key]) => ! ["source_ids", "destination_device_id", ...Object.keys(workflow.config_schema.properties)].includes(key));
  async function launch() {
    if (!user) return;
    setBusy(true); setError("");
    try {
      const run = await api<{ task_id: string }>(`/api/tenants/${tenant}/accounts/runs`, {
        method: "POST", body: JSON.stringify({ key: workflow.key, request_key: crypto.randomUUID(), file_ids: selected, destination_device_id: destination?.deviceId || null, config: values }),
      }, user.csrf_token);
      navigate(`/${routeSlug}/tasks/${run.task_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start workflow."); }
    finally { setBusy(false); }
  }
  return <section className="accounts-panel" aria-label="Run workflow">
    <h3>Run {workflow.name.toLowerCase()}</h3>
    {loading && <LoadingIndicator>Loading sources…</LoadingIndicator>}
    {!sources.length && error && <RetryMessage onRetry={() => setAttempt(value => value + 1)}>{error}</RetryMessage>}
    {sources.map((source) => <details className="accounts-sources" key={source.id}><summary>{source.label} · {source.files.length} files</summary><div className="accounts-file-list">
      {source.files.map((file) => <label className="accounts-check" key={file.id}><input type="checkbox" checked={selected.includes(file.id)}
        onChange={(event) => setSelected((current) => event.target.checked ? [...current, file.id] : current.filter((id) => id !== file.id))} />{file.path}</label>)}
    </div></details>)}
    {fields.map(([key, spec]) => <label className="config-field" key={key}>{spec.title ?? key}
      {spec.enum ? <select value={String(values[key] ?? "")} onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))}>
        <option value="">Choose</option>{spec.enum.map((value) => <option key={value} value={value}>{value}</option>)}</select>
        : spec.type === "boolean" ? <input type="checkbox" checked={Boolean(values[key])} onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.checked }))} />
          : <input type={spec.type === "integer" || spec.type === "number" ? "number" : "text"} value={String(values[key] ?? "")}
            onChange={(event) => setValues((current) => ({ ...current, [key]: spec.type === "integer" || spec.type === "number" ? Number(event.target.value) : event.target.value }))} />}
    </label>)}
    <RunSettings tenant={tenant} workflow={workflow} settings={settings} onConfigChange={onConfigChange} busy={busy} />
    {error && <p role="alert">{error}</p>}
    <button className="button button-primary" disabled={busy || destination?.loading || Boolean(destination?.deviceId && !destination.available) || !selected.length || workflow.status !== "active"} onClick={() => void launch()}>{busy && <Spinner />}{busy ? 'Starting…' : 'Run workflow'}</button>
  </section>;
}

function ProposalReview({ tenant, taskId, controlState = "active" }: { tenant: string; taskId: string; controlState?: string }) {
  const { user } = useAuth();
  const [run, setRun] = useState<{ id: string; state: string; result: Record<string, unknown> | null } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const loaded = await api<typeof run>(`/api/tenants/${tenant}/accounts/tasks/${taskId}/run`);
        if (!active) return;
        setRun(loaded); setLoadError("");
        if (loaded && !["completed", "failed"].includes(loaded.state)) timer = setTimeout(() => void poll(), 2000);
      } catch (e) { if (active) { setLoadError(e instanceof Error ? e.message : "Could not load workflow."); timer = setTimeout(() => void poll(), 5000); } }
    };
    void poll(); return () => { active = false; clearTimeout(timer); };
  }, [tenant, taskId, attempt, controlState]);
  async function approve() {
    if (!run || !user) return;
    setBusy(true); setError("");
    try {
      setRun(await api<typeof run>(`/api/tenants/${tenant}/accounts/runs/${run.id}/approve`, {
        method: "POST", body: JSON.stringify({ result: run.result }),
      }, user.csrf_token));
    } catch (e) { setError(e instanceof Error ? e.message : "Could not approve workflow."); }
    finally { setBusy(false); }
  }
  return <section className="accounts-panel">{error && <p role="alert">{error}</p>}
    {loadError && <RetryMessage onRetry={() => setAttempt(value => value + 1)}>{loadError}</RetryMessage>}
    {!run && !loadError && <LoadingIndicator>Loading workflow…</LoadingIndicator>}
    {typeof run?.result?.summary === 'string' && <p>{run.result.summary.slice(0,160)}</p>}
    {run?.state === "review" && <button className="button button-primary" disabled={busy || Boolean(loadError) || controlState !== "active"} onClick={() => void approve()}>{busy && <Spinner />}Approve result</button>}
  </section>;
}

function DestinationWorkflowLaunch(props: LaunchProps) {
  const destination = useDestinationPC(props.tenant, props.workflow.key);
  const proposal = presentationFor(props.workflow) === 'proposal';
  return <>
    <section className="accounts-panel workflow-destination-panel" aria-label="Workflow destination">
      <DestinationPCPicker devices={destination.devices} value={destination.state.deviceId}
        onChange={destination.select} required={!proposal} loading={destination.state.loading} />
      {destination.state.error && <><p role="alert">{destination.state.error}</p>
        <button className="button button-ghost" onClick={() => void destination.refresh()}>Retry loading PCs</button></>}
      <p className="quiet-state">{proposal ? 'This workflow processes selected files online. Choose a PC only when needed for its destination.' : presentationFor(props.workflow)==='accounts-statement' ? 'Statement interpretation runs online using Source Discovery. Verified Tally saves use this PC.' : 'Selected sources and destination saves use this PC. Bill recognition runs online.'}</p>
    </section>
    {proposal ? <ProposalLaunch {...props} destination={destination.state} /> : <AccountsLaunch {...props} destination={destination.state} />}
  </>;
}

/** New workflow presentations inherit destination selection without per-workflow PC pickers. */
export function WorkflowLaunch(props: LaunchProps) {
  const presentation = presentationFor(props.workflow);
  if (presentation === 'accounts-discovery') return <AccountsLaunch {...props} />;
  return presentation ? <DestinationWorkflowLaunch key={`${props.tenant}:${props.workflow.id}`} {...props} /> : null;
}

export function WorkflowQuickRun(props: LaunchProps) {
  const navigate = useNavigate();
  const presentation = presentationFor(props.workflow);
  if (presentation === "proposal") return <button className="button button-primary" onClick={() => navigate(`/${props.routeSlug}/workflows/${props.workflow.id}`)}>Run workflow</button>;
  return presentation ? <AccountsQuickRun {...props} /> : null;
}

export function WorkflowReview(props: { tenant: string; taskId: string; workflow?: Workflow; controlState?: string }) {
  return props.workflow && presentationFor(props.workflow) === "proposal"
    ? <ProposalReview tenant={props.tenant} taskId={props.taskId} controlState={props.controlState} />
    : <AccountsReview tenant={props.tenant} taskId={props.taskId} controlState={props.controlState} presentation={props.workflow ? presentationFor(props.workflow) : null} />;
}
