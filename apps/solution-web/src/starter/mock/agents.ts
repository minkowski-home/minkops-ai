/**
 * Mock agent data for frontend development.
 * Replace with real API calls when backend is ready.
 * Shape must match src/types/agent.ts.
 */

import type { Agent, AgentTeam } from "../types/agent";

export const MOCK_AGENTS: Agent[] = [
  {
    id: "agent-imel",
    name: "Intake",
    description: "Normalises incoming work and prepares it for a configured workflow.",
    category: "communication",
    status: "active",
    lastActiveAt: new Date(Date.now() - 1000 * 60 * 4).toISOString(),
    enabled: true,
    teamId: "team-cx"
  },
  {
    id: "agent-kall",
    name: "Reviewer",
    description: "Routes exceptions and approval decisions to the right operator.",
    category: "research",
    status: "idle",
    lastActiveAt: new Date(Date.now() - 1000 * 60 * 22).toISOString(),
    enabled: true,
    teamId: "team-cx"
  },
  {
    id: "agent-scout",
    name: "Sources",
    description: "Connects approved external sources and records their sync state.",
    category: "research",
    status: "active",
    lastActiveAt: new Date(Date.now() - 1000 * 60 * 2).toISOString(),
    enabled: true,
    teamId: null
  },
  {
    id: "agent-synapse",
    name: "Ledger",
    description: "Reconciles structured records and prepares durable exports.",
    category: "data",
    status: "idle",
    lastActiveAt: new Date(Date.now() - 1000 * 60 * 60 * 3).toISOString(),
    enabled: true,
    teamId: null
  },
  {
    id: "agent-aria",
    name: "Scheduler",
    description: "Runs approved workflows on their configured cadence.",
    category: "scheduling",
    status: "disabled",
    lastActiveAt: null,
    enabled: false,
    teamId: null
  }
];

export const MOCK_AGENT_TEAMS: AgentTeam[] = [
  {
    id: "team-cx",
    name: "Operations workflow",
    description: "Prepares work and routes material decisions to a human operator.",
    agentIds: ["agent-imel", "agent-kall"],
    enabled: true
  }
];
