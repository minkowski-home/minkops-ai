/**
 * Mock task/message data for frontend development.
 * Replace with real API calls when backend is ready.
 * Shape must match src/types/task.ts.
 */

import type { Task } from "../types/task";

export const MOCK_TASKS: Task[] = [
  {
    id: "task-001",
    title: "Summarise Q1 support tickets from Acme Corp",
    status: "completed",
    assignedAgentId: "agent-synapse",
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
    updatedAt: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
    messages: [
      {
        id: "msg-001-1",
        role: "human",
        content: "Can you pull all support tickets from Acme Corp for Q1 and give me a summary by category?",
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
        agentId: null,
        agentName: null
      },
      {
        id: "msg-001-2",
        role: "agent",
        content: "On it. I found 47 tickets from Acme Corp in Q1. Pulling categories now...",
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 5000).toISOString(),
        agentId: "agent-synapse",
        agentName: "Synapse"
      },
      {
        id: "msg-001-3",
        role: "agent",
        content: "Done. Here's the breakdown:\n\n• **Billing** — 18 tickets (38%)\n• **Integration** — 14 tickets (30%)\n• **Performance** — 9 tickets (19%)\n• **Feature requests** — 6 tickets (13%)\n\nBilling dominates. Most stem from invoice date mismatches after their Feb plan change. I can draft a proactive comms email if you'd like.",
        timestamp: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
        agentId: "agent-synapse",
        agentName: "Synapse"
      }
    ]
  }
];

/** A blank conversation for new task creation. */
export const EMPTY_TASK_MESSAGES = [];
