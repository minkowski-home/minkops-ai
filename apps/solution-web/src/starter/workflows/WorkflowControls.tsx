/** Product adapters around the same installed workflow lifecycle. */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Workflow } from "../api";
import { AccountsLaunch, AccountsQuickRun } from "../accounts/AccountsLaunch";
import { AccountsReview } from "../accounts/AccountsReview";
import type { Source } from "../accounts/types";
import { useAuth } from "../contexts/AuthContext";
import { presentationFor } from "./presentation";

type LaunchProps = { tenant: string; routeSlug: string; workflow: Workflow };

/** Schema-driven fallback for reviewed proposals using existing file grants. */
function ProposalLaunch({ tenant, routeSlug, workflow }: LaunchProps) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [sources, setSources] = useState<Source[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [values, setValues] = useState<Record<string, unknown>>({ ...workflow.run_defaults, ...workflow.config_values });
  useEffect(() => {
    let active = true;
    void api<Source[]>(`/api/tenants/${tenant}/accounts/sources`).then((loaded) => {
      if (active) setSources(loaded);
    }).catch((e: Error) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [tenant]);
  const properties = (workflow.run_schema?.properties ?? {}) as Record<string, { type?: string; title?: string; enum?: string[] }>;
  const fields = Object.entries(properties).filter(([key]) => key !== "source_ids");
  async function launch() {
    if (!user) return;
    setBusy(true); setError("");
    try {
      const run = await api<{ task_id: string }>(`/api/tenants/${tenant}/accounts/runs`, {
        method: "POST", body: JSON.stringify({ key: workflow.key, request_key: crypto.randomUUID(), file_ids: selected, config: values }),
      }, user.csrf_token);
      navigate(`/${routeSlug}/tasks/${run.task_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start workflow."); }
    finally { setBusy(false); }
  }
  return <section className="accounts-panel" aria-label="Run workflow">
    <h3>Run {workflow.name.toLowerCase()}</h3>
    {sources.map((source) => <fieldset key={source.id}><legend>{source.label}</legend>
      {source.files.map((file) => <label key={file.id}><input type="checkbox" checked={selected.includes(file.id)}
        onChange={(event) => setSelected((current) => event.target.checked ? [...current, file.id] : current.filter((id) => id !== file.id))} />{file.path}</label>)}
    </fieldset>)}
    {fields.map(([key, spec]) => <label className="config-field" key={key}>{spec.title ?? key}
      {spec.enum ? <select value={String(values[key] ?? "")} onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))}>
        <option value="">Choose</option>{spec.enum.map((value) => <option key={value} value={value}>{value}</option>)}</select>
        : spec.type === "boolean" ? <input type="checkbox" checked={Boolean(values[key])} onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.checked }))} />
          : <input type={spec.type === "integer" || spec.type === "number" ? "number" : "text"} value={String(values[key] ?? "")}
            onChange={(event) => setValues((current) => ({ ...current, [key]: spec.type === "integer" || spec.type === "number" ? Number(event.target.value) : event.target.value }))} />}
    </label>)}
    {error && <p role="alert">{error}</p>}
    <button className="button button-primary" disabled={busy || !selected.length || workflow.status !== "active"} onClick={() => void launch()}>Run workflow</button>
  </section>;
}

function ProposalReview({ tenant, taskId }: { tenant: string; taskId: string }) {
  const { user } = useAuth();
  const [run, setRun] = useState<{ id: string; state: string; result: Record<string, unknown> | null } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const loaded = await api<typeof run>(`/api/tenants/${tenant}/accounts/tasks/${taskId}/run`);
        if (!active) return;
        setRun(loaded);
        if (loaded && !["completed", "failed"].includes(loaded.state)) timer = setTimeout(() => void poll(), 2000);
      } catch (e) { if (active) setError(e instanceof Error ? e.message : "Could not load workflow."); }
    };
    void poll(); return () => { active = false; clearTimeout(timer); };
  }, [tenant, taskId]);
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
    {run?.result && <pre>{JSON.stringify(run.result, null, 2)}</pre>}
    {run?.state === "review" && <button className="button button-primary" disabled={busy} onClick={() => void approve()}>Approve result</button>}
  </section>;
}

export function WorkflowLaunch(props: LaunchProps) {
  const presentation = presentationFor(props.workflow);
  if (presentation === "proposal") return <ProposalLaunch {...props} />;
  return presentation ? <AccountsLaunch {...props} /> : null;
}

export function WorkflowQuickRun(props: LaunchProps) {
  const navigate = useNavigate();
  const presentation = presentationFor(props.workflow);
  if (presentation === "proposal") return <button className="button button-primary" onClick={() => navigate(`/${props.routeSlug}/workflows/${props.workflow.id}`)}>Run workflow</button>;
  return presentation ? <AccountsQuickRun {...props} /> : null;
}

export function WorkflowReview(props: { tenant: string; taskId: string; workflow?: Workflow }) {
  return props.workflow && presentationFor(props.workflow) === "proposal"
    ? <ProposalReview tenant={props.tenant} taskId={props.taskId} />
    : <AccountsReview tenant={props.tenant} taskId={props.taskId} />;
}
