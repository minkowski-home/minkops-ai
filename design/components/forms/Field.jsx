import React from "react";

export function Field({ label, htmlFor, hint, error, required = false, children, style, ...rest }) {
  return (
    <div style={{ display: "grid", gap: "6px", ...style }} {...rest}>
      {label ? (
        <label htmlFor={htmlFor} style={{ font: "var(--fw-medium) var(--fs-xs)/1.2 var(--font-text)", letterSpacing: "var(--ls-normal)", color: "var(--text-secondary)" }}>
          {label}
          {required ? <span style={{ color: "var(--brand-ember)" }}> *</span> : null}
        </label>
      ) : null}
      {children}
      {error ? (
        <p style={{ margin: 0, font: "var(--type-body-sm)", color: "var(--status-alert)" }}>{error}</p>
      ) : hint ? (
        <p style={{ margin: 0, font: "var(--fw-regular) var(--fs-xs)/1.45 var(--font-text)", color: "var(--text-muted)" }}>{hint}</p>
      ) : null}
    </div>
  );
}
