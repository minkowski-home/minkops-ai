const { AgentRow, Toggle, Eyebrow, Button, Icon, Card } = window.MinkopsDesignSystem_6c27f0;

function AgentsPane({ agents, team, selectedId, onSelect, onToggleAgent, onToggleTeam }) {
  const teamMembers = agents.filter((a) => a.team === team.name);
  const standalone = agents.filter((a) => !a.team);
  return (
    <section style={{ width: "var(--pane-agents-w)", flex: "none", display: "flex", flexDirection: "column", borderRight: "1px solid var(--border-hairline)", background: "var(--surface-page)", minHeight: 0 }}>
      <PaneHeader title="Your agents" action={
        <Button size="sm" variant="ghost">+ Browse</Button>
      } />
      <div style={{ overflowY: "auto", padding: "10px", display: "grid", gap: "12px", alignContent: "start" }}>
        <div style={{ display: "grid", gap: "6px" }}>
          <Eyebrow>Teams</Eyebrow>
          <Card tone="sunken" pad="10px" style={{ display: "grid", gap: "6px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ font: "var(--fw-medium) var(--fs-sm)/1.1 var(--font-display)" }}>{team.name}</span>
              <span style={{ marginLeft: "auto" }}><Toggle checked={team.enabled} onChange={onToggleTeam} label="" /></span>
            </div>
            <p style={{ margin: 0, font: "var(--fw-regular) var(--fs-xs)/1.5 var(--font-text)", color: "var(--text-secondary)" }}>{team.description}</p>
            <span style={{ font: "var(--type-mono)", color: "var(--text-muted)" }}>{team.members.join(", ")}</span>
          </Card>
        </div>

        <div style={{ display: "grid", gap: "2px" }}>
          <Eyebrow>{team.name}</Eyebrow>
          {teamMembers.map((a) => (
            <AgentRow key={a.id} {...a} selected={a.id === selectedId} onSelect={() => onSelect(a.id)} onToggle={(v) => onToggleAgent(a.id, v)} />
          ))}
        </div>

        <div style={{ display: "grid", gap: "2px" }}>
          <Eyebrow>Individual</Eyebrow>
          {standalone.map((a) => (
            <AgentRow key={a.id} {...a} selected={a.id === selectedId} onSelect={() => onSelect(a.id)} onToggle={(v) => onToggleAgent(a.id, v)} />
          ))}
        </div>
      </div>
    </section>
  );
}

Object.assign(window, { AgentsPane });
