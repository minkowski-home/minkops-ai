import React from "react";

export function OptionRow({ label, meta, selected = false, multi = false, onSelect, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      type="button" role={multi ? "checkbox" : "radio"} aria-checked={selected}
      onClick={onSelect}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        display: "flex", alignItems: "center", gap: "12px", width: "100%",
        minHeight: 48, padding: "10px 14px", textAlign: "left", cursor: "pointer",
        background: selected ? "var(--surface-accent-soft)" : hover ? "var(--surface-sunken)" : "var(--surface-raised)",
        border: "1px solid " + (selected ? "var(--brand-ember)" : "var(--border-default)"),
        borderRadius: "var(--radius-2)", transition: "var(--transition-color)", ...style
      }}
      {...rest}
    >
      <span
        aria-hidden="true"
        style={{
          display: "grid", placeItems: "center", width: 16, height: 16, flex: "none",
          borderRadius: multi ? "var(--radius-1)" : "50%",
          border: "1px solid " + (selected ? "var(--brand-ember)" : "var(--border-strong)"),
          background: selected ? "var(--brand-ember)" : "transparent",
          color: "var(--n-0)"
        }}
      >
        {selected ? (
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
        ) : null}
      </span>
      <span style={{ display: "grid", gap: "2px", minWidth: 0 }}>
        <span style={{ font: "var(--type-body-sm)", fontWeight: "var(--fw-medium)", color: "var(--text-primary)" }}>{label}</span>
        {meta ? <span style={{ font: "var(--type-eyebrow)", letterSpacing: "var(--ls-wide)", textTransform: "uppercase", color: "var(--text-muted)" }}>{meta}</span> : null}
      </span>
    </button>
  );
}
