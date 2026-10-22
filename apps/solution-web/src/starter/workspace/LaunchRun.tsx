import { useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Workflow, type Workspace } from "../api";
import { useAuth } from "../contexts/AuthContext";
import { Spinner } from "../components/Feedback";
import { useRead } from "../useRead";
import type { RunStatus } from "./review";

interface Company { id: string; name: string; guid: string; books_from: string }
interface Uploaded { files: { id: string; path: string }[] }

const REVIEW: Record<string, string> = { all_outputs: "Approve every entry", only_exceptions: "Only exceptions" };

/** Start a run of an installed workflow for one client: its files, and only the run settings the workflow declares. */
export function LaunchRun({ workspace, workflow, routeSlug }: { workspace: Workspace; workflow: Workflow; routeSlug: string }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const tenant = workspace.tenant.slug;
  const clients = workspace.clients ?? [];
  const [client, setClient] = useState(clients[0]?.slug ?? "");
  const [files, setFiles] = useState<File[]>([]);
  const [mapping, setMapping] = useState<File | null>(null);
  const [review, setReview] = useState("");
  const [company, setCompany] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  // One request key per launch: a retry after a lost response returns the same run instead of a second one.
  const request = useRef<string>("");
  const settings = ((workflow.run_schema ?? {}) as { properties?: Record<string, { enum?: string[] }> }).properties ?? {};
  const scope = `${user?.id ?? ""}:${tenant}`;
  const { data: companies = [] } = useRead<Company[]>(scope,
    `/api/tenants/${encodeURIComponent(tenant)}/clients/${encodeURIComponent(client)}/companies`,
    { enabled: Boolean(client && settings.company_mode) });
  if (workflow.status !== "active" || !workflow.run_schema || !clients.length) return null;

  async function start(event: FormEvent) {
    event.preventDefault();
    if (!user || busy || !files.length) return;
    const names = [...files, ...(mapping ? [mapping] : [])].map((file) => file.name);
    const repeated = names.find((name, n) => names.indexOf(name) !== n);
    if (repeated) {
      setMessage(`Two of the chosen files are named ${repeated}. Rename one, then start the run.`);
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const form = new FormData();
      const chosen = mapping ? [...files, mapping] : files;
      form.append("paths", JSON.stringify(chosen.map((file) => file.name)));
      form.append("label", `${workflow.name} files`);
      chosen.forEach((file) => form.append("files", file));
      const source = await api<Uploaded>(`/api/tenants/${encodeURIComponent(tenant)}/accounts/sources`,
        { method: "POST", body: form }, user.csrf_token);
      const byPath = new Map(source.files.map((file) => [file.path, file.id]));
      const config: Record<string, unknown> = {
        ...(review ? { review_mode: review } : {}),
        ...(company ? { company_mode: "locked", locked_company_guid: company } : {}),
        ...(mapping ? { branch_mapping_file_id: byPath.get(mapping.name) } : {}),
      };
      request.current ||= crypto.randomUUID();
      const launched = await api<RunStatus>(`/api/tenants/${encodeURIComponent(tenant)}/clients/${encodeURIComponent(client)}/runs`, {
        method: "POST", body: JSON.stringify({ workflow: workflow.key, file_ids: files.map((file) => byPath.get(file.name)),
          config, request_key: request.current }),
      }, user.csrf_token);
      request.current = "";
      navigate(`/${routeSlug}/tasks/${launched.run.task_id}`);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Could not start the run.");
    } finally {
      setBusy(false);
    }
  }

  return <form className="config-panel launch-panel" onSubmit={(event) => void start(event)}>
    <div className="section-heading"><div><h2>Start a run</h2><p>Choose the files to read, and whose books they belong to.</p></div></div>
    <div className="accounts-field-grid">
      {/* Shown even for one client, so the person starting the run sees whose books it reads. */}
      <label>Client<select aria-label="Client" value={client}
        onChange={(event) => { setClient(event.target.value); setCompany(""); }}>
        {clients.map((item) => <option key={item.slug} value={item.slug}>{item.name}</option>)}</select></label>
      <label>Files<input type="file" aria-label="Files" multiple required
        onChange={(event) => setFiles(Array.from(event.target.files ?? []))} /></label>
      {settings.branch_mapping_file_id && <label>Mapping file (optional)<input type="file" aria-label="Mapping file"
        onChange={(event) => setMapping(event.target.files?.[0] ?? null)} /></label>}
      {settings.review_mode?.enum && <label>Review<select aria-label="Review" value={review}
        onChange={(event) => setReview(event.target.value)}>
        <option value="">As the workflow is set</option>
        {settings.review_mode.enum.map((mode) => <option key={mode} value={mode}>{REVIEW[mode] ?? mode}</option>)}</select></label>}
      {settings.company_mode && <label>Company<select aria-label="Company" value={company}
        onChange={(event) => setCompany(event.target.value)}>
        <option value="">The company each bill is addressed to</option>
        {/* A company split by year keeps one GUID: each bill goes to the part whose books cover its date. */}
        {companies.filter((item, n) => companies.findIndex((other) => other.guid === item.guid) === n)
          .map((item) => <option key={item.guid} value={item.guid}>{item.name}</option>)}
      </select></label>}
    </div>
    <button className="button button-primary" disabled={busy || !files.length}>{busy && <Spinner />}{busy ? "Starting…" : "Start run"}</button>
    {message && <p role="alert" className="form-message">{message}</p>}
  </form>;
}
