import React from "react";

export function Toggle({ checked = false, onChange, label, disabled = false, id, style }) {
  return (
    <label
      title={checked ? "Disable" : "Enable"}
      style={{
        display: "inline-flex", alignItems: "center", gap: "8px",
        cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1, ...style
      }}
    >
      <input
        id={id} type="checkbox" checked={checked} disabled={disabled} aria-label={label}
        onChange={(e) => onChange && onChange(e.target.checked)}
        style={{ position: "absolute", opacity: 0, width: 1, height: 1, margin: 0 }}
      />
      <span
        style={{
          position: "relative", width: 30, height: 17, flex: "none",
          borderRadius: "var(--radius-pill)",
          background: checked ? "var(--brand-ember)" : "var(--n-200)",
          transition: "background-color var(--dur-fast) var(--ease-out)"
        }}
      >
        <span
          style={{
            position: "absolute", top: 2, left: checked ? 15 : 2, width: 13, height: 13,
            borderRadius: "50%", background: "var(--n-0)",
            boxShadow: "0 1px 2px rgba(23,23,27,0.2)",
            transition: "left var(--dur-fast) var(--ease-out)"
          }}
        />
      </span>
      {label ? <span style={{ font: "var(--type-body-sm)", color: "var(--text-secondary)" }}>{label}</span> : null}
    </label>
  );
}
