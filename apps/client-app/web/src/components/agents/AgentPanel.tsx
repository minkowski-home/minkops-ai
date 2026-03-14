/**
 * AgentPanel — left pane of the dashboard.
 *
 * Displays the tenant's subscribed agents and agent teams with
 * one-click enable/disable toggles. State is local for now; wire to
 * PATCH /api/agents/:id and PATCH /api/agent-teams/:id when the
 * backend is ready.
 *
 * Disable vs unsubscribe distinction: toggling the switch sets
 * `enabled: false` (agent stays provisioned but won't receive tasks).
 * A future "Unsubscribe" action (context menu / kebab) will remove the
 * agent from the tenant's roster entirely.
 */

import { useState, useCallback } from "react";
import type { Agent, AgentTeam } from "../../types/agent";
import { MOCK_AGENTS, MOCK_AGENT_TEAMS } from "../../mock/agents";
import "./AgentPanel.css";

/** Returns a human-readable relative time label. */
function relativeTime(isoString: string | null): string {
  if (!isoString) return "never";
  const diffMs = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

/** Derive a short 2-char abbreviation from agent name for the icon. */
function agentInitials(name: string): string {
  return name.slice(0, 2).toUpperCase();
}

interface ToggleSwitchProps {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}

function ToggleSwitch({ id, checked, onChange, label }: ToggleSwitchProps) {
  return (
    <label className="toggle-switch" title={checked ? "Disable" : "Enable"}>
      <input
        id={id}
        type="checkbox"
        checked={checked}
        aria-label={label}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="toggle-track" />
    </label>
  );
}

export default function AgentPanel() {
  const [agents, setAgents] = useState<Agent[]>(MOCK_AGENTS);
  const [teams, setTeams] = useState<AgentTeam[]>(MOCK_AGENT_TEAMS);

  const toggleAgent = useCallback((agentId: string, enabled: boolean) => {
    setAgents((prev) =>
      prev.map((a) =>
        a.id === agentId
          ? { ...a, enabled, status: enabled ? "idle" : "disabled" }
          : a
      )
    );
    // TODO: PATCH /api/agents/:agentId { enabled }
  }, []);

  const toggleTeam = useCallback((teamId: string, enabled: boolean) => {
    setTeams((prev) =>
      prev.map((t) => (t.id === teamId ? { ...t, enabled } : t))
    );
    // Toggling a team also toggles all its member agents
    setAgents((prev) =>
      prev.map((a) =>
        a.teamId === teamId
          ? { ...a, enabled, status: enabled ? "idle" : "disabled" }
          : a
      )
    );
    // TODO: PATCH /api/agent-teams/:teamId { enabled }
  }, []);

  // Agents that are not part of any team
  const standaloneAgents = agents.filter((a) => a.teamId === null);

  return (
    <div className="agent-panel">
      <div className="agent-panel-header">
        <p className="agent-panel-title">Your Agents</p>
        {/* Placeholder action — will open agent marketplace */}
        <button className="agent-browse-btn" type="button">
          + Browse &amp; add agents
        </button>
      </div>

      <div className="agent-panel-body">
        {/* ---- Agent Teams ---- */}
        {teams.length > 0 && (
          <>
            <p className="agent-section-label">Teams</p>
            {teams.map((team) => {
              const memberAgents = agents.filter((a) => team.agentIds.includes(a.id));
              return (
                <div key={team.id} className="agent-team-card">
                  <div className="agent-team-header">
                    <span className="agent-team-name">{team.name}</span>
                    <ToggleSwitch
                      id={`team-toggle-${team.id}`}
                      checked={team.enabled}
                      onChange={(v) => toggleTeam(team.id, v)}
                      label={`Toggle ${team.name}`}
                    />
                  </div>
                  <p className="agent-team-desc">{team.description}</p>
                  <span className="agent-team-members">
                    {memberAgents.map((a) => a.name).join(", ")}
                  </span>
                </div>
              );
            })}
          </>
        )}

        {/* ---- Agents inside teams (shown individually below) ---- */}
        {teams.map((team) => {
          const memberAgents = agents.filter((a) => team.agentIds.includes(a.id));
          if (!memberAgents.length) return null;
          return (
            <div key={`team-agents-${team.id}`}>
              <p className="agent-section-label">{team.name}</p>
              {memberAgents.map((agent) => (
                <AgentRow
                  key={agent.id}
                  agent={agent}
                  onToggle={toggleAgent}
                />
              ))}
            </div>
          );
        })}

        {/* ---- Standalone agents ---- */}
        {standaloneAgents.length > 0 && (
          <>
            <p className="agent-section-label">Individual</p>
            {standaloneAgents.map((agent) => (
              <AgentRow key={agent.id} agent={agent} onToggle={toggleAgent} />
            ))}
          </>
        )}
      </div>
    </div>
  );
}

interface AgentRowProps {
  agent: Agent;
  onToggle: (id: string, enabled: boolean) => void;
}

function AgentRow({ agent, onToggle }: AgentRowProps) {
  return (
    <div className={`agent-row${agent.enabled ? "" : " agent-disabled"}`}>
      <div className={`agent-row-icon${agent.enabled ? "" : " disabled"}`}>
        {agentInitials(agent.name)}
      </div>

      <div className="agent-row-body">
        <div className="agent-row-name">{agent.name}</div>
        <div className="agent-row-meta">
          <span className={`agent-status-dot ${agent.status}`} aria-hidden="true" />
          <span className="agent-row-status-text">{agent.status}</span>
          <span className="agent-row-last-active">
            {relativeTime(agent.lastActiveAt)}
          </span>
        </div>
      </div>

      <ToggleSwitch
        id={`agent-toggle-${agent.id}`}
        checked={agent.enabled}
        onChange={(v) => onToggle(agent.id, v)}
        label={`Toggle ${agent.name}`}
      />
    </div>
  );
}
