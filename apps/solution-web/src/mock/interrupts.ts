/**
 * Mock human interrupt data for frontend development.
 * Replace with real API calls when backend is ready.
 * Shape must match src/types/interrupt.ts.
 */

import type { HumanInterrupt } from "../types/interrupt";

export const MOCK_INTERRUPTS: HumanInterrupt[] = [
  {
    id: "int-001",
    type: "approval",
    priority: "high",
    status: "pending",
    title: "Approve refund: Acme Corp — $3,200",
    description:
      "Imel drafted a refund approval for Acme Corp ticket #2847. The amount exceeds the $1,000 auto-approval threshold and requires operator sign-off before sending.",
    taskId: "task-imel-2847",
    taskTitle: "Acme Corp refund request #2847",
    agentId: "agent-imel",
    agentName: "Imel",
    createdAt: new Date(Date.now() - 1000 * 60 * 8).toISOString(),
    suggestedAction: "Review the drafted email and approve or modify the refund amount."
  },
  {
    id: "int-002",
    type: "escalation",
    priority: "critical",
    status: "pending",
    title: "Escalation: repeated SLA breach — TechFlow Inc",
    description:
      "TechFlow Inc has had 3 tickets breach SLA in 7 days. Kall has exhausted its KB resolution paths. This account is flagged as enterprise tier — manual intervention recommended.",
    taskId: "task-kall-tf-9921",
    taskTitle: "TechFlow Inc — SLA breach pattern",
    agentId: "agent-kall",
    agentName: "Kall",
    createdAt: new Date(Date.now() - 1000 * 60 * 31).toISOString(),
    suggestedAction: "Contact the TechFlow account manager directly and schedule a call."
  },
  {
    id: "int-003",
    type: "review",
    priority: "medium",
    status: "pending",
    title: "Review scraped lead profile — Marcus Wren, NovaBuild",
    description:
      "Scout enriched a lead profile for Marcus Wren (VP Engineering, NovaBuild). Confidence on company size and budget signals is 72% — below the auto-qualify threshold. Review before adding to CRM pipeline.",
    taskId: "task-scout-lead-mw",
    taskTitle: "Lead enrichment: Marcus Wren",
    agentId: "agent-scout",
    agentName: "Scout",
    createdAt: new Date(Date.now() - 1000 * 60 * 52).toISOString(),
    suggestedAction: "Verify company size on LinkedIn and confirm the budget signal before qualifying."
  },
  {
    id: "int-004",
    type: "review",
    priority: "low",
    status: "acknowledged",
    title: "Draft blog post ready for review",
    description:
      "Synapse completed a first draft of the Q1 product update post based on your outline. Ready for editorial review.",
    taskId: "task-synapse-blog-q1",
    taskTitle: "Q1 product update blog post",
    agentId: "agent-synapse",
    agentName: "Synapse",
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
    suggestedAction: null
  }
];
