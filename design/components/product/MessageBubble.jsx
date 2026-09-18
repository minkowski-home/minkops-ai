import React from "react";
import { Avatar } from "../core/Avatar.jsx";

export function MessageBubble({ role = "agent", sender, content, time, style, ...rest }) {
  const human = role === "human";
  return (
    <div style={{ display: "flex", gap: "10px", flexDirection: human ? "row-reverse" : "row", ...style }} {...rest}>
      <Avatar name={sender} kind={human ? "human" : "agent"} size={28} />
      <div style={{ display: "grid", gap: "4px", maxWidth: "min(560px, 78%)", justifyItems: human ? "end" : "start" }}>
        <span style={{ font: "var(--type-eyebrow)", letterSpacing: "var(--ls-wide)", textTransform: "uppercase", color: "var(--text-muted)" }}>{sender}</span>
        <p
          style={{
            margin: 0, padding: "9px 12px", font: "var(--type-body-sm)",
            borderRadius: "var(--radius-3)",
            background: human ? "var(--surface-inverse)" : "var(--surface-sunken)",
            color: human ? "var(--text-inverse)" : "var(--text-primary)",
            border: "1px solid " + (human ? "var(--surface-inverse)" : "var(--border-hairline)"),
            whiteSpace: "pre-wrap"
          }}
        >
          {content}
        </p>
        <span style={{ font: "var(--type-mono)", color: "var(--text-faint)" }}>{time}</span>
      </div>
    </div>
  );
}
