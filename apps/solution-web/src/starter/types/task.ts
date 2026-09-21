/**
 * Task / chat message domain types.
 *
 * Backend contract for the /api/tasks and /api/messages endpoints.
 * The chat interface submits a HumanMessage and receives a stream of
 * AgentMessage replies. Task objects wrap the full conversation thread.
 */

export type MessageRole = "human" | "agent" | "system";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  /** ISO timestamp. */
  timestamp: string;
  /** Which agent sent this message, if role === "agent". */
  agentId: string | null;
  agentName: string | null;
}

export type TaskStatus = "pending" | "in_progress" | "completed" | "failed" | "awaiting_human";

export interface Task {
  id: string;
  /** Human-authored title / summary of the task. */
  title: string;
  status: TaskStatus;
  messages: ChatMessage[];
  /** ISO timestamp when the task was created. */
  createdAt: string;
  /** ISO timestamp of the last update. */
  updatedAt: string;
  /** Agent assigned to work on this task, if any. */
  assignedAgentId: string | null;
}
