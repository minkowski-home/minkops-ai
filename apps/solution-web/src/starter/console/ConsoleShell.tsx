import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { ThemePicker } from "../theme/ThemeContext";
import { Icon } from "./Icon";
import type { ConsoleRoute } from "./types";

function initials(name: string) {
  return name.split(" ").slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

interface Props {
  children: React.ReactNode;
  title: string;
  tenantName: string;
  routeSlug: string;
  pendingCount: number;
  collapsed: boolean;
  onToggleSidebar: () => void;
  canEdit: boolean;
}

const navigation: { route: ConsoleRoute; label: string; icon: "home" | "agents" | "tasks" }[] = [
  { route: "dashboard", label: "Dashboard", icon: "home" },
  { route: "employees", label: "Employees", icon: "agents" },
  { route: "workflows", label: "Workflows", icon: "tasks" },
];

export function ConsoleShell({ children, title, tenantName, routeSlug, pendingCount,
  collapsed, onToggleSidebar, canEdit }: Props) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return <div className={`console-shell${collapsed ? " is-collapsed" : ""}`}>
    <aside className="console-sidebar" aria-label="Main navigation">
      <div className="console-brand-row">
        <button className="console-wordmark" onClick={() => navigate(`/${routeSlug}/dashboard`)}
          aria-label="Minkops dashboard"><span className="wordmark-dot" /><span>minkops</span></button>
        <button className="icon-button sidebar-collapse" onClick={onToggleSidebar}
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}>
          <Icon name={collapsed ? "chevronRight" : "chevronLeft"} size={14} />
        </button>
      </div>
      <nav className="console-nav">
        {navigation.map((item) => <NavLink key={item.route} to={`/${routeSlug}/${item.route}`}
          className={({ isActive }) => `console-nav-item${isActive ? " is-active" : ""}`}
          title={collapsed ? item.label : undefined}>
          <Icon name={item.icon} size={18} /><span>{item.label}</span>
          {item.route === "dashboard" && pendingCount > 0 && <b>{pendingCount}</b>}
        </NavLink>)}
        <NavLink to={`/${routeSlug}/connections`} className={({ isActive }) => `console-nav-item${isActive ? ' is-active' : ''}`}>
          <Icon name="settings" size={18} /><span>Connections</span>
        </NavLink>
        {canEdit && <NavLink to={`/${routeSlug}/access`}
          className={({ isActive }) => `console-nav-item${isActive ? " is-active" : ""}`}>
          <Icon name="settings" size={18} /><span>Access</span>
        </NavLink>}
      </nav>
      <div className="console-account">
        <div className="human-avatar" aria-hidden="true">{user ? initials(user.name) : "?"}</div>
        <div className="console-account-copy"><strong>{user?.name}</strong><span>{user?.email}</span></div>
        <button className="icon-button account-logout" title="Sign out" aria-label="Sign out"
          onClick={() => { void logout().then(() => navigate("/login")); }}>
          <Icon name="logout" size={17} />
        </button>
      </div>
    </aside>
    <main className="console-main">
      <header className="console-header"><h1>{title}</h1><div className="console-header-tools">
        <span className="tenant-label">{tenantName}</span><ThemePicker />
      </div></header>
      <div className="console-view">{children}</div>
    </main>
  </div>;
}
