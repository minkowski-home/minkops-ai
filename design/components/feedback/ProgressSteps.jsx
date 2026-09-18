import React from "react";

export function ProgressSteps({ total = 4, current = 0, style, ...rest }) {
  return (
    <div
      role="progressbar" aria-valuenow={current + 1} aria-valuemin={1} aria-valuemax={total}
      style={{ display: "flex", gap: "4px", ...style }} {...rest}
    >
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          style={{
            height: 3, flex: 1, borderRadius: "var(--radius-1)",
            background: i <= current ? "var(--brand-ember)" : "var(--n-100)",
            transition: "background-color var(--dur-base) var(--ease-out)"
          }}
        />
      ))}
    </div>
  );
}
