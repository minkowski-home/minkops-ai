/**
 * Dashboard page — the root view after login.
 * Content panels are slotted into AppShell as they are built out in
 * subsequent commits. AppShell owns layout; panels own their own data.
 */

import AppShell from "../components/layout/AppShell";
import AgentPanel from "../components/agents/AgentPanel";
import TaskPanel from "../components/task/TaskPanel";
import InterruptPanel from "../components/interrupt/InterruptPanel";
import ThemeSelector from "../components/theme/ThemeSelector";
import { MOCK_INTERRUPTS } from "../mock/interrupts";

interface DashboardProps {
  pageTitle?: string;
}

export default function Dashboard({ pageTitle = "Dashboard" }: DashboardProps) {
  const pendingInterrupts = MOCK_INTERRUPTS.filter((i) => i.status === "pending").length;

  return (
    <AppShell
      pageTitle={pageTitle}
      interruptCount={pendingInterrupts}
      leftPane={<AgentPanel />}
      centerPane={<TaskPanel />}
      rightPane={<InterruptPanel />}
      headerRight={<ThemeSelector />}
    />
  );
}
