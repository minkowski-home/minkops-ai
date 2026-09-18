import React from "react";

const SIZES = {
  sm: { height: "28px", padding: "0 10px", font: "var(--fw-semibold) var(--fs-xs)/1 var(--font-text)", gap: "6px" },
  md: { height: "36px", padding: "0 14px", font: "var(--type-button)", gap: "8px" },
  lg: { height: "46px", padding: "0 22px", font: "var(--fw-semibold) var(--fs-base)/1 var(--font-text)", gap: "10px" }
};

const VARIANTS = {
  primary: { background: "var(--action-primary-bg)", color: "var(--action-primary-fg)", border: "1px solid var(--action-primary-bg)" },
  secondary: { background: "var(--action-secondary-bg)", color: "var(--action-secondary-fg)", border: "1px solid var(--action-secondary-border)" },
  ghost: { background: "transparent", color: "var(--action-ghost-fg)", border: "1px solid transparent" },
  inverse: { background: "var(--n-0)", color: "var(--n-900)", border: "1px solid var(--n-0)" },
  danger: { background: "var(--n-0)", color: "var(--action-danger-fg)", border: "1px solid var(--n-200)" }
};

const HOVER = {
  primary: { background: "var(--action-primary-bg-hover)", borderColor: "var(--action-primary-bg-hover)" },
  secondary: { background: "var(--action-secondary-bg-hover)", borderColor: "var(--border-strong)" },
  ghost: { background: "var(--action-ghost-bg-hover)", color: "var(--text-primary)" },
  inverse: { background: "var(--n-100)", borderColor: "var(--n-100)" },
  danger: { background: "var(--status-alert-fill)", borderColor: "var(--status-alert)" }
};

export function Button({
  variant = "primary", size = "md", iconLeft, iconRight, disabled = false,
  fullWidth = false, type = "button", children, style, ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const base = {
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    borderRadius: "var(--radius-2)", cursor: disabled ? "not-allowed" : "pointer",
    letterSpacing: "var(--ls-tight)", whiteSpace: "nowrap", textDecoration: "none",
    width: fullWidth ? "100%" : undefined,
    transition: "var(--transition-color)",
    ...SIZES[size], ...VARIANTS[variant],
    ...(hover && !disabled ? HOVER[variant] : null),
    ...(disabled ? { background: "var(--action-disabled-bg)", color: "var(--action-disabled-fg)", borderColor: "var(--border-hairline)" } : null),
    ...style
  };
  return (
    <button
      type={type} disabled={disabled} style={base}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      {...rest}
    >
      {iconLeft}
      {children}
      {iconRight}
    </button>
  );
}
