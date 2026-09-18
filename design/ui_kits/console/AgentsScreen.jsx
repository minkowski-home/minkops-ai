const { AgentTile, Eyebrow, Button, Icon } = window.MinkopsDesignSystem_6c27f0;

const CATALOGUE = [
  { name: "Imel", tool: "Email handler", domain: "Generic", glyph: "email", status: "Hired" },
  { name: "Kall", tool: "Customer support rep", domain: "Generic", glyph: "support", status: "Hired" },
  { name: "Leed", tool: "Lead generation caller", domain: "Generic", glyph: "sales", status: "Available" },
  { name: "Eko", tool: "Social media handler", domain: "Generic", glyph: "social", status: "Available" },
  { name: "Floc", tool: "Content creator", domain: "Generic", glyph: "writer", status: "Available" },
  { name: "Insi", tool: "Business analyst", domain: "Generic", glyph: "analyst", status: "Available" },
  { name: "Kim", tool: "Store manager's assistant", domain: "Generic", glyph: "retail", status: "In build" },
  { name: "Ora", tool: "Moodboard generator", domain: "Interior design", glyph: "designer", status: "In build" },
  { name: "Cruz", tool: "Manager's assistant", domain: "Fast food", glyph: "manager", status: "In build" },
  { name: "Hosi", tool: "Front of house", domain: "Fast food", glyph: "host", status: "In build" },
  { name: "Prex", tool: "Back of house", domain: "Fast food", glyph: "kitchen", status: "In build" }
];

function AgentsScreen() {
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "28px 32px", display: "grid", gap: "18px", alignContent: "start" }}>
      <div style={{ display: "grid", gap: "8px" }}>
        <Eyebrow rule>Roster · 11 agents</Eyebrow>
        <h2 style={{ font: "var(--type-h2)" }}>Browse &amp; add agents</h2>
        <p style={{ margin: 0, maxWidth: "var(--measure)", font: "var(--type-body)", color: "var(--text-secondary)" }}>
          Each agent replaces one role, not one task. Hire the ones that match the work you're doing by hand today.
        </p>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(232px, 1fr))", gap: "12px" }}>
        {CATALOGUE.map((a) => <AgentTile key={a.name} {...a} onClick={() => {}} />)}
      </div>
    </div>
  );
}

Object.assign(window, { AgentsScreen });
