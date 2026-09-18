import React from "react";

export function FlowNode({ agent, role, output = false, label, style, ...rest }) {
  return (
    <div
      style={{
        display: "grid", gap: "4px", minWidth: 148, padding: "14px 16px",
        background: output ? "var(--surface-inverse)" : "var(--surface-raised)",
        color: output ? "var(--text-inverse)" : "var(--text-primary)",
        border: "1px solid " + (output ? "var(--surface-inverse)" : "var(--border-default)"),
        borderTop: output ? "1px solid var(--surface-inverse)" : "2px solid var(--brand-ember)",
        borderRadius: "var(--radius-3)", ...style
      }}
      {...rest}
    >
      {output ? (
        <span style={{ font: "var(--fw-medium) var(--fs-sm)/1.2 var(--font-text)" }}>{label}</span>
      ) : (
        <>
          <span style={{ font: "var(--fw-semibold) var(--fs-md)/1.1 var(--font-display)", letterSpacing: "var(--ls-display)" }}>{agent}</span>
          <span style={{ font: "var(--type-eyebrow)", letterSpacing: "var(--ls-wide)", textTransform: "uppercase", color: "var(--text-muted)" }}>{role}</span>
        </>
      )}
    </div>
  );
}

export function FlowArrow({ label, style, ...rest }) {
  return (
    <div style={{ display: "grid", justifyItems: "center", gap: "4px", minWidth: 96, ...style }} {...rest}>
      {label ? <span style={{ font: "var(--type-mono)", color: "var(--text-muted)", textAlign: "center" }}>{label}</span> : null}
      <svg width="72" height="8" viewBox="0 0 72 8" fill="none" aria-hidden="true">
        <path d="M0 4H66" stroke="var(--border-strong)" strokeWidth="1.5" />
        <path d="M63 1L67 4L63 7" stroke="var(--border-strong)" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </div>
  );
}
