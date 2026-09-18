import React from "react";

const STATES = {
  active: "var(--signal-live)",
  idle: "var(--signal-idle)",
  disabled: "var(--signal-off)",
  error: "var(--status-alert)",
  ok: "var(--status-ok)"
};

export function StatusDot({ status = "idle", size = 7, pulse = false, label, style, ...rest }) {
  const color = STATES[status] || STATES.idle;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", ...style }} {...rest}>
      <span
        style={{
          width: size, height: size, borderRadius: "50%", background: color, flex: "none",
          boxShadow: pulse ? "0 0 0 3px " + (status === "active" ? "var(--ember-tint-14)" : "var(--slate-tint-20)") : "none"
        }}
      />
      {label ? (
        <span style={{ font: "var(--type-eyebrow)", letterSpacing: "var(--ls-wide)", textTransform: "uppercase", color: "var(--text-muted)" }}>{label}</span>
      ) : null}
    </span>
  );
}
