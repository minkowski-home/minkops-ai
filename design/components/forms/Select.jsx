import React from "react";

export function Select({ options = [], invalid = false, style, children, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  return (
    <div style={{ position: "relative", ...style }}>
      <select
        onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
        {...rest}
        style={{
          height: 38, width: "100%", padding: "0 32px 0 10px", appearance: "none",
          background: "var(--surface-raised)", color: "var(--text-primary)", font: "var(--type-body-sm)",
          border: "1px solid " + (invalid ? "var(--status-alert)" : focus ? "var(--brand-ember)" : "var(--border-default)"),
          borderRadius: "var(--radius-2)", outline: "none",
          boxShadow: focus && !invalid ? "0 0 0 3px var(--ember-tint-14)" : "none",
          transition: "var(--transition-color)"
        }}
      >
        {children || options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <svg
        width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
        style={{ position: "absolute", right: 11, top: "50%", transform: "translateY(-50%) rotate(90deg)", pointerEvents: "none" }}
      >
        <path d="M9 18l6-6-6-6" />
      </svg>
    </div>
  );
}
