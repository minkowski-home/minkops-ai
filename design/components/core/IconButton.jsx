import React from "react";

export function IconButton({ label, size = 32, active = false, children, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      type="button" aria-label={label} title={label}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        display: "inline-grid", placeItems: "center", width: size, height: size,
        background: active ? "var(--surface-selected)" : hover ? "var(--action-ghost-bg-hover)" : "transparent",
        color: active ? "var(--brand-rust)" : hover ? "var(--text-primary)" : "var(--action-ghost-fg)",
        border: "1px solid " + (active ? "var(--ember-tint-24)" : "transparent"),
        borderRadius: "var(--radius-2)", cursor: "pointer",
        transition: "var(--transition-color)", ...style
      }}
      {...rest}
    >
      {children}
    </button>
  );
}
