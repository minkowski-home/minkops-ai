/**
 * Dashboard page — the root view after login.
 * Content panels are slotted into AppShell as they are built out in
 * subsequent commits. AppShell owns layout; panels own their own data.
 */

import AppShell from "../components/layout/AppShell";

export default function Dashboard() {
  return (
    <AppShell
      pageTitle="Dashboard"
      interruptCount={0}
    />
  );
}
