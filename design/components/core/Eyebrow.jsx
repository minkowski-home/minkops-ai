import React from "react";

export function Eyebrow({ rule = false, children, style, ...rest }) {
  return (
    <p
      style={{
        display: "flex", alignItems: "center", gap: "10px", margin: 0,
        font: "var(--type-eyebrow)", letterSpacing: "var(--ls-eyebrow)",
        textTransform: "uppercase", color: "var(--text-muted)", ...style
      }}
      {...rest}
    >
      {children}
      {rule ? <span style={{ flex: 1, height: 1, background: "var(--border-hairline)" }} /> : null}
    </p>
  );
}
