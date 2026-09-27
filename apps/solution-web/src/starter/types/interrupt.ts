/**
 * Human interrupt domain types.
 *
 * Backend contract for the /api/interrupts endpoint.
 * Interrupts are items routed to a human operator for review,
 * approval, or escalation resolution. They originate from agent
 * workflows that hit a decision boundary requiring human judgement.
 */

export type InterruptType = "review" | "approval" | "escalation" | "error";

export type InterruptPriority = "low" | "medium" | "high" | "critical";

export type InterruptStatus = "pending" | "acknowledged" | "resolved" | "dismissed";

export interface HumanInterrupt {
  id: string;
  type: InterruptType;
  priority: InterruptPriority;
  status: InterruptStatus;
  title: string;
  /** Detailed description of what needs human attention. */
  description: string;
  /** The task that triggered this interrupt. */
  taskId: string;
  taskTitle: string;
  /** The agent that raised this interrupt. */
  agentId: string;
  agentName: string;
  /** ISO timestamp. */
  createdAt: string;
  /** Suggested action text for the human operator. */
  suggestedAction: string | null;
}
