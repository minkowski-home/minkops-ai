/**
 * Starter action queue. These are generic setup decisions, not client data.
 */

import type { HumanInterrupt } from "../types/interrupt";

export const MOCK_INTERRUPTS: HumanInterrupt[] = [
  {
    id: "starter-review-policy",
    type: "approval",
    priority: "high",
    status: "pending",
    title: "Set the review policy",
    description: "Choose which extraction or reconciliation exceptions require an operator before they can be exported.",
    taskId: "starter-policy",
    taskTitle: "Starter review policy",
    agentId: "agent-kall",
    agentName: "Reviewer",
    createdAt: new Date(Date.now() - 1000 * 60 * 8).toISOString(),
    suggestedAction: "Start with human review for every exception, then narrow the policy with real evidence."
  },
  {
    id: "starter-schedule",
    type: "review",
    priority: "medium",
    status: "pending",
    title: "Choose a transaction sync interval",
    description: "The transaction workflow will need an explicit schedule once accounts and warehouse credentials are connected.",
    taskId: "starter-schedule",
    taskTitle: "Transaction workflow schedule",
    agentId: "agent-synapse",
    agentName: "Ledger",
    createdAt: new Date(Date.now() - 1000 * 60 * 20).toISOString(),
    suggestedAction: "Begin with a manual run or a low-frequency interval until reconciliation behavior is verified."
  }
];
