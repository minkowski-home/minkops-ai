import React from "react";

export function EmptyState({ icon, headline, hint, action, style, ...rest }) {
  return (
    <div
      style={{
        display: "grid", justifyItems: "center", gap: "8px", padding: "48px 24px",
        textAlign: "center", ...style
      }}
      {...rest}
    >
      {icon ? (
        <span style={{ display: "grid", placeItems: "center", width: 36, height: 36, marginBottom: "4px", borderRadius: "var(--radius-2)", border: "1px solid var(--border-default)", background: "var(--surface-sunken)", color: "var(--text-muted)" }}>
          {icon}
        </span>
      ) : null}
      <p style={{ margin: 0, font: "var(--type-h4)", color: "var(--text-primary)" }}>{headline}</p>
      {hint ? <p style={{ margin: 0, maxWidth: "34ch", font: "var(--type-body-sm)", color: "var(--text-muted)" }}>{hint}</p> : null}
      {action ? <div style={{ marginTop: "8px" }}>{action}</div> : null}
    </div>
  );
}
