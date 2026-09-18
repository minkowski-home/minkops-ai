import React from "react";

export function TypingIndicator({ name = "Agent", style, ...rest }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px", ...style }} {...rest}>
      <style>{"@keyframes mk-typing{0%,60%,100%{opacity:.25}30%{opacity:1}}"}</style>
      <span style={{ display: "flex", gap: "4px", padding: "8px 10px", border: "1px solid var(--border-hairline)", borderRadius: "var(--radius-2)", background: "var(--surface-sunken)" }}>
        {[0, 1, 2].map((i) => (
          <span key={i} style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--brand-ember)", animation: "mk-typing 1.2s " + i * 0.16 + "s infinite var(--ease-in-out)" }} />
        ))}
      </span>
      <span style={{ font: "var(--type-eyebrow)", letterSpacing: "var(--ls-wide)", textTransform: "uppercase", color: "var(--text-muted)" }}>{name} is working</span>
    </div>
  );
}
