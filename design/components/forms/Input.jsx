import React from "react";

export function Input({ invalid = false, mono = false, size = "md", style, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  return (
    <input
      onFocus={(e) => { setFocus(true); rest.onFocus && rest.onFocus(e); }}
      onBlur={(e) => { setFocus(false); rest.onBlur && rest.onBlur(e); }}
      {...rest}
      style={{
        height: size === "sm" ? 30 : 38, width: "100%", padding: "0 10px",
        background: "var(--surface-raised)", color: "var(--text-primary)",
        font: mono ? "var(--fw-regular) var(--fs-sm)/1 var(--font-mono)" : "var(--type-body-sm)",
        border: "1px solid " + (invalid ? "var(--status-alert)" : focus ? "var(--brand-ember)" : "var(--border-default)"),
        borderRadius: "var(--radius-2)", outline: "none",
        boxShadow: focus && !invalid ? "0 0 0 3px var(--ember-tint-14)" : "none",
        transition: "var(--transition-color)", ...style
      }}
    />
  );
}
