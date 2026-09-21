import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { Icon, type ConsoleIconName } from "./Icon";
import type { ConsoleRoute } from "./types";

function initials(name: string) {
  return name.split(" ").slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

interface ConsoleShellProps {
  children: React.ReactNode;
  title: string;
  productName: string;
  navigation: { route: ConsoleRoute; label: string; icon: ConsoleIconName }[];
  pendingCount: number;
  collapsed: boolean;
  onToggleSidebar: () => void;
}

export function ConsoleShell({
  children,
  title,
  productName,
  navigation,
  pendingCount,
  collapsed,
  onToggleSidebar
}: ConsoleShellProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className={`console-shell${collapsed ? " is-collapsed" : ""}`}>
      <aside className="console-sidebar" aria-label="Main navigation">
        <div className="console-brand-row">
          <button className="console-wordmark" onClick={() => navigate("/dashboard")} aria-label={`${productName} dashboard`}>
            <span className="wordmark-dot" />
            <span>{productName}</span>
          </button>
          <button className="icon-button sidebar-collapse" onClick={onToggleSidebar} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}>
            <Icon name={collapsed ? "chevronRight" : "chevronLeft"} size={14} />
          </button>
        </div>

        <nav className="console-nav">
          {navigation.map((item) => (
            <NavLink
              key={item.route}
              to={`/${item.route}`}
              className={({ isActive }) => `console-nav-item${isActive ? " is-active" : ""}`}
              title={collapsed ? item.label : undefined}
            >
              <Icon name={item.icon} size={18} />
              <span>{item.label}</span>
              {item.route === "dashboard" && pendingCount > 0 ? <b>{pendingCount}</b> : null}
            </NavLink>
          ))}
        </nav>

        <div className="console-account">
          <div className="human-avatar" aria-hidden="true">{user ? initials(user.name) : "?"}</div>
          <div className="console-account-copy">
            <strong>{user?.name ?? "Operator"}</strong>
            <span>{user?.role ?? ""}</span>
          </div>
          <button className="icon-button account-logout" onClick={logout} aria-label="Sign out" title="Sign out">
            <Icon name="logout" size={17} />
          </button>
        </div>
      </aside>

      <main className="console-main">
        <header className="console-header">
          <h1>{title}</h1>
          <div className="console-header-tools">
            <span className="tenant-label">{user?.tenantName}</span>
            <button
              className={`icon-button notification-button${pendingCount ? " has-items" : ""}`}
              aria-label={`${pendingCount} items need attention`}
              onClick={() => navigate("/dashboard#attention")}
            >
              <Icon name="bell" size={18} />
              {pendingCount ? <b>{pendingCount}</b> : null}
            </button>
          </div>
        </header>
        <div key={location.pathname} className="console-view">{children}</div>
      </main>
    </div>
  );
}
