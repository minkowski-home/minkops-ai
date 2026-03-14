/**
 * Dashboard page — the root view after login.
 * Content panels are slotted into AppShell as they are built out in
 * subsequent commits. AppShell owns layout; panels own their own data.
 */

import AppShell from "../components/layout/AppShell";
import AgentPanel from "../components/agents/AgentPanel";
import { MOCK_INTERRUPTS } from "../mock/interrupts";

export default function Dashboard() {
  const pendingInterrupts = MOCK_INTERRUPTS.filter((i) => i.status === "pending").length;

  return (
    <AppShell
      pageTitle="Dashboard"
      interruptCount={pendingInterrupts}
      leftPane={<AgentPanel />}
    />
  );
}
