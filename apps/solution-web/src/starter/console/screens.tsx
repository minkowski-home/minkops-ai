import { useState } from "react";
import { Link } from "react-router-dom";
import type { Agent, AgentTeam } from "../types/agent";
import type { HumanInterrupt } from "../types/interrupt";
import { Icon } from "./Icon";
import { PRESET_WORKFLOWS } from "./mockWorkflows";
import type { ActivityItem, PresetWorkflow } from "./types";

function relativeTime(iso: string | null) {
  if (!iso) return "never";
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1_440) return `${Math.floor(minutes / 60)}h ago`;
  return `${Math.floor(minutes / 1_440)}d ago`;
}

function glyphForAgent(name: string) {
  const initial = name.slice(0, 1).toUpperCase();
  return <span className="agent-glyph" aria-hidden="true">{initial}</span>;
}

function AgentRow({ agent, onToggle }: { agent: Agent; onToggle: (id: string) => void }) {
  return (
    <div className={`fleet-row${agent.enabled ? "" : " is-disabled"}`}>
      {glyphForAgent(agent.name)}
      <div className="fleet-row-copy">
        <strong>{agent.name}</strong>
        <span><i className={`status-dot ${agent.status}`} /> {agent.status} · {relativeTime(agent.lastActiveAt)}</span>
      </div>
      <button
        className={`toggle${agent.enabled ? " is-on" : ""}`}
        onClick={() => onToggle(agent.id)}
        aria-label={`${agent.enabled ? "Disable" : "Enable"} ${agent.name}`}
      ><span /></button>
    </div>
  );
}

export function FleetPane({ agents, team, onToggleAgent, onToggleTeam }: {
  agents: Agent[];
  team: AgentTeam;
  onToggleAgent: (id: string) => void;
  onToggleTeam: () => void;
}) {
  const teamAgents = agents.filter((agent) => agent.teamId === team.id);
  const individualAgents = agents.filter((agent) => !agent.teamId);
  return (
    <aside className="fleet-pane">
      <div className="pane-title"><span>Your agents</span><Link to="/agents">Browse</Link></div>
      <div className="fleet-scroll">
        <section className="fleet-section">
          <p className="eyebrow">Team</p>
          <div className="team-card">
            <div>
              <strong>{team.name}</strong>
              <p>{team.description}</p>
              <span>{teamAgents.map((agent) => agent.name).join(", ")}</span>
            </div>
            <button className={`toggle${team.enabled ? " is-on" : ""}`} onClick={onToggleTeam} aria-label={`${team.enabled ? "Disable" : "Enable"} ${team.name}`}><span /></button>
          </div>
        </section>
        <section className="fleet-section">
          <p className="eyebrow">{team.name}</p>
          {teamAgents.map((agent) => <AgentRow key={agent.id} agent={agent} onToggle={onToggleAgent} />)}
        </section>
        <section className="fleet-section">
          <p className="eyebrow">Individual</p>
          {individualAgents.map((agent) => <AgentRow key={agent.id} agent={agent} onToggle={onToggleAgent} />)}
        </section>
      </div>
    </aside>
  );
}

function DecisionChoices({ interrupt, onResolve }: { interrupt: HumanInterrupt; onResolve: (id: string, choice: string) => void }) {
  const options = interrupt.type === "approval"
    ? ["Approve the proposed action", "Keep this for review"]
    : interrupt.type === "escalation"
      ? ["Follow the recommended action", "Leave this in the queue"]
      : ["Accept the recommendation", "Review later"];
  return <div className="decision-options">
    {options.map((option, index) => (
      <button key={option} className="decision-option" onClick={() => onResolve(interrupt.id, option)}>
        <span>{option}</span>{index === 0 ? <em>Suggested</em> : null}
      </button>
    ))}
  </div>;
}

export function AttentionQueue({ interrupts, onResolve }: { interrupts: HumanInterrupt[]; onResolve: (id: string, choice: string) => void }) {
  const pending = interrupts.filter((item) => item.status === "pending");
  const order = { critical: 0, high: 1, medium: 2, low: 3 };
  const sorted = [...pending].sort((a, b) => order[a.priority] - order[b.priority]);
  const summary = ["critical", "high", "medium", "low"] as const;
  return (
    <aside className="attention-pane" id="attention">
      <div className="pane-title"><span>Needs attention {pending.length ? `(${pending.length})` : ""}</span></div>
      {pending.length ? <div className="priority-summary">
        {summary.map((priority) => {
          const count = pending.filter((item) => item.priority === priority).length;
          return count ? <span key={priority} className={`priority-pill ${priority}`}>{count} {priority}</span> : null;
        })}
      </div> : null}
      <div className="attention-scroll">
        {sorted.length ? sorted.map((item) => (
          <article className={`decision-card priority-${item.priority}`} key={item.id}>
            <div className="decision-meta"><span>{item.type}</span><time>{relativeTime(item.createdAt)}</time></div>
            <h3>{item.title}</h3>
            <p>{item.description}</p>
            <small>Raised by <b>{item.agentName}</b> · {item.taskTitle}</small>
            {item.suggestedAction ? <div className="suggested-action">{item.suggestedAction}</div> : null}
            <DecisionChoices interrupt={item} onResolve={onResolve} />
          </article>
        )) : <EmptyState title="All clear" detail="No items need your attention right now. Agents are running smoothly." />}
      </div>
    </aside>
  );
}

function ActivityLedger({ activity }: { activity: ActivityItem[] }) {
  return <section className="activity-ledger">
    <div className="pane-title"><span>Done while you were away</span><span className="ledger-day">Today</span></div>
    <ol>
      {activity.map((item) => (
        <li key={item.id} className={`activity-row is-${item.outcome}`}>
          {glyphForAgent(item.agentName)}
          <div><p>{item.summary}</p><span>{item.agentName} · {item.time}</span></div>
          <b>{item.outcome === "done" ? "Done" : item.outcome === "working" ? "Working" : "Waiting"}</b>
        </li>
      ))}
    </ol>
  </section>;
}

function StartWork({ agents, onStart }: { agents: Agent[]; onStart: (workflow: PresetWorkflow) => void }) {
  const [open, setOpen] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const available = PRESET_WORKFLOWS.filter((workflow) => agents.some((agent) => agent.id === workflow.agentId && agent.enabled));
  return <>
    <button className="button button-primary" onClick={() => setOpen(true)}>Start task</button>
    {open ? <div className="workflow-overlay" role="dialog" aria-modal="true" aria-label="Start a task">
      <div className="workflow-drawer">
        <header><div><p className="eyebrow">Start a task</p><h2>Pick a workflow</h2><p>Planned workflows stay visible here before their connectors and runtime are ready.</p></div><button className="icon-button" onClick={() => setOpen(false)} aria-label="Close"><Icon name="x" size={17} /></button></header>
        <div className="workflow-list">
          {available.map((workflow) => {
            const agent = agents.find((candidate) => candidate.id === workflow.agentId);
            return <button key={workflow.id} className="workflow-card" disabled={workflow.availability === "planned"} onClick={() => { onStart(workflow); setOpen(false); }}>
              {glyphForAgent(agent?.name ?? "Agent")}<span><strong>{workflow.label}</strong><small>{workflow.detail}</small><em>{workflow.availability === "planned" ? "Planned — implementation pending" : agent?.name}</em></span><Icon name="chevronRight" size={16} />
            </button>;
          })}
        </div>
        <div className="custom-task">
          <button className="button button-ghost" onClick={() => setCustomOpen((current) => !current)}>{customOpen ? "Hide custom task" : "Write a custom task"}</button>
          {customOpen ? <form onSubmit={(event) => { event.preventDefault(); if (!draft.trim()) return; onStart({ id: `custom-${Date.now()}`, agentId: "agent-imel", label: "Custom task", detail: draft.trim(), outcome: "I’ve received the task and will return with the next decision, if there is one.", availability: "ready" }); setDraft(""); setOpen(false); }}>
            <label htmlFor="custom-task">Describe the work</label><textarea id="custom-task" value={draft} onChange={(event) => setDraft(event.target.value)} rows={3} placeholder="Use this only when none of the workflows fit." />
            <button className="button button-primary" type="submit" disabled={!draft.trim()}>Hand to Imel</button>
          </form> : null}
        </div>
      </div>
    </div> : null}
  </>;
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <div className="empty-state"><span><Icon name="check" size={18} /></span><strong>{title}</strong><p>{detail}</p></div>;
}

export function DashboardScreen(props: {
  agents: Agent[];
  team: AgentTeam;
  activity: ActivityItem[];
  interrupts: HumanInterrupt[];
  onToggleAgent: (id: string) => void;
  onToggleTeam: () => void;
  onResolve: (id: string, choice: string) => void;
  onStart: (workflow: PresetWorkflow) => void;
}) {
  return <div className="console-workspace">
    <FleetPane agents={props.agents} team={props.team} onToggleAgent={props.onToggleAgent} onToggleTeam={props.onToggleTeam} />
    <section className="operator-pane">
      <div className="operator-intro"><div><p className="eyebrow">Operator desk</p><h2>Here&apos;s what changed.</h2><p>Your fleet worked through the routine work. The only items here are the ones that need you.</p></div><StartWork agents={props.agents} onStart={props.onStart} /></div>
      <ActivityLedger activity={props.activity} />
    </section>
    <AttentionQueue interrupts={props.interrupts} onResolve={props.onResolve} />
  </div>;
}

export function TasksScreen({ activity, agents, onStart }: { activity: ActivityItem[]; agents: Agent[]; onStart: (workflow: PresetWorkflow) => void }) {
  return <section className="route-screen work-screen"><header className="route-heading"><div><p className="eyebrow">Work ledger</p><h2>Nothing starts with a blank box.</h2><p>Use a preset to give an employee work it already knows how to complete.</p></div><StartWork agents={agents} onStart={onStart} /></header><ActivityLedger activity={activity} /></section>;
}

export function AgentsScreen({ agents, onToggleAgent }: { agents: Agent[]; onToggleAgent: (id: string) => void }) {
  return <section className="route-screen"><header className="route-heading"><div><p className="eyebrow">Your fleet</p><h2>Hire for a role, not a task.</h2><p>Each employee owns a bounded kind of work and brings decisions back when they exceed policy.</p></div></header><div className="agent-grid">{agents.map((agent) => <article className="agent-card" key={agent.id}>{glyphForAgent(agent.name)}<div><p className="agent-card-status">{agent.enabled ? agent.status : "disabled"}</p><h3>{agent.name}</h3><p>{agent.description}</p></div><footer><span>{agent.category}</span><button className={`toggle${agent.enabled ? " is-on" : ""}`} onClick={() => onToggleAgent(agent.id)} aria-label={`${agent.enabled ? "Disable" : "Enable"} ${agent.name}`}><span /></button></footer></article>)}</div></section>;
}

export function PlaceholderScreen({ name, icon }: { name: string; icon: "analytics" | "settings" }) {
  return <section className="route-screen placeholder-screen"><header className="route-heading"><div><p className="eyebrow">{name}</p><h2>{name}</h2></div></header><div className="placeholder-card"><Icon name={icon} size={22} /><h3>Not designed yet</h3><p>This route is present, but there is no source design for it. It is intentionally left blank.</p></div></section>;
}
