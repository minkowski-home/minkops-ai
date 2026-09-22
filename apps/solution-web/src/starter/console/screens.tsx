import { useState } from "react";
import type { ActiveTask, AttentionItem, HiredTeam, WorkflowInstance } from "../workspace/initialState";
import { Icon } from "./Icon";

function WorkflowCard({ workflow, onStart, onOpen }: { workflow: WorkflowInstance; onStart: () => void; onOpen: () => void }) {
  return <article className="workflow-launch-card">
    <div className="workflow-launch-card__mark"><Icon name="tasks" size={20} /></div>
    <div className="workflow-launch-card__body"><p className="eyebrow">{workflow.team}</p><h3>{workflow.title}</h3><p>{workflow.description}</p></div>
    <footer><button className="button button-primary" onClick={onStart}>Start</button><button className="button button-ghost" onClick={onOpen}>Edit</button></footer>
  </article>;
}

function AttentionPane({ activeTasks, attention, onResolve }: { activeTasks: ActiveTask[]; attention: AttentionItem[]; onResolve: (id: string, decision: string) => void }) {
  return <aside className="attention-pane">
    <section className="attention-section"><div className="pane-title"><span>Active tasks</span><span>{activeTasks.length}</span></div>
      {activeTasks.length ? <ul className="compact-list">{activeTasks.map((task) => <li key={task.id}><Icon name="tasks" size={15} /><div><strong>{task.title}</strong><span>Running</span></div></li>)}</ul> : <p className="quiet-state">No active tasks.</p>}
    </section>
    <section className="attention-section"><div className="pane-title"><span>Needs attention</span><span>{attention.length}</span></div>
      {attention.length ? <div className="attention-list">{attention.map((item) => <article className="attention-card" key={item.id}><p className="eyebrow">Review</p><h3>{item.title}</h3><p>{item.detail}</p><div><button className="button button-primary" onClick={() => onResolve(item.id, "Approved")}>Approve</button><button className="button button-ghost" onClick={() => onResolve(item.id, "Rejected")}>Reject</button></div></article>)}</div> : <p className="quiet-state">Nothing needs your decision.</p>}
    </section>
    <section className="attention-section"><div className="pane-title"><span>Handoffs</span><span>0</span></div><p className="quiet-state">No handoffs waiting.</p></section>
  </aside>;
}

function WorkflowEditor({ workflow, onClose, onUpdate, onAddInstance }: { workflow: WorkflowInstance; onClose: () => void; onUpdate: (configuration: Record<string, string>) => void; onAddInstance: () => void }) {
  const [configuration, setConfiguration] = useState(workflow.configuration);
  return <div className="workflow-overlay" role="dialog" aria-modal="true" aria-label={`Edit ${workflow.title}`}><section className="workflow-drawer"><header><div><p className="eyebrow">Activated workflow</p><h2>{workflow.title}</h2><p>{workflow.team}</p></div><button className="icon-button" onClick={onClose} aria-label="Close"><Icon name="x" size={17} /></button></header><form onSubmit={(event) => { event.preventDefault(); onUpdate(configuration); onClose(); }}><div className="workflow-settings">{Object.entries(configuration).map(([label, value]) => <label key={label}>{label}<input value={value} onChange={(event) => setConfiguration((current) => ({ ...current, [label]: event.target.value }))} /></label>)}</div><button className="button button-primary" type="submit">Save changes</button><button className="button button-ghost" type="button" onClick={onAddInstance}>Add another instance</button></form></section></div>;
}

export function DashboardScreen({ workflows, activeTasks, attention, history, onStart, onResolve, onUpdate, onAddInstance }: { workflows: WorkflowInstance[]; activeTasks: ActiveTask[]; attention: AttentionItem[]; history: string[]; onStart: (workflow: WorkflowInstance) => void; onResolve: (id: string, decision: string) => void; onUpdate: (id: string, configuration: Record<string, string>) => void; onAddInstance: (workflow: WorkflowInstance) => void }) {
  const [editing, setEditing] = useState<WorkflowInstance | null>(null);
  return <div className="dashboard-workspace"><main className="dashboard-main"><header className="launchpad-heading"><p className="eyebrow">Dashboard</p><h2>Start your day</h2><p>Your saved workflows are ready when you are.</p></header><section className="workflow-launch-grid">{workflows.map((workflow) => <WorkflowCard key={workflow.id} workflow={workflow} onStart={() => onStart(workflow)} onOpen={() => setEditing(workflow)} />)}</section><section className="history-section"><div className="section-heading"><div><p className="eyebrow">Task history</p><h3>Finished tasks</h3></div></div>{history.length ? <ul className="history-list">{history.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="quiet-state history-empty">Completed work will appear here.</p>}</section></main><AttentionPane activeTasks={activeTasks} attention={attention} onResolve={onResolve} />{editing ? <WorkflowEditor workflow={editing} onClose={() => setEditing(null)} onUpdate={(configuration) => onUpdate(editing.id, configuration)} onAddInstance={() => { onAddInstance(editing); setEditing(null); }} /> : null}</div>;
}

export function AgentsScreen({ teams }: { teams: HiredTeam[] }) {
  return <section className="route-screen"><header className="route-heading"><div><p className="eyebrow">Your agents</p><h2>Hired teams</h2><p>These teams make the workflow presets available to your workspace.</p></div></header><div className="agent-grid">{teams.map((team) => <article className="agent-card" key={team.id}><Icon name="agents" size={22} /><div><p className="eyebrow">Active team</p><h3>{team.name}</h3><p>{team.description}</p></div><footer><span>{team.workflows.length} workflow{team.workflows.length === 1 ? "" : "s"} available</span></footer></article>)}</div></section>;
}

export function WorkflowsScreen({ workflows, onUpdate, onAddInstance, onStart }: { workflows: WorkflowInstance[]; onUpdate: (id: string, configuration: Record<string, string>) => void; onAddInstance: (workflow: WorkflowInstance) => void; onStart: (workflow: WorkflowInstance) => void }) {
  const [editing, setEditing] = useState<WorkflowInstance | null>(null);
  return <section className="route-screen"><header className="route-heading"><div><p className="eyebrow">Workflow presets</p><h2>Your workflows</h2><p>Set up a preset once, then run any configured instance from the dashboard.</p></div></header><div className="workflow-catalog">{workflows.map((workflow) => <article className="catalog-row" key={workflow.id}><div><p className="eyebrow">Configured</p><h3>{workflow.title}</h3><p>{workflow.description}</p></div><div><button className="button button-ghost" onClick={() => setEditing(workflow)}>Configure</button><button className="button button-primary" onClick={() => onStart(workflow)}>Start</button></div></article>)}</div>{editing ? <WorkflowEditor workflow={editing} onClose={() => setEditing(null)} onUpdate={(configuration) => onUpdate(editing.id, configuration)} onAddInstance={() => { onAddInstance(editing); setEditing(null); }} /> : null}</section>;
}
