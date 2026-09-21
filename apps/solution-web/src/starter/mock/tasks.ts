/**
 * Mock task/message data for frontend development.
 * Replace with real API calls when backend is ready.
 * Shape must match src/types/task.ts.
 */

import type { Task } from "../types/task";

export const MOCK_TASKS: Task[] = [
  {
    id: "task-001",
    title: "Starter workspace orientation",
    status: "completed",
    assignedAgentId: "agent-synapse",
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
    updatedAt: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
    messages: [
      {
        id: "msg-001-1",
        role: "human",
        content: "Show the default operator workspace and the planned workflows.",
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
        agentId: null,
        agentName: null
      },
      {
        id: "msg-001-2",
        role: "agent",
        content: "The workspace is ready. The work list and action queue will receive live records once a workflow is connected.",
        timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 5000).toISOString(),
        agentId: "agent-synapse",
        agentName: "Ledger"
      },
      {
        id: "msg-001-3",
        role: "agent",
        content: "The two planned workflows are WhatsApp images → Excel and transaction reconciliation → warehouse. Both remain disabled until their connectors and runtime are implemented.",
        timestamp: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
        agentId: "agent-synapse",
        agentName: "Ledger"
      }
    ]
  }
];

/** A blank conversation for new task creation. */
export const EMPTY_TASK_MESSAGES = [];
