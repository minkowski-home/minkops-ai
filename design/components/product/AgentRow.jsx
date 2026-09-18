import React from "react";
import { Avatar } from "../core/Avatar.jsx";
import { StatusDot } from "../core/StatusDot.jsx";
import { Toggle } from "../core/Toggle.jsx";

export function AgentRow({ name, role, status = "idle", lastActive, enabled = true, selected = false, onToggle, onSelect, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
    <div
      onClick={onSelect}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        display: "flex", alignItems: "center", gap: "10px", padding: "8px 10px",
        borderRadius: "var(--radius-2)", cursor: onSelect ? "pointer" : "default",
        background: selected ? "var(--surface-selected)" : hover ? "var(--surface-sunken)" : "transparent",
        boxShadow: selected ? "var(--shadow-inset-active)" : "none",
        opacity: enabled ? 1 : 0.55, transition: "var(--transition-color)", ...style
      }}
      {...rest}
    >
      <Avatar name={name} kind="agent" size={30} />
      <div style={{ display: "grid", gap: "3px", minWidth: 0, flex: 1 }}>
        <span style={{ display: "flex", alignItems: "baseline", gap: "8px", minWidth: 0 }}>
          <span style={{ font: "var(--fw-medium) var(--fs-sm)/1.1 var(--font-display)", letterSpacing: "var(--ls-tight)", color: "var(--text-primary)" }}>{name}</span>
          {role ? <span style={{ font: "var(--type-body-sm)", color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{role}</span> : null}
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <StatusDot status={enabled ? status : "disabled"} label={enabled ? status : "disabled"} />
          {lastActive ? <span style={{ font: "var(--type-mono)", color: "var(--text-faint)" }}>{lastActive}</span> : null}
        </span>
      </div>
      {onToggle ? <Toggle checked={enabled} onChange={onToggle} label="" /> : null}
    </div>
  );
}
