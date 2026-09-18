const { Icon, IconButton, Avatar, Badge } = window.MinkopsDesignSystem_6c27f0;

const NAV = [
  { key: "dashboard", label: "Dashboard", icon: "home" },
  { key: "agents", label: "Agents", icon: "agents" },
  { key: "tasks", label: "Tasks", icon: "tasks" },
  { key: "analytics", label: "Analytics", icon: "analytics" },
  { key: "settings", label: "Settings", icon: "settings" }
];

function SidebarItem({ item, active, collapsed, onClick }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button type="button" onClick={onClick}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      title={collapsed ? item.label : undefined}
      style={{
        display: "flex", alignItems: "center", gap: "10px", width: "100%", height: 34,
        padding: collapsed ? "0" : "0 10px", justifyContent: collapsed ? "center" : "flex-start",
        background: active ? "var(--surface-selected)" : hover ? "var(--action-ghost-bg-hover)" : "transparent",
        color: active ? "var(--brand-rust)" : hover ? "var(--text-primary)" : "var(--text-secondary)",
        border: "none", borderRadius: "var(--radius-2)", cursor: "pointer", textAlign: "left",
        boxShadow: active ? "var(--shadow-inset-active)" : "none",
        font: "var(--fw-medium) var(--fs-sm)/1 var(--font-text)", transition: "var(--transition-color)"
      }}>
      <Icon name={item.icon} size={17} />
      {collapsed ? null : item.label}
    </button>
  );
}

function ConsoleSidebar({ route, onRoute, collapsed, onCollapse, onSignOut }) {
  return (
    <nav aria-label="Main navigation" style={{
      width: collapsed ? "var(--sidebar-w-collapsed)" : "var(--sidebar-w)", flex: "none",
      display: "flex", flexDirection: "column", background: "var(--surface-sunken)",
      borderRight: "1px solid var(--border-hairline)", transition: "width var(--dur-base) var(--ease-out)"
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", height: "var(--header-h)", padding: collapsed ? "0 8px" : "0 10px 0 12px", borderBottom: "1px solid var(--border-hairline)" }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--brand-ember)", flex: "none" }} />
        {collapsed ? null : (
          <span style={{ font: "var(--fw-bold) var(--fs-md)/1 var(--font-display)", letterSpacing: "var(--ls-wordmark)" }}>minkops</span>
        )}
        <span style={{ marginLeft: "auto" }}>
          <IconButton label={collapsed ? "Expand sidebar" : "Collapse sidebar"} size={26} onClick={onCollapse}>
            <Icon name={collapsed ? "chevronRight" : "chevronLeft"} size={13} />
          </IconButton>
        </span>
      </div>

      <div style={{ display: "grid", gap: "2px", padding: "10px 8px" }}>
        {NAV.map((item) => (
          <SidebarItem key={item.key} item={item} active={route === item.key} collapsed={collapsed} onClick={() => onRoute(item.key)} />
        ))}
      </div>

      <div style={{ marginTop: "auto", padding: "10px 8px", borderTop: "1px solid var(--border-hairline)", display: "grid", gap: "6px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "0 2px" }}>
          <Avatar name={window.USER.name} kind="human" size={28} />
          {collapsed ? null : (
            <span style={{ display: "grid", gap: "1px", minWidth: 0 }}>
              <span style={{ font: "var(--fw-medium) var(--fs-xs)/1.2 var(--font-text)", color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{window.USER.name}</span>
              <span style={{ font: "var(--type-eyebrow)", letterSpacing: "var(--ls-wide)", textTransform: "uppercase", color: "var(--text-muted)" }}>{window.USER.role}</span>
            </span>
          )}
        </div>
        <SidebarItem item={{ label: "Sign out", icon: "logout" }} collapsed={collapsed} onClick={onSignOut} />
      </div>
    </nav>
  );
}

function ConsoleHeader({ title, interruptCount, children }) {
  return (
    <header style={{
      display: "flex", alignItems: "center", gap: "10px", height: "var(--header-h)", flex: "none",
      padding: "0 14px", background: "var(--surface-page)", borderBottom: "1px solid var(--border-hairline)"
    }}>
      <span style={{ font: "var(--fw-medium) var(--fs-md)/1 var(--font-display)", letterSpacing: "var(--ls-display)" }}>{title}</span>
      <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "8px" }}>
        {children}
        <span style={{ position: "relative", display: "inline-flex" }}>
          <IconButton label={interruptCount + " items need attention"}><Icon name="bell" size={17} /></IconButton>
          {interruptCount > 0 ? (
            <span style={{
              position: "absolute", top: -2, right: -2, minWidth: 15, height: 15, padding: "0 4px",
              display: "grid", placeItems: "center", borderRadius: "var(--radius-pill)",
              background: "var(--brand-ember)", color: "var(--n-0)",
              font: "var(--fw-medium) 9px/1 var(--font-mono)", border: "1.5px solid var(--surface-page)"
            }}>{interruptCount}</span>
          ) : null}
        </span>
        <Badge tone="neutral" mono={false}>{window.USER.tenantName}</Badge>
      </span>
    </header>
  );
}

function PaneHeader({ title, meta, action }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "10px 12px", borderBottom: "1px solid var(--border-hairline)", flex: "none" }}>
      <span style={{ font: "var(--type-eyebrow)", letterSpacing: "var(--ls-eyebrow)", textTransform: "uppercase", color: "var(--text-muted)" }}>{title}</span>
      {meta}
      {action ? <span style={{ marginLeft: "auto" }}>{action}</span> : null}
    </div>
  );
}

Object.assign(window, { ConsoleSidebar, ConsoleHeader, PaneHeader, CONSOLE_NAV: NAV });
