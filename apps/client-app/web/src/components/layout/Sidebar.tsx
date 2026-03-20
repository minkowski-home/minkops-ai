import { NavLink } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import {
  IconHome,
  IconAgents,
  IconTasks,
  IconAnalytics,
  IconSettings,
  IconChevronLeft,
  IconChevronRight,
  IconLogout
} from "../icons";
import "./Sidebar.css";

interface NavItem {
  to: string;
  label: string;
  Icon: React.FC<{ className?: string; size?: number }>;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", Icon: IconHome },
  { to: "/agents", label: "Agents", Icon: IconAgents },
  { to: "/tasks", label: "Tasks", Icon: IconTasks },
  { to: "/analytics", label: "Analytics", Icon: IconAnalytics },
  { to: "/settings", label: "Settings", Icon: IconSettings }
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { user, logout } = useAuth();

  /** Derive initials from display name for the avatar. */
  const initials = user?.name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("") ?? "?";

  return (
    <nav
      className={`sidebar glass-panel-vibrant soft-enter${collapsed ? " collapsed" : ""}`}
      aria-label="Main navigation"
    >
      <div className="sidebar-header">
        <div className="sidebar-brand">
          <span className="sidebar-brand-name">minkops</span>
        </div>
        <button
          className="sidebar-toggle"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <IconChevronRight size={14} /> : <IconChevronLeft size={14} />}
        </button>
      </div>

      <div className="sidebar-nav">
        {NAV_ITEMS.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/dashboard"}
            className={({ isActive }) =>
              `sidebar-item${isActive ? " active" : ""}`
            }
            title={collapsed ? label : undefined}
          >
            <span className="sidebar-item-icon">
              <Icon size={18} />
            </span>
            <span className="sidebar-item-label">{label}</span>
          </NavLink>
        ))}
      </div>

      <div className="sidebar-footer">
        <div className="sidebar-user" title={collapsed ? user?.name : undefined}>
          <div className="sidebar-avatar" aria-hidden="true">{initials}</div>
          <div className="sidebar-user-info">
            <div className="sidebar-user-name">{user?.name ?? "Unknown"}</div>
            <div className="sidebar-user-role">{user?.role ?? ""}</div>
          </div>
        </div>

        <button
          className="sidebar-item"
          onClick={logout}
          title={collapsed ? "Sign out" : undefined}
        >
          <span className="sidebar-item-icon">
            <IconLogout size={18} />
          </span>
          <span className="sidebar-item-label">Sign out</span>
        </button>
      </div>
    </nav>
  );
}
