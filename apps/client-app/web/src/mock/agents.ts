/**
 * Mock agent data for frontend development.
 * Replace with real API calls when backend is ready.
 * Shape must match src/types/agent.ts.
 */

import type { Agent, AgentTeam } from "../types/agent";

export const MOCK_AGENTS: Agent[] = [
  {
    id: "agent-imel",
    name: "Imel",
    description: "Handles inbound email triage, drafts responses, and routes tickets.",
    category: "communication",
    status: "active",
    lastActiveAt: new Date(Date.now() - 1000 * 60 * 4).toISOString(),
    enabled: true,
    teamId: "team-cx"
  },
  {
    id: "agent-kall",
    name: "Kall",
    description: "Resolves support tickets by querying the knowledge base.",
    category: "research",
    status: "idle",
    lastActiveAt: new Date(Date.now() - 1000 * 60 * 22).toISOString(),
    enabled: true,
    teamId: "team-cx"
  },
  {
    id: "agent-scout",
    name: "Scout",
    description: "Researches leads, summarises web content, and populates CRM fields.",
    category: "research",
    status: "active",
    lastActiveAt: new Date(Date.now() - 1000 * 60 * 2).toISOString(),
    enabled: true,
    teamId: null
  },
  {
    id: "agent-synapse",
    name: "Synapse",
    description: "Aggregates data from multiple sources and produces structured reports.",
    category: "data",
    status: "idle",
    lastActiveAt: new Date(Date.now() - 1000 * 60 * 60 * 3).toISOString(),
    enabled: true,
    teamId: null
  },
  {
    id: "agent-aria",
    name: "Aria",
    description: "Manages calendar scheduling, sends invites, and handles rescheduling.",
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
    name: "CX Response Team",
    description: "Handles end-to-end customer communication and support ticket resolution.",
    agentIds: ["agent-imel", "agent-kall"],
    enabled: true
  }
];
