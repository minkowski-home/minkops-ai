/**
 * InterruptPanel — right pane of the dashboard.
 *
 * Displays items queued for human attention: completed tasks awaiting
 * review, tasks requiring approval above agent authority thresholds,
 * and escalations where the agent has exhausted its resolution paths.
 *
 * Action wiring (TODO when backend is ready):
 *   Acknowledge:  PATCH /api/interrupts/:id { status: "acknowledged" }
 *   Resolve:      PATCH /api/interrupts/:id { status: "resolved" }
 *   Dismiss:      PATCH /api/interrupts/:id { status: "dismissed" }
 *
 * The interrupt feed should eventually be driven by a WebSocket or SSE
 * channel so new items appear in real time without polling.
 */

import { useState, useCallback } from "react";
import type { HumanInterrupt, InterruptPriority, InterruptType } from "../../types/interrupt";
import { MOCK_INTERRUPTS } from "../../mock/interrupts";
import { IconCheck, IconX } from "../icons";
import "./InterruptPanel.css";

/** Returns a human-readable relative time label. */
function relativeTime(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

/** Count active (pending) items by priority for the summary header. */
function countByPriority(
  items: HumanInterrupt[]
): Record<InterruptPriority, number> {
  const active = items.filter((i) => i.status === "pending");
  return {
    critical: active.filter((i) => i.priority === "critical").length,
    high: active.filter((i) => i.priority === "high").length,
    medium: active.filter((i) => i.priority === "medium").length,
    low: active.filter((i) => i.priority === "low").length
  };
}

export default function InterruptPanel() {
  const [interrupts, setInterrupts] = useState<HumanInterrupt[]>(MOCK_INTERRUPTS);

  const acknowledge = useCallback((id: string) => {
    setInterrupts((prev) =>
      prev.map((i) => (i.id === id ? { ...i, status: "acknowledged" } : i))
    );
    // TODO: PATCH /api/interrupts/:id { status: "acknowledged" }
  }, []);

  const resolve = useCallback((id: string) => {
    setInterrupts((prev) => prev.filter((i) => i.id !== id));
    // TODO: PATCH /api/interrupts/:id { status: "resolved" }
  }, []);

  const dismiss = useCallback((id: string) => {
    setInterrupts((prev) => prev.filter((i) => i.id !== id));
    // TODO: PATCH /api/interrupts/:id { status: "dismissed" }
  }, []);

  const counts = countByPriority(interrupts);
  const pendingCount = interrupts.filter((i) => i.status === "pending").length;

  // Sort: critical first, then high, then medium, then low;
  // within the same priority, pending before acknowledged; newest first.
  const sorted = [...interrupts].sort((a, b) => {
    const priorityOrder: InterruptPriority[] = ["critical", "high", "medium", "low"];
    const pa = priorityOrder.indexOf(a.priority);
    const pb = priorityOrder.indexOf(b.priority);
    if (pa !== pb) return pa - pb;
    if (a.status !== b.status) {
      return a.status === "pending" ? -1 : 1;
    }
    return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
  });

  return (
    <div className="interrupt-panel">
      <div className="interrupt-panel-header">
        <div className="interrupt-header-row">
          <p className="interrupt-panel-title">
            Needs Attention {pendingCount > 0 && `(${pendingCount})`}
          </p>
        </div>

        {/* Priority summary pills */}
        {pendingCount > 0 && (
          <div className="interrupt-summary">
            {counts.critical > 0 && (
              <span className="interrupt-summary-pill critical">
                {counts.critical} critical
              </span>
            )}
            {counts.high > 0 && (
              <span className="interrupt-summary-pill high">
                {counts.high} high
              </span>
            )}
            {counts.medium > 0 && (
              <span className="interrupt-summary-pill medium">
                {counts.medium} medium
              </span>
            )}
            {counts.low > 0 && (
              <span className="interrupt-summary-pill low">
                {counts.low} low
              </span>
            )}
          </div>
        )}
      </div>

      <div className="interrupt-panel-body">
        {sorted.length === 0 ? (
          <div className="interrupt-empty">
            <div className="interrupt-empty-headline">All clear</div>
            <div className="interrupt-empty-hint">
              No items need your attention right now. Agents are running smoothly.
            </div>
          </div>
        ) : (
          sorted.map((item) => (
            <InterruptCard
              key={item.id}
              interrupt={item}
              onAcknowledge={acknowledge}
              onResolve={resolve}
              onDismiss={dismiss}
            />
          ))
        )}
      </div>
    </div>
  );
}

interface InterruptCardProps {
  interrupt: HumanInterrupt;
  onAcknowledge: (id: string) => void;
  onResolve: (id: string) => void;
  onDismiss: (id: string) => void;
}

function typeLabel(type: InterruptType): string {
  switch (type) {
    case "approval":   return "Approval";
    case "escalation": return "Escalation";
    case "review":     return "Review";
    case "error":      return "Error";
  }
}

function InterruptCard({
  interrupt,
  onAcknowledge,
  onResolve,
  onDismiss
}: InterruptCardProps) {
  const isPending = interrupt.status === "pending";

  return (
    <div
      className={[
        "interrupt-card",
        `priority-${interrupt.priority}`,
        interrupt.status !== "pending" ? interrupt.status : ""
      ]
        .filter(Boolean)
        .join(" ")}
      aria-label={`${interrupt.priority} priority ${interrupt.type}: ${interrupt.title}`}
    >
      {/* Type badge + timestamp */}
      <div className="interrupt-card-top">
        <span className={`interrupt-type-badge ${interrupt.type}`}>
          {typeLabel(interrupt.type)}
        </span>
        <span className="interrupt-card-time">{relativeTime(interrupt.createdAt)}</span>
      </div>

      <div className="interrupt-card-title">{interrupt.title}</div>
      <div className="interrupt-card-desc">{interrupt.description}</div>

      <div className="interrupt-card-agent">
        Raised by <strong>{interrupt.agentName}</strong> · {interrupt.taskTitle}
      </div>

      {/* Suggested action hint */}
      {interrupt.suggestedAction && (
        <div className="interrupt-suggested">{interrupt.suggestedAction}</div>
      )}

      {/* Action buttons — only shown for pending items */}
      {isPending && (
        <div className="interrupt-card-actions">
          <button
            className="interrupt-action-btn primary"
            onClick={() => onResolve(interrupt.id)}
            aria-label={`Resolve: ${interrupt.title}`}
          >
            <IconCheck size={12} />
            Resolve
          </button>
          <button
            className="interrupt-action-btn secondary"
            onClick={() => onAcknowledge(interrupt.id)}
            aria-label={`Acknowledge: ${interrupt.title}`}
          >
            Acknowledge
          </button>
          <button
            className="interrupt-action-btn danger"
            onClick={() => onDismiss(interrupt.id)}
            aria-label={`Dismiss: ${interrupt.title}`}
          >
            <IconX size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
