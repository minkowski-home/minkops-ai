/**
 * A queued item that needs a human: approval above an agent's authority,
 * an escalation, a review, or an error.
 *
 * @startingPoint section="Console" subtitle="Human interrupt card with actions" viewport="700x300"
 */
export interface InterruptCardProps {
  type?: "approval" | "escalation" | "review" | "error";
  priority?: "critical" | "high" | "medium" | "low";
  status?: "pending" | "acknowledged";
  /** Specific, scannable title — include the entity and amount where relevant. */
  title: string;
  description?: string;
  /** Agent that raised it. */
  agentName?: string;
  /** Originating task. */
  taskTitle?: string;
  /** What the operator should do, in one sentence. */
  suggestedAction?: string;
  /** Pre-formatted relative time: "8m ago". */
  time?: string;
  onResolve?: () => void;
  onAcknowledge?: () => void;
  onDismiss?: () => void;
  style?: React.CSSProperties;
}

export declare function InterruptCard(props: InterruptCardProps): JSX.Element;
