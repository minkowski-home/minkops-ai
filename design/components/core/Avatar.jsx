import React from "react";

function initials(name) {
  return String(name || "?").trim().split(/\s+/).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
}

export function Avatar({ name, kind = "agent", size = 30, square = true, style, ...rest }) {
  const isAgent = kind === "agent";
  return (
    <span
      title={name}
      style={{
        display: "grid", placeItems: "center", width: size, height: size, flex: "none",
        borderRadius: square ? "var(--radius-2)" : "50%",
        background: isAgent ? "var(--surface-inverse)" : "var(--surface-inset)",
        color: isAgent ? "var(--text-inverse)" : "var(--text-secondary)",
        border: isAgent ? "1px solid var(--surface-inverse)" : "1px solid var(--border-default)",
        font: "var(--fw-medium) " + Math.max(10, Math.round(size * 0.36)) + "px/1 var(--font-mono)",
        letterSpacing: "0.02em", ...style
      }}
      {...rest}
    >
      {initials(name)}
    </span>
  );
}
