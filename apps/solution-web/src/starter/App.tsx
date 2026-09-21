import { useMemo, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { ConsoleShell } from "./console/ConsoleShell";
import { AgentsScreen, DashboardScreen, PlaceholderScreen, TasksScreen } from "./console/screens";
import type { ActivityItem, ConsoleRoute, PresetWorkflow } from "./console/types";
import { MOCK_AGENTS, MOCK_AGENT_TEAMS } from "./mock/agents";
import { MOCK_INTERRUPTS } from "./mock/interrupts";
import { MOCK_TASKS } from "./mock/tasks";
import Login from "./pages/Login";
import { solution } from "@minkops/solution-manifest";
import { resolveStarterUi } from "./config";

const routeTitles: Record<ConsoleRoute, string> = {
  dashboard: "Dashboard", agents: "Agents", tasks: "Work", analytics: "Analytics", settings: "Settings"
};

function initialActivity(): ActivityItem[] {
  const messages = MOCK_TASKS.flatMap((task) => task.messages).map((message) => ({
    id: message.id,
    agentName: message.agentName ?? "You",
    summary: message.content.replace(/\*\*/g, "").split("\n")[0],
    time: new Date(message.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    outcome: (message.role === "agent" ? "done" : "working") as ActivityItem["outcome"]
  }));
  return [
    { id: "activity-image-to-excel", agentName: "Intake", summary: "WhatsApp images → Excel is planned. Connect a source and define the extraction schema to begin.", time: "Next", outcome: "waiting" },
    { id: "activity-transactions", agentName: "Ledger", summary: "Transaction reconciliation → warehouse is planned. Connect accounts and set a run interval to begin.", time: "Next", outcome: "waiting" },
    ...messages.reverse()
  ];
}

function ProtectedConsole() {
  const { user, isLoading } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [agents, setAgents] = useState(MOCK_AGENTS);
  const [team, setTeam] = useState(MOCK_AGENT_TEAMS[0]);
  const [interrupts, setInterrupts] = useState(MOCK_INTERRUPTS);
  const [activity, setActivity] = useState(initialActivity);
  const pendingCount = useMemo(() => interrupts.filter((item) => item.status === "pending").length, [interrupts]);

  if (isLoading) return null;
  if (!user) return <Navigate to="/login" replace />;

  const toggleAgent = (id: string) => setAgents((current) => current.map((agent) => {
    if (agent.id !== id) return agent;
    const enabled = !agent.enabled;
    return { ...agent, enabled, status: enabled ? "idle" : "disabled" };
  }));
  const toggleTeam = () => {
    const enabled = !team.enabled;
    setTeam((current) => ({ ...current, enabled }));
    setAgents((current) => current.map((agent) => agent.teamId === team.id ? { ...agent, enabled, status: enabled ? "idle" : "disabled" } : agent));
  };
  const resolve = (id: string, choice: string) => {
    const item = interrupts.find((candidate) => candidate.id === id);
    setInterrupts((current) => current.filter((candidate) => candidate.id !== id));
    if (item) setActivity((current) => [{ id: `resolved-${id}`, agentName: item.agentName, summary: `${choice}: ${item.title}`, time: "now", outcome: "working" }, ...current]);
  };
  const start = (workflow: PresetWorkflow) => {
    const agent = agents.find((candidate) => candidate.id === workflow.agentId);
    setActivity((current) => [{ id: `workflow-${Date.now()}`, agentName: agent?.name ?? "Imel", summary: workflow.outcome, time: "now", outcome: "working" }, ...current]);
  };
  const screen = (route: ConsoleRoute) => {
    if (route === "dashboard") return <DashboardScreen agents={agents} team={team} activity={activity} interrupts={interrupts} onToggleAgent={toggleAgent} onToggleTeam={toggleTeam} onResolve={resolve} onStart={start} />;
    if (route === "agents") return <AgentsScreen agents={agents} onToggleAgent={toggleAgent} />;
    if (route === "tasks") return <TasksScreen activity={activity} agents={agents} onStart={start} />;
    return <PlaceholderScreen name={routeTitles[route]} icon={route === "analytics" ? "analytics" : "settings"} />;
  };

  const solutionUi = resolveStarterUi(solution);

  return <Routes>
    {solutionUi.navigation.map((item) => (
      <Route key={item.route} path={`/${item.route}`} element={<ConsoleShell title={item.label} productName={solutionUi.productName} navigation={solutionUi.navigation.map((navigationItem) => ({ ...navigationItem }))} pendingCount={pendingCount} collapsed={collapsed} onToggleSidebar={() => setCollapsed((value) => !value)}>{screen(item.route)}</ConsoleShell>} />
    ))}
    <Route path="*" element={<Navigate to="/dashboard" replace />} />
  </Routes>;
}

function AppRoutes() {
  return <Routes><Route path="/login" element={<Login />} /><Route path="/*" element={<ProtectedConsole />} /></Routes>;
}

export default function App() {
  return <AuthProvider><BrowserRouter><AppRoutes /></BrowserRouter></AuthProvider>;
}
