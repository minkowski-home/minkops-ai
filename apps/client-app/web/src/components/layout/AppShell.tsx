import { useState } from "react";
import { useAuth } from "../../contexts/AuthContext";
import Sidebar from "./Sidebar";
import { IconBell } from "../icons";
import "./AppShell.css";

interface AppShellProps {
  /** Left pane content — agent list. */
  leftPane?: React.ReactNode;
  /** Center pane content — task/chat area. */
  centerPane?: React.ReactNode;
  /** Right pane content — human interrupt queue. */
  rightPane?: React.ReactNode;
  /** Controls injected into the header right slot (e.g. ThemeSelector). */
  headerRight?: React.ReactNode;
  /** Page title shown in the header breadcrumb area. */
  pageTitle?: string;
  /** Number of pending interrupts to show on the bell badge. */
  interruptCount?: number;
}

export default function AppShell({
  leftPane,
  centerPane,
  rightPane,
  headerRight,
  pageTitle = "Dashboard",
  interruptCount = 0
}: AppShellProps) {
  const { user } = useAuth();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <div className="app-shell">
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((c) => !c)}
      />

      <div className="app-shell-main">
        {/* Top header */}
        <header className="app-shell-header">
          <div className="app-shell-header-left">
            <span className="app-shell-page-title">{pageTitle}</span>
          </div>

          <div className="app-shell-header-right">
            {/* Interrupt notification bell */}
            <div className="header-bell-wrap">
              <button
                className="header-icon-btn"
                aria-label={`${interruptCount} items need attention`}
                title="Human interrupt queue"
              >
                <IconBell size={18} />
              </button>
              {interruptCount > 0 && (
                <span className="header-badge" aria-hidden="true">
                  {interruptCount > 99 ? "99+" : interruptCount}
                </span>
              )}
            </div>

            {/* Tenant name chip */}
            {user?.tenantName && (
              <span className="header-tenant-chip">{user.tenantName}</span>
            )}

            {/* Slot for ThemeSelector and other header controls */}
            {headerRight}
          </div>
        </header>

        {/* Three-pane content area */}
        <div className="app-shell-content">
          <div className="app-pane">{leftPane}</div>
          <div className="app-pane">{centerPane}</div>
          <div className="app-pane">{rightPane}</div>
        </div>
      </div>
    </div>
  );
}
