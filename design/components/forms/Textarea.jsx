import React from "react";

export function Textarea({ invalid = false, autoGrow = false, rows = 4, style, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  const handleInput = (e) => {
    if (autoGrow) {
      e.target.style.height = "auto";
      e.target.style.height = e.target.scrollHeight + "px";
    }
    rest.onInput && rest.onInput(e);
  };
  return (
    <textarea
      rows={rows}
      onFocus={(e) => { setFocus(true); rest.onFocus && rest.onFocus(e); }}
      onBlur={(e) => { setFocus(false); rest.onBlur && rest.onBlur(e); }}
      {...rest}
      onInput={handleInput}
      style={{
        width: "100%", padding: "9px 10px", resize: autoGrow ? "none" : "vertical",
        maxHeight: autoGrow ? "var(--composer-max-h)" : undefined,
        background: "var(--surface-raised)", color: "var(--text-primary)", font: "var(--type-body-sm)",
        border: "1px solid " + (invalid ? "var(--status-alert)" : focus ? "var(--brand-ember)" : "var(--border-default)"),
        borderRadius: "var(--radius-2)", outline: "none",
        boxShadow: focus && !invalid ? "0 0 0 3px var(--ember-tint-14)" : "none",
        transition: "var(--transition-color)", ...style
      }}
    />
  );
}
