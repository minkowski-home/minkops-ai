import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import "./index.css";
import { api, tenantSlug, type Workflow, type Workspace } from "./api";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { ConsoleShell } from "./console/ConsoleShell";
import { AccessScreen, DashboardScreen, EmployeeDetail, EmployeesScreen, TaskDetail,
  WorkflowDetail, WorkflowsScreen } from "./console/screens";
import Login, { InvitePage, JoinPage, SignupPage, VerifyPage } from "./pages/Login";
import { ThemeProvider } from "./theme/ThemeContext";
import { DevicesScreen } from './desktop/DevicesScreen';

function HomeRedirect() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <main className="loading-state">Opening Minkops…</main>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.memberships[0]) return <Navigate to={`/${user.memberships[0].slug}/dashboard`} replace />;
  if (user.is_platform_admin) return <Navigate to="/pr-infra/dashboard" replace />;
  return <Navigate to="/join" replace />;
}

function Console() {
  const { workspaceId } = useParams();
  const location = useLocation();
  const { user, isLoading } = useAuth();
  const routeSlug = workspaceId ?? "pr-infra";
  const slug = tenantSlug(routeSlug);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [workflowError, setWorkflowError] = useState("");

  const refreshWorkspace = useCallback(async () => {
    try {
      const loaded = await api<Workspace>(`/api/tenants/${encodeURIComponent(slug)}/workspace`);
      setWorkspace(loaded);
      setError("");
    } catch (caught) {
      setWorkspace(null);
      setError(caught instanceof Error ? caught.message : "Could not open workspace.");
    }
  }, [slug]);

  useEffect(() => {
    if (user) void refreshWorkspace();
  }, [user, refreshWorkspace, location.pathname]);

  useEffect(() => {
    if (!user || !location.pathname.endsWith('/dashboard')) return;
    // Durable workflow state changes independently of this browser. Refresh
    // the activity queue while it is visible, including after returning from review.
    const timer = setInterval(() => void refreshWorkspace(), 4000);
    return () => clearInterval(timer);
  }, [user, refreshWorkspace, location.pathname]);

  if (isLoading) return <main className="loading-state">Opening Minkops…</main>;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  if (error) return <main className="access-state"><h1>Workspace unavailable</h1><p>{error}</p>
    <Link className="button button-primary" to="/join">Request access</Link></main>;
  if (!workspace) return <main className="loading-state">Loading workspace…</main>;

  function runTest(workflow: Workflow) {
    setWorkflowError("");
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file || !user) return;
      const form = new FormData();
      form.append("file", file);
      try {
        await api(`/api/tenants/${slug}/test/image-to-excel`, {
          method: "POST", body: form,
        }, user.csrf_token);
        await refreshWorkspace();
      } catch (caught) {
        setWorkflowError(caught instanceof Error ? caught.message : "Test run failed.");
      }
    };
    input.click();
    void workflow;
  }

  const path = location.pathname;
  const title = path.includes("/employees/") ? "Employee" : path.endsWith("/employees") ? "Employees"
    : path.includes("/workflows/") ? "Workflow" : path.endsWith("/workflows") ? "Workflows"
      : path.includes("/tasks/") ? "Task" : path.endsWith("/connections") ? "Connections" : path.endsWith("/access") ? "Access" : "Dashboard";
  const attentionCount = workspace.tasks.filter((task) => task.status === "attention").length;

  return <ConsoleShell title={title} tenantName={workspace.tenant.name} routeSlug={routeSlug}
    pendingCount={attentionCount} collapsed={collapsed} onToggleSidebar={() => setCollapsed((value) => !value)}
    canEdit={workspace.can_edit}>
    <Routes>
      <Route path="dashboard" element={<DashboardScreen workspace={workspace} routeSlug={routeSlug}
        onRunTest={runTest} workflowError={workflowError} />} />
      <Route path="employees" element={<EmployeesScreen workspace={workspace} routeSlug={routeSlug} />} />
      <Route path="employees/:id" element={<EmployeeRoute workspace={workspace} routeSlug={routeSlug}
        onSaved={refreshWorkspace} />} />
      <Route path="workflows" element={<WorkflowsScreen workspace={workspace} routeSlug={routeSlug} />} />
      <Route path="workflows/:id" element={<WorkflowRoute workspace={workspace} routeSlug={routeSlug}
        onSaved={refreshWorkspace} />} />
      <Route path="tasks/:id" element={<TaskRoute workspace={workspace} routeSlug={routeSlug} />} />
      <Route path="connections" element={<DevicesScreen tenant={slug} routeSlug={routeSlug} />} />
      <Route path="access" element={workspace.can_edit
        ? <AccessScreen workspace={workspace} onSaved={refreshWorkspace} />
        : <Navigate to="dashboard" replace />} />
      <Route path="login" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="dashboard" replace />} />
    </Routes>
  </ConsoleShell>;
}

function EmployeeRoute({ workspace, routeSlug, onSaved }: {
  workspace: Workspace; routeSlug: string; onSaved: () => Promise<void>;
}) {
  const { id = "" } = useParams();
  return <EmployeeDetail workspace={workspace} routeSlug={routeSlug} id={id} onSaved={onSaved} />;
}

function WorkflowRoute({ workspace, routeSlug, onSaved }: {
  workspace: Workspace; routeSlug: string; onSaved: () => Promise<void>;
}) {
  const { id = "" } = useParams();
  return <WorkflowDetail workspace={workspace} routeSlug={routeSlug} id={id} onSaved={onSaved} />;
}

function TaskRoute({ workspace, routeSlug }: { workspace: Workspace; routeSlug: string }) {
  const { id = "" } = useParams();
  return <TaskDetail key={id} workspace={workspace} routeSlug={routeSlug} id={id} />;
}

export default function App() {
  return <ThemeProvider><AuthProvider><BrowserRouter><Routes>
    <Route path="/" element={<HomeRedirect />} />
    <Route path="/login" element={<Login />} />
    <Route path="/signup" element={<SignupPage />} />
    <Route path="/verify/:token" element={<VerifyPage />} />
    <Route path="/invite/:token" element={<InvitePage />} />
    <Route path="/join" element={<JoinPage />} />
    <Route path="/:workspaceId/*" element={<Console />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></BrowserRouter></AuthProvider></ThemeProvider>;
}
