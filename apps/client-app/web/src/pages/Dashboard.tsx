/**
 * Dashboard page — the root view after login.
 * Renders the AppShell which owns the sidebar + three-pane layout.
 * Content panels are added to the shell in subsequent commits.
 */

export default function Dashboard() {
  return (
    <div
      style={{
        height: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--color-bg)",
        color: "var(--color-text-muted)",
        fontFamily: "var(--font-main)",
        fontSize: "0.95rem"
      }}
    >
      Dashboard shell coming in next commit.
    </div>
  );
}
