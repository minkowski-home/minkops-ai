/**
 * Agent domain types.
 *
 * These interfaces model the shape of data the backend is expected to
 * return. Backend engineers should treat these as the API contract for
 * the /api/agents and /api/agent-teams endpoints.
 */

export type AgentStatus = "active" | "idle" | "error" | "disabled";

export interface Agent {
  id: string;
  name: string;
  /** Short one-line description of what this agent does. */
  description: string;
  /** Category tag for grouping/filtering in the UI. */
  category: "communication" | "research" | "data" | "scheduling" | "general";
  status: AgentStatus;
  /** ISO timestamp of the last task processed by this agent. */
  lastActiveAt: string | null;
  /** Whether the tenant has subscribed to / enabled this agent. */
  enabled: boolean;
  /** ID of the team this agent belongs to, if any. */
  teamId: string | null;
}

export interface AgentTeam {
  id: string;
  name: string;
  description: string;
  /** IDs of agents that form this team. */
  agentIds: string[];
  /** true if all agents in the team are enabled. */
  enabled: boolean;
}
