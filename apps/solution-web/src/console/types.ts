import type { Agent, AgentTeam } from "../types/agent";
import type { HumanInterrupt } from "../types/interrupt";

export type ConsoleRoute = "dashboard" | "agents" | "tasks" | "analytics" | "settings";

export interface ActivityItem {
  id: string;
  agentName: string;
  summary: string;
  time: string;
  outcome: "done" | "working" | "waiting";
}

export interface PresetWorkflow {
  id: string;
  agentId: string;
  label: string;
  detail: string;
  outcome: string;
}

export interface ConsoleState {
  agents: Agent[];
  team: AgentTeam;
  interrupts: HumanInterrupt[];
  activity: ActivityItem[];
}
