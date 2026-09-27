import { useMemo, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import "./index.css";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { ConsoleShell } from "./console/ConsoleShell";
import { AgentsScreen, DashboardScreen, WorkflowsScreen } from "./console/screens";
import type { ConsoleRoute } from "./console/types";
import { ACTIVATED_WORKFLOWS, HIRED_TEAMS, type ActiveTask, type AttentionItem, type WorkflowInstance } from "./workspace/initialState";
import Login from "./pages/Login";
import { resolveStarterUi } from "./config";
import { DEFAULT_SOLUTION_ID, getSolution } from "./solutions/registry";
import type { SolutionManifest } from "@minkops/solution-contracts";

const routeTitles: Record<ConsoleRoute, string> = {
  dashboard: "Dashboard",
  agents: "Agents",
  workflows: "Workflows"
};

function ProtectedConsole({ solution }: { solution: SolutionManifest }) {
  const { user, isLoading } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [workflows, setWorkflows] = useState<WorkflowInstance[]>(ACTIVATED_WORKFLOWS);
  const [activeTasks, setActiveTasks] = useState<ActiveTask[]>([]);
  const [attention, setAttention] = useState<AttentionItem[]>([]);
  const [history, setHistory] = useState<string[]>([]);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const pendingCount = useMemo(() => attention.length, [attention]);
  const solutionUi = resolveStarterUi(solution);

  if (isLoading) return null;
  if (!user) return <Navigate to={`/${solution.id}/login`} replace />;

const start = (workflow: WorkflowInstance) => {
  if (activeTasks.some((task) => task.workflowId === workflow.id)) return;
  setWorkflowError(null);

  // Keep normal behaviour for other workflows
  if (workflow.presetId !== "whatsapp-image-to-excel") {
    setActiveTasks((current) => [
      ...current,
      {
        id: `task-${Date.now()}`,
        workflowId: workflow.id,
        title: workflow.title,
        state: "running"
      }
    ]);

    return;
  }

  // Open image picker for WhatsApp Image to Excel
  const input = document.createElement("input");

  input.type = "file";
  input.accept = "image/*";

  input.onchange = async () => {
    const file = input.files?.[0];

    if (!file) return;

    const taskId = `task-${Date.now()}`;

    setActiveTasks((current) => [
      ...current,
      {
        id: taskId,
        workflowId: workflow.id,
        title: workflow.title,
        state: "running"
      }
    ]);

    try {
      const formData = new FormData();

      formData.append("file", file);

      const response = await fetch(
        "http://localhost:8000/extract_image",
        {
          method: "POST",
          body: formData
        }
      );

      if (!response.ok) {
        const body = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(body?.detail || `Image processing failed (HTTP ${response.status}).`);
      }

      const result = await response.json();

      console.log("Image processing result:", result);

      setActiveTasks((current) =>
        current.filter((task) => task.id !== taskId)
      );

      setHistory((current) => [
        `Completed: ${file.name}`,
        ...current
      ]);

    } catch (error) {
      console.error("Image processing error:", error);

      setActiveTasks((current) =>
        current.filter((task) => task.id !== taskId)
      );

      const message = error instanceof Error ? error.message : "Image processing failed. Check that the API is running.";
      setWorkflowError(message);
      setHistory((current) => [`Failed: ${file.name}`, ...current]);
    }
  };

  input.click();
};

  const updateWorkflow = (id: string, configuration: Record<string, string>) => {
    setWorkflows((current) => current.map((workflow) => workflow.id === id ? { ...workflow, configuration } : workflow));
  };
  const addInstance = (workflow: WorkflowInstance) => {
    const number = workflows.filter((candidate) => candidate.presetId === workflow.presetId).length + 1;
    setWorkflows((current) => [...current, {
      ...workflow,
      id: `${workflow.presetId}-${number}`,
      title: `${workflow.title} ${number}`,
      configuration: { ...workflow.configuration }
    }]);
  };
  const resolve = (id: string, decision: string) => {
    const item = attention.find((candidate) => candidate.id === id);
    setAttention((current) => current.filter((candidate) => candidate.id !== id));
    if (item) setHistory((current) => [`${decision}: ${item.title}`, ...current]);
  };
  const screen = (route: ConsoleRoute) => {
    if (route === "dashboard") {
      return <DashboardScreen workflows={workflows} activeTasks={activeTasks} attention={attention} history={history} workflowError={workflowError} onStart={start} onResolve={resolve} onUpdate={updateWorkflow} onAddInstance={addInstance} />;
    }
    if (route === "agents") return <AgentsScreen teams={HIRED_TEAMS} />;
    return <WorkflowsScreen workflows={workflows} onUpdate={updateWorkflow} onAddInstance={addInstance} onStart={start} />;
  };

  return <Routes>
    {solutionUi.navigation.map((item) => (
      <Route key={item.route} path={`/${item.route}`} element={
        <ConsoleShell
          title={routeTitles[item.route]}
          productName={solutionUi.productName}
          navigation={solutionUi.navigation.map((navigationItem) => ({ ...navigationItem }))}
          pendingCount={pendingCount}
          collapsed={collapsed}
          onToggleSidebar={() => setCollapsed((value) => !value)}
        >{screen(item.route)}</ConsoleShell>
      } />
    ))}
    <Route path="*" element={<Navigate to={`/${solution.id}/dashboard`} replace />} />
  </Routes>;
}

function AppRoutes() {
  const { solutionId } = useParams();
  const solution = solutionId ? getSolution(solutionId) : undefined;
  if (!solution) return <Navigate to={`/${DEFAULT_SOLUTION_ID}/dashboard`} replace />;

  return <Routes>
    <Route path="login" element={<Login solution={solution} />} />
    <Route path="*" element={<ProtectedConsole solution={solution} />} />
  </Routes>;
}

export default function App() {
  return <AuthProvider><BrowserRouter><Routes>
    <Route path="/:solutionId/*" element={<AppRoutes />} />
    <Route path="*" element={<Navigate to={`/${DEFAULT_SOLUTION_ID}/dashboard`} replace />} />
  </Routes></BrowserRouter></AuthProvider>;
}
