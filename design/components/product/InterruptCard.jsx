import React from "react";
import { Badge } from "../core/Badge.jsx";
import { Button } from "../core/Button.jsx";
import { Icon } from "../core/Icon.jsx";

const LABELS = { approval: "Approval", escalation: "Escalation", review: "Review", error: "Error" };

export function InterruptCard({
  type = "review", priority = "medium", status = "pending", title, description,
  agentName, taskTitle, suggestedAction, time,
  onResolve, onAcknowledge, onDismiss, style, ...rest
}) {
  const pending = status === "pending";
  const critical = priority === "critical";
  return (
    <article
      style={{
        display: "grid", gap: "8px", padding: "12px 14px",
        background: "var(--surface-raised)", borderRadius: "var(--radius-3)",
        border: "1px solid " + (critical ? "rgba(179,38,30,0.28)" : "var(--border-default)"),
        borderLeft: "2px solid " + (critical ? "var(--status-alert)" : pending ? "var(--brand-ember)" : "var(--border-strong)"),
        opacity: pending ? 1 : 0.72, ...style
      }}
      {...rest}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <Badge tone={type}>{LABELS[type] || type}</Badge>
        {critical ? <Badge tone="escalation">Critical</Badge> : null}
        <span style={{ marginLeft: "auto", font: "var(--type-mono)", color: "var(--text-faint)" }}>{time}</span>
      </div>
      <p style={{ margin: 0, font: "var(--fw-medium) var(--fs-sm)/1.35 var(--font-text)", color: "var(--text-primary)" }}>{title}</p>
      {description ? <p style={{ margin: 0, font: "var(--fw-regular) var(--fs-xs)/1.55 var(--font-text)", color: "var(--text-secondary)" }}>{description}</p> : null}
      {(agentName || taskTitle) ? (
        <p style={{ margin: 0, font: "var(--type-mono)", color: "var(--text-muted)" }}>
          {agentName ? <>Raised by <strong style={{ color: "var(--text-secondary)", fontWeight: "var(--fw-medium)" }}>{agentName}</strong></> : null}
          {agentName && taskTitle ? " · " : null}{taskTitle}
        </p>
      ) : null}
      {suggestedAction ? (
        <p style={{ margin: 0, padding: "8px 10px", background: "var(--surface-sunken)", borderLeft: "1px solid var(--border-default)", font: "var(--fw-regular) var(--fs-xs)/1.5 var(--font-text)", color: "var(--text-secondary)" }}>{suggestedAction}</p>
      ) : null}
      {pending ? (
        <div style={{ display: "flex", gap: "6px", marginTop: "2px" }}>
          <Button size="sm" variant="primary" onClick={onResolve} iconLeft={<Icon name="check" size={12} />}>Resolve</Button>
          <Button size="sm" variant="secondary" onClick={onAcknowledge}>Acknowledge</Button>
          <Button size="sm" variant="danger" onClick={onDismiss} style={{ marginLeft: "auto", padding: "0 8px" }} aria-label="Dismiss"><Icon name="x" size={12} /></Button>
        </div>
      ) : null}
    </article>
  );
}
