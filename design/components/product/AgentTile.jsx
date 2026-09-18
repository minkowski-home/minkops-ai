import React from "react";
import { Icon } from "../core/Icon.jsx";

export function AgentTile({ name, tool, domain, glyph = "email", status, onClick, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const interactive = Boolean(onClick);
  return (
    <article
      onClick={onClick}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        display: "grid", gap: "10px", padding: "16px", background: "var(--surface-raised)",
        border: "1px solid " + (hover && interactive ? "var(--brand-ember)" : "var(--border-default)"),
        borderRadius: "var(--radius-3)", cursor: interactive ? "pointer" : "default",
        transition: "var(--transition-color)", ...style
      }}
      {...rest}
    >
      <span style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ display: "grid", placeItems: "center", width: 34, height: 34, borderRadius: "var(--radius-2)", background: "var(--surface-inset)", border: "1px solid var(--border-hairline)", color: "var(--brand-rust)" }}>
          <Icon name={glyph} size={22} />
        </span>
        {status ? <span style={{ font: "var(--type-eyebrow)", letterSpacing: "var(--ls-wide)", textTransform: "uppercase", color: "var(--text-faint)" }}>{status}</span> : null}
      </span>
      <span style={{ display: "grid", gap: "3px" }}>
        <span style={{ font: "var(--fw-semibold) var(--fs-lg)/1.1 var(--font-display)", letterSpacing: "var(--ls-display)", color: "var(--text-primary)" }}>{name}</span>
        <span style={{ font: "var(--type-body-sm)", color: "var(--text-secondary)" }}>{tool}</span>
      </span>
      {domain ? <span style={{ font: "var(--type-mono)", color: "var(--text-muted)", paddingTop: "8px", borderTop: "1px solid var(--border-hairline)" }}>{domain}</span> : null}
    </article>
  );
}
