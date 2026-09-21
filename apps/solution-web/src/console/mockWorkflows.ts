import type { PresetWorkflow } from "./types";

export const PRESET_WORKFLOWS: PresetWorkflow[] = [
  {
    id: "refund",
    agentId: "agent-imel",
    label: "Review a customer request",
    detail: "Imel reads the thread, drafts a reply, and sends anything above policy for your approval.",
    outcome: "I’ve picked up the customer request. I’ll handle it end to end and only interrupt if your decision is needed."
  },
  {
    id: "support-pattern",
    agentId: "agent-kall",
    label: "Investigate a support pattern",
    detail: "Kall checks recent tickets, the knowledge base, and repeated failure points.",
    outcome: "I’m checking the support pattern against recent tickets and policy. I’ll bring back a specific recommendation."
  },
  {
    id: "lead-review",
    agentId: "agent-scout",
    label: "Qualify a new lead",
    detail: "Scout enriches the contact, checks fit, and queues low-confidence records for review.",
    outcome: "I’m enriching the lead and checking the signals against your qualification rules."
  },
  {
    id: "weekly-brief",
    agentId: "agent-synapse",
    label: "Build a weekly brief",
    detail: "Synapse pulls the key work, exceptions, and decisions into one operator summary.",
    outcome: "I’m assembling the weekly brief from the work completed and the decisions still open."
  }
];
