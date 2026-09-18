import React from "react";

const TONES = {
  neutral: { color: "var(--text-secondary)", background: "var(--surface-inset)", border: "var(--border-default)" },
  approval: { color: "var(--brand-rust)", background: "var(--ember-tint-08)", border: "var(--ember-tint-24)" },
  escalation: { color: "var(--status-alert)", background: "var(--status-alert-fill)", border: "rgba(179,38,30,0.22)" },
  review: { color: "var(--status-info)", background: "var(--status-info-fill)", border: "var(--border-default)" },
  error: { color: "var(--status-alert)", background: "var(--status-alert-fill)", border: "rgba(179,38,30,0.22)" },
  ok: { color: "var(--status-ok)", background: "var(--status-ok-fill)", border: "rgba(31,111,69,0.2)" },
  warn: { color: "var(--status-warn)", background: "var(--status-warn-fill)", border: "rgba(138,98,18,0.22)" }
};

export function Badge({ tone = "neutral", mono = true, children, style, ...rest }) {
  const t = TONES[tone] || TONES.neutral;
  return (
    <span
      style={{
        display: "inline-flex", alignItems: "center", gap: "5px", height: "20px",
        padding: "0 7px", borderRadius: "var(--radius-1)",
        font: mono ? "var(--fw-medium) var(--fs-micro)/1 var(--font-mono)" : "var(--fw-semibold) var(--fs-micro)/1 var(--font-text)",
        letterSpacing: mono ? "var(--ls-wide)" : "var(--ls-normal)",
        textTransform: mono ? "uppercase" : "none",
        color: t.color, background: t.background, border: "1px solid " + t.border,
        whiteSpace: "nowrap", ...style
      }}
      {...rest}
    >
      {children}
    </span>
  );
}
