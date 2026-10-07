import { useEffect, useMemo, useState, type CSSProperties, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, type Employee, type SettingSpec, type Task,
  type Workflow, type Workspace } from "../api";
import { useAuth } from "../contexts/AuthContext";
import { WorkflowLaunch, WorkflowQuickRun, WorkflowReview } from "../workflows/WorkflowControls";
import { presentationFor } from "../workflows/presentation";
import { greetingFor, groupWorkflows, sortWorkflows, type WorkflowGroup,
  type WorkflowSort } from "../workspace/presentation";
import { taskSnapshot, type TaskDetails } from "../workspace/taskDetail";
import { Icon } from "./Icon";
import { progressView, type ProgressMode } from '../workspace/progress';

const statusText: Record<string, string> = {
  active: "Active", inactive: "Inactive", paused: "Paused", planned: "Planned",
  running: "In progress", attention: "Needs attention", handoff: "Save pending",
  completed: "Completed", failed: "Failed",
};

function Status({ value }: { value: string }) {
  return <span className={`status status--${value}`}>{statusText[value] ?? value}</span>;
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <div className="empty-state"><div className="empty-state__icon"><Icon name="tasks" size={22} /></div>
    <h3>{title}</h3><p>{detail}</p></div>;
}

function ConfigPanel({ item, kind, tenantSlug, canEdit, onSaved }: {
  item: Employee | Workflow;
  kind: "employees" | "workflows";
  tenantSlug: string;
  canEdit: boolean;
  onSaved: () => Promise<void>;
}) {
  const { user } = useAuth();
  const [values, setValues] = useState(item.config_values);
  const [status, setStatus] = useState(item.status);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const fields = Object.entries(item.config_schema.properties);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!user || !canEdit) return;
    setBusy(true);
    setMessage("");
    try {
      await api(`/api/tenants/${encodeURIComponent(tenantSlug)}/${kind}/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status, config_values: values }),
      }, user.csrf_token);
      await onSaved();
      setMessage("Settings saved.");
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Could not save settings.");
    } finally { setBusy(false); }
  }
  return <form className="config-panel" onSubmit={(event) => void save(event)}>
    <div className="section-heading"><div><h2>Settings</h2><p>Simple controls for this {kind === "employees" ? "employee" : "workflow"}.</p></div>
      {!canEdit && <span className="read-only-note">View only</span>}
    </div>
    <label className="config-field"><span>Status</span>
      <select value={status} disabled={!canEdit} onChange={(event) => setStatus(event.target.value as typeof status)}>
        {(kind === "employees" ? ["active", "inactive"] : ["active", "paused", "planned"])
          .map((option) => <option key={option} value={option}>{statusText[option]}</option>)}
      </select>
    </label>
    {fields.map(([key, spec]: [string, SettingSpec]) => <label className="config-field" key={key}>
      <span>{spec.title ?? key}</span>
      {spec.description && <small>{spec.description}</small>}
      {spec.type === "boolean"
        ? <span className="switch-row"><input type="checkbox" checked={Boolean(values[key])}
          disabled={!canEdit} onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.checked }))} />
          {values[key] ? "On" : "Off"}</span>
        : spec.enum
          ? <select value={String(values[key] ?? "")} disabled={!canEdit}
            onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))}>
              {spec.enum.map((option) => <option key={String(option)} value={String(option)}>{option}</option>)}
            </select>
          : <input type={spec.type === "integer" ? "number" : "text"} value={String(values[key] ?? "")}
            disabled={!canEdit} onChange={(event) => setValues((current) => ({
              ...current, [key]: spec.type === "integer" ? Number(event.target.value) : event.target.value,
            }))} />}
    </label>)}
    {!fields.length && <p className="quiet-state">No additional controls for this item yet.</p>}
    {canEdit && <button className="button button-primary" disabled={busy}>{busy ? "Saving…" : "Save settings"}</button>}
    {message && <p role="status" className="form-message">{message}</p>}
  </form>;
}

export function EmployeesScreen({ workspace, routeSlug }: { workspace: Workspace; routeSlug: string }) {
  const active = workspace.employees.filter((employee) => employee.status === "active");
  return <section className="route-screen">
    <header className="route-heading"><div><h2>Employees</h2><p>People-shaped help for the work your team has activated.</p></div>
      <span className="route-count">{active.length} active</span></header>
    {active.length ? <div className="employee-list">{active.map((employee) => {
      const workflows = workspace.workflows.filter((workflow) => workflow.employee_ids.includes(employee.id)
        && workflow.status === "active");
      return <Link className="employee-card" key={employee.id} to={`/${routeSlug}/employees/${employee.id}`}>
        <div className="employee-mark"><Icon name="agents" size={22} /></div>
        <div><h3>{employee.name}</h3><p>{employee.description}</p>
          <div className="employee-workflows"><span>Active workflows</span>
            <strong>{workflows.length ? workflows.map((workflow) => workflow.name).join(" · ") : "None yet"}</strong>
          </div>
        </div><Icon name="chevronRight" size={17} />
      </Link>;
    })}</div> : <EmptyState title="No active employees yet"
      detail="Employees will appear here when your workspace activates them." />}
  </section>;
}

export function EmployeeDetail({ workspace, routeSlug, id, onSaved }: {
  workspace: Workspace; routeSlug: string; id: string; onSaved: () => Promise<void>;
}) {
  const item = workspace.employees.find((employee) => employee.id === id);
  if (!item) return <section className="route-screen"><EmptyState title="Employee not found" detail="This employee is not in your workspace." /></section>;
  const linked = workspace.workflows.filter((workflow) => workflow.employee_ids.includes(item.id));
  return <section className="route-screen detail-screen">
    <Link className="back-link" to={`/${routeSlug}/employees`}>← Employees</Link>
    <header className="detail-heading"><div><h2>{item.name}</h2><p>{item.description}</p></div><Status value={item.status} /></header>
    <div className="detail-grid"><ConfigPanel key={item.id} item={item} kind="employees" tenantSlug={workspace.tenant.slug}
      canEdit={workspace.can_edit} onSaved={onSaved} />
      <aside className="related-panel"><h2>Workflows</h2>
        {linked.length ? linked.map((workflow) => <Link key={workflow.id}
          to={`/${routeSlug}/workflows/${workflow.id}`} className="related-row">
          <span>{workflow.name}</span><Status value={workflow.status} />
        </Link>) : <p className="quiet-state">No workflows linked yet.</p>}
      </aside></div>
  </section>;
}

export function WorkflowsScreen({ workspace, routeSlug }: { workspace: Workspace; routeSlug: string }) {
  const [group, setGroup] = useState<WorkflowGroup>("none");
  const [sort, setSort] = useState<WorkflowSort>("name");
  const [filter, setFilter] = useState("all");
  const workflows = useMemo(() => sortWorkflows(workspace.workflows.filter((item) =>
    filter === "all" || item.status === filter), sort), [workspace.workflows, filter, sort]);
  const groups = groupWorkflows(workflows, workspace.employees, group);
  return <section className="route-screen">
    <header className="route-heading"><div><h2>Workflows</h2><p>Work available, paused, and being planned.</p></div>
      <span className="route-count">{workspace.workflows.length} total</span></header>
    <div className="list-controls">
      <label>Show <select value={filter} onChange={(event) => setFilter(event.target.value)}>
        <option value="all">All statuses</option><option value="active">Active</option>
        <option value="paused">Paused</option><option value="planned">Planned</option>
      </select></label>
      <label>Group by <select value={group} onChange={(event) => setGroup(event.target.value as WorkflowGroup)}>
        <option value="none">None</option><option value="employee">Employee</option>
        <option value="status">Status</option>
      </select></label>
      <label>Sort by <select value={sort} onChange={(event) => setSort(event.target.value as WorkflowSort)}>
        <option value="name">Name</option><option value="status">Status</option>
      </select></label>
    </div>
    {workflows.length ? groups.map((section) => <section className="workflow-group" key={section.label}>
      {group !== "none" && <h3>{section.label}</h3>}
      <div className="workflow-list">{section.items.map((workflow) => <Link
        key={workflow.id} to={`/${routeSlug}/workflows/${workflow.id}`} className="workflow-row">
        <div><h4>{workflow.name}</h4><p>{workflow.description}</p>
          <small>{workflow.employee_ids.map((id) => workspace.employees.find((employee) => employee.id === id)?.name)
            .filter(Boolean).join(" · ") || "Unassigned"}</small>
        </div><Status value={workflow.status} /><Icon name="chevronRight" size={17} />
      </Link>)}</div>
    </section>) : <EmptyState title="No workflows here" detail="Try another filter, or check back when a workflow is added." />}
  </section>;
}

export function WorkflowDetail({ workspace, routeSlug, id, onSaved }: {
  workspace: Workspace; routeSlug: string; id: string; onSaved: () => Promise<void>;
}) {
  const item = workspace.workflows.find((workflow) => workflow.id === id);
  if (!item) return <section className="route-screen"><EmptyState title="Workflow not found" detail="This workflow is not in your workspace." /></section>;
  const linked = workspace.employees.filter((employee) => item.employee_ids.includes(employee.id));
  return <section className="route-screen detail-screen">
    <Link className="back-link" to={`/${routeSlug}/workflows`}>← Workflows</Link>
    <header className="detail-heading"><div><h2>{item.name}</h2><p>{item.description}</p></div><Status value={item.status} /></header>
    {presentationFor(item) && <WorkflowLaunch key={item.id}
      tenant={workspace.tenant.slug} routeSlug={routeSlug} workflow={item} />}
    <div className="detail-grid"><ConfigPanel key={item.id} item={item} kind="workflows" tenantSlug={workspace.tenant.slug}
      canEdit={workspace.can_edit} onSaved={onSaved} />
      <aside className="related-panel"><h2>Employees</h2>
        {linked.map((employee) => <Link key={employee.id} to={`/${routeSlug}/employees/${employee.id}`}
          className="related-row"><span>{employee.name}</span><Icon name="chevronRight" size={16} /></Link>)}
        {!linked.length && <p className="quiet-state">No employee linked yet.</p>}
      </aside></div>
  </section>;
}

function TaskLinks({ title, tasks, routeSlug }: { title: string; tasks: Task[]; routeSlug: string }) {
  return <section className="attention-section"><div className="pane-title"><span>{title}</span><span>{tasks.length}</span></div>
    {tasks.length ? <div className="pane-items">{tasks.map((task) => <Link
      className="pane-task" key={task.id} to={`/${routeSlug}/tasks/${task.id}`}>
      <span className={`task-dot task-dot--${task.status}`} />
      <span><strong>{task.title}</strong><small>{task.summary}</small></span>
      <Icon name="chevronRight" size={15} />
    </Link>)}</div> : <p className="quiet-state">Nothing here right now.</p>}
  </section>;
}

export function DashboardScreen({ workspace, routeSlug, onRunTest, workflowError }: {
  workspace: Workspace; routeSlug: string; onRunTest: (workflow: Workflow) => void; workflowError: string;
}) {
  const { user } = useAuth();
  const [paneWidth, setPaneWidth] = useState(340);
  const active = workspace.workflows.filter((workflow) => workflow.status === "active");
  const tasks = workspace.tasks;
  const welcome = greetingFor(user?.name ?? "there", new Date().toLocaleDateString("en-CA"));
  const resize = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const separator = event.currentTarget;
    separator.setPointerCapture(event.pointerId);
    const move = (moveEvent: PointerEvent) => setPaneWidth(Math.min(500, Math.max(260, window.innerWidth - moveEvent.clientX)));
    const stop = () => {
      separator.removeEventListener("pointermove", move);
      separator.removeEventListener("pointerup", stop);
    };
    separator.addEventListener("pointermove", move);
    separator.addEventListener("pointerup", stop, { once: true });
  };
  return <div className="dashboard-workspace" style={{ "--pane-width": `${paneWidth}px` } as CSSProperties}>
    <main className="dashboard-main"><header className="launchpad-heading">
      <h2>{welcome}</h2><p>Your work and decisions are in one place.</p></header>
      {workflowError && <p role="alert" className="workflow-feedback">{workflowError}</p>}
      <section className="dashboard-section"><div className="section-heading"><div><h3>Ready workflows</h3>
        <p>Start with the work that is available today.</p></div></div>
        {active.length ? <div className="workflow-launch-grid">{active.map((workflow) =>
          <article className="workflow-launch-card" key={workflow.id}>
            <div className="workflow-launch-card__mark"><Icon name="tasks" size={20} /></div>
            <div><h4>{workflow.name}</h4><p>{workflow.description}</p></div>
            <footer><Link className="button button-ghost" to={`/${routeSlug}/workflows/${workflow.id}`}>View details</Link>
              {workspace.tenant.slug === "mock-tenant" && workflow.key === "image-to-excel-test"
                && <button className="button button-primary" onClick={() => onRunTest(workflow)}>Run test</button>}
              {presentationFor(workflow) && <WorkflowQuickRun
                tenant={workspace.tenant.slug} routeSlug={routeSlug} workflow={workflow} />}
            </footer>
          </article>)}</div>
          : <EmptyState title="Your workspace starts here" detail="Activated workflows will appear when your team is ready." />}
      </section>
    </main>
    {/* An adjustable ARIA separator is interactive even though this lint version treats it as static. */}
    {/* eslint-disable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */}
    <div className="pane-resizer" role="separator" aria-label="Resize activity pane"
      aria-orientation="vertical" aria-valuemin={260} aria-valuemax={500} aria-valuenow={paneWidth}
      tabIndex={0} onPointerDown={resize}
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft") setPaneWidth((value) => Math.min(500, value + 20));
        if (event.key === "ArrowRight") setPaneWidth((value) => Math.max(260, value - 20));
      }} />
    {/* eslint-enable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */}
    <aside className="attention-pane" aria-label="Activity">
      <div className="activity-heading"><h3>Activity</h3><p>What is happening now</p></div>
      <TaskLinks title="Active tasks" tasks={tasks.filter((task) => task.status === "running")} routeSlug={routeSlug} />
      <TaskLinks title="Needs attention" tasks={tasks.filter((task) => task.status === "attention")} routeSlug={routeSlug} />
      <TaskLinks title="Handoffs" tasks={tasks.filter((task) => task.status === "handoff")} routeSlug={routeSlug} />
      <TaskLinks title="Recent outcomes" tasks={tasks.filter((task) => ["completed", "failed"].includes(task.status))} routeSlug={routeSlug} />
    </aside>
  </div>;
}

export function TaskDetail({ workspace, routeSlug, id }: {
  workspace: Workspace; routeSlug: string; id: string;
}) {
  const snapshot = useMemo(() => taskSnapshot(workspace.tasks, id), [workspace.tasks, id]);
  const [detail, setDetail] = useState<TaskDetails | null>(() => snapshot);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    setDetail((current) => current?.id === id ? current : snapshot);
    setError("");
    setLoading(true);
    const poll = async () => {
      try {
        const result = await api<TaskDetails>(`/api/tenants/${workspace.tenant.slug}/tasks/${id}`);
        if (!active) return;
        setDetail(result); setError("");
        if (!["completed", "failed"].includes(result.status)) timer = setTimeout(() => void poll(), 2000);
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "Could not load task.");
      } finally { if (active) setLoading(false); }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [workspace.tenant.slug, id, snapshot, attempt]);
  if (error && !detail) return <section className="route-screen">
    <h2>Task unavailable</h2><p role="alert">{error}</p>
    <button className="button button-ghost" onClick={() => setAttempt((value) => value + 1)}>Retry</button>
  </section>;
  if (!detail) return <section className="route-screen"><p>Loading task…</p></section>;
  const workflow = workspace.workflows.find((w) => w.id === detail.workflow_id);
  const presentation = workflow ? presentationFor(workflow) : null;
  const mode: ProgressMode = presentation === "accounts-bill" ? "bill-entry" : presentation === "accounts-discovery" ? "source-discovery"
    : !detail.workflow_id && detail.title === 'Check Tally connection' ? 'tally.probe'
      : !detail.workflow_id && detail.title === 'Refresh local folder' ? 'files.refresh' : 'simple';
  const progress = progressView(detail, mode);
  return <section className="route-screen detail-screen task-detail">
    <Link className="back-link" to={`/${routeSlug}/dashboard`}>← Dashboard</Link>
    <header className="detail-heading"><div><h2>{detail.title}</h2></div>
      <Status value={detail.status} /></header>
    <div className="task-progress">
      <div className={`task-stage-mark${progress.finished ? ' is-finished' : ''}`} aria-hidden="true"><Icon name={progress.finished ? 'check' : detail.status === 'failed' ? 'x' : 'tasks'} size={28} /></div>
      <div className="task-stage-copy"><h3>{progress.label}</h3><p>{detail.summary}</p>
        <ol className="task-stage-list" aria-label="Task stages">{progress.stages.map((stage, index) => <li key={stage}
          className={index < progress.current || progress.finished ? 'is-done' : index === progress.current ? 'is-current' : ''}
          aria-current={!progress.finished && index === progress.current ? 'step' : undefined}>
          <span aria-hidden="true">{index < progress.current || progress.finished ? <Icon name="check" size={14} /> : index + 1}</span>{stage}</li>)}</ol>
      </div>
    </div>
    <WorkflowReview key={id} tenant={workspace.tenant.slug} taskId={id} workflow={workflow} />
    <details className="timeline"><summary>Activity details · {detail.events.length} updates</summary>
      {error && <p role="alert" className="form-message">The latest timeline could not load. {error} <button
        className="button button-ghost" onClick={() => setAttempt((value) => value + 1)}>Retry</button></p>}
      {loading && detail.events.length === 0 && <p className="quiet-state">Loading timeline…</p>}
      {!loading && !error && detail.events.length === 0 && <p className="quiet-state">No activity recorded yet.</p>}
      <ol>{detail.events.map((event) => <li key={event.id}>
        <span className="timeline-point" /><div><strong>{event.summary}</strong>
          <small>{new Date(event.created_at).toLocaleString()}</small>
        </div></li>)}</ol>
    </details>
  </section>;
}

interface JoinRequest {
  id: string; name: string; email: string;
}

export function AccessScreen({ workspace, onSaved }: { workspace: Workspace; onSaved: () => Promise<void> }) {
  const { user } = useAuth();
  const [requests, setRequests] = useState<JoinRequest[]>([]);
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState("");
  const [inviteLink, setInviteLink] = useState("");
  const tenant = workspace.tenant.slug;
  useEffect(() => {
    if (!workspace.can_edit) return;
    void api<JoinRequest[]>(`/api/tenants/${tenant}/join-requests`).then(setRequests).catch(() => setRequests([]));
  }, [tenant, workspace.can_edit]);
  async function approve(id: string) {
    if (!user) return;
    try {
      await api(`/api/tenants/${tenant}/join-requests/${id}/approve`, { method: "POST" }, user.csrf_token);
      setRequests((current) => current.filter((item) => item.id !== id));
      setStatus("Access approved.");
      await onSaved();
    } catch (caught) { setStatus(caught instanceof Error ? caught.message : "Could not approve."); }
  }
  async function invite(event: FormEvent) {
    event.preventDefault();
    if (!user) return;
    try {
      const result = await api<{ invitation_link?: string }>(`/api/tenants/${tenant}/invitations`, {
        method: "POST", body: JSON.stringify({ email, role: "member" }),
      }, user.csrf_token);
      setStatus("Invitation sent.");
      setInviteLink(result.invitation_link ?? "");
      setEmail("");
    } catch (caught) { setStatus(caught instanceof Error ? caught.message : "Could not invite."); }
  }
  return <section className="route-screen"><header className="route-heading"><div>
    <h2>Workspace access</h2><p>Approve requests or invite a teammate.</p></div></header>
    <div className="detail-grid"><section className="related-panel"><h3>Pending requests</h3>
      {requests.length ? requests.map((item) => <div className="related-row" key={item.id}>
        <span>{item.name}<small>{item.email}</small></span>
        <button className="button button-ghost" onClick={() => void approve(item.id)}>Approve</button>
      </div>) : <p className="quiet-state">No requests waiting.</p>}
    </section>
      <form className="config-panel" onSubmit={(event) => void invite(event)}><h3>Invite someone</h3>
        <label className="config-field">Email<input type="email" required value={email}
          onChange={(event) => setEmail(event.target.value)} /></label>
        <button className="button button-primary">Send invitation</button>
        {inviteLink && <p className="form-message">Local invite link: <a href={inviteLink}>{inviteLink}</a></p>}
      </form>
    </div>
    {status && <p role="status" className="form-message">{status}</p>}
  </section>;
}
