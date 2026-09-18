const { Button, Eyebrow, AgentTile, Icon, StatusDot } = window.MinkopsDesignSystem_6c27f0;

const ROSTER = [
  { name: "Imel", tool: "Email handler", domain: "Generic", glyph: "email", status: "Live" },
  { name: "Kall", tool: "Customer support rep", domain: "Generic", glyph: "support", status: "Live" },
  { name: "Leed", tool: "Lead generation caller", domain: "Generic", glyph: "sales", status: "Next" },
  { name: "Eko", tool: "Social media handler", domain: "Generic", glyph: "social", status: "Next" },
  { name: "Floc", tool: "Content creator", domain: "Generic", glyph: "writer", status: "Next" },
  { name: "Insi", tool: "Business analyst", domain: "Generic", glyph: "analyst", status: "In build" },
  { name: "Kim", tool: "Store manager's assistant", domain: "Generic", glyph: "retail", status: "In build" },
  { name: "Ora", tool: "Moodboard generator", domain: "Interior design", glyph: "designer", status: "In build" },
  { name: "Cruz", tool: "Manager's assistant", domain: "Fast food", glyph: "manager", status: "In build" },
  { name: "Hosi", tool: "Front of house", domain: "Fast food", glyph: "host", status: "In build" },
  { name: "Prex", tool: "Back of house", domain: "Fast food", glyph: "kitchen", status: "In build" }
];

function Hero({ onAccess }) {
  return (
    <section style={{ padding: "96px 32px 72px", background: "var(--surface-page)" }}>
      <div style={{ maxWidth: "var(--container-w)", margin: "0 auto", display: "grid", gap: "32px" }}>
        <Eyebrow rule>A suite of AI employees</Eyebrow>
        <h1 style={{ font: "var(--fw-semibold) var(--fs-5xl)/1.04 var(--font-display)", letterSpacing: "var(--ls-display)", maxWidth: "18ch" }}>
          Intelligence, <span style={{ color: "var(--brand-rust)" }}>redefined</span>
        </h1>
        <p style={{ margin: 0, maxWidth: "var(--measure)", font: "var(--type-body-lg)", color: "var(--text-secondary)" }}>
          Hire an AI employee the way you'd hire a person — for a specific role, with real
          responsibility. Except it starts on day one, works nights and weekends, and never
          asks for a raise.
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
          <Button size="lg" variant="primary" onClick={onAccess} iconRight={<Icon name="chevronRight" size={16} />}>Request access</Button>
          <Button size="lg" variant="secondary">See how they work together</Button>
          <span style={{ marginLeft: "8px" }}><StatusDot status="active" pulse label="Imel and Kall run our own inbox today" /></span>
        </div>
      </div>
    </section>
  );
}

function RosterGrid({ onAccess }) {
  return (
    <Section eyebrow="The roster · 11 agents" title="Know your future employees"
      lead="Each agent replaces one role with disjoint skills, not one task. They intercommunicate and read the same company knowledge a human colleague would."
      tone="sunken">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(248px, 1fr))", gap: "12px" }}>
        {ROSTER.map((a) => <AgentTile key={a.name} {...a} onClick={onAccess} />)}
      </div>
      <p style={{ margin: 0, font: "var(--type-mono)", color: "var(--text-muted)" }}>
        Live = running in production today. Next = in active development. In build = designed, not yet shipped.
      </p>
    </Section>
  );
}

Object.assign(window, { Hero, RosterGrid, ROSTER });
