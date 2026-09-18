import React from "react";

const TONES = {
  default: { background: "var(--surface-raised)", border: "1px solid var(--border-default)", color: "var(--text-primary)" },
  sunken: { background: "var(--surface-sunken)", border: "1px solid var(--border-hairline)", color: "var(--text-primary)" },
  inverse: { background: "var(--surface-inverse)", border: "1px solid var(--surface-inverse)", color: "var(--text-inverse)" },
  accent: { background: "var(--surface-accent-soft)", border: "1px solid var(--ember-tint-24)", color: "var(--text-primary)" }
};

export function Card({ tone = "default", pad = "var(--pad-card)", accentEdge = false, elevated = false, children, style, ...rest }) {
  const t = TONES[tone] || TONES.default;
  return (
    <div
      style={{
        borderRadius: "var(--radius-3)", padding: pad, ...t,
        boxShadow: elevated ? "var(--shadow-pop)" : "none",
        borderLeft: accentEdge ? "2px solid var(--brand-ember)" : t.border,
        ...style
      }}
      {...rest}
    >
      {children}
    </div>
  );
}
