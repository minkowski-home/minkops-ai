import React from "react";

const LEVELS = {
  critical: { color: "var(--status-alert)", dot: "var(--status-alert)" },
  high: { color: "var(--brand-rust)", dot: "var(--brand-ember)" },
  medium: { color: "var(--status-warn)", dot: "var(--status-warn)" },
  low: { color: "var(--text-muted)", dot: "var(--n-400)" }
};

export function PriorityPill({ level = "low", count, children, style, ...rest }) {
  const l = LEVELS[level] || LEVELS.low;
  return (
    <span
      style={{
        display: "inline-flex", alignItems: "center", gap: "6px", height: "22px",
        padding: "0 9px 0 7px", borderRadius: "var(--radius-pill)",
        border: "1px solid var(--border-default)", background: "var(--surface-raised)",
        font: "var(--fw-medium) var(--fs-xs)/1 var(--font-text)", color: l.color,
        whiteSpace: "nowrap", ...style
      }}
      {...rest}
    >
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: l.dot, flex: "none" }} />
      {count != null ? count + " " : null}{children ?? level}
    </span>
  );
}
