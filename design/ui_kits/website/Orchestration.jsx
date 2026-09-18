const { FlowNode, FlowArrow, Eyebrow, Button, Icon } = window.MinkopsDesignSystem_6c27f0;

const FLOWS = [
  { title: "01 · Automated marketing campaign", desc: "From idea to published ad copy without human intervention.",
    nodes: [ { agent: "Floc", role: "Copywriter" }, { arrow: "Drafts copy" }, { agent: "Ora", role: "Visual experience" }, { arrow: "Generates assets" }, { output: "Published campaign" } ] },
  { title: "02 · Intelligent social engagement", desc: "Handling public perception and private support simultaneously.",
    nodes: [ { agent: "Eko", role: "Social handler" }, { arrow: "Detects complaint" }, { agent: "Kall", role: "Support rep" }, { arrow: "Resolves ticket" }, { agent: "Eko", role: "Social handler" } ] },
  { title: "03 · QSR operations", desc: "Zero-man fast food store management.",
    nodes: [ { agent: "Hosi", role: "Front of house" }, { arrow: "Order taken" }, { agent: "Cruz", role: "Store manager" }, { arrow: "Relays ticket" }, { agent: "Prex", role: "Kitchen staff" } ] }
];

function OrchestrationPage({ onAccess }) {
  return (
    <>
      <section style={{ padding: "80px 32px 56px" }}>
        <div style={{ maxWidth: "var(--container-w)", margin: "0 auto", display: "grid", gap: "20px" }}>
          <Eyebrow rule>Orchestration</Eyebrow>
          <h1 style={{ font: "var(--fw-semibold) var(--fs-4xl)/1.06 var(--font-display)", letterSpacing: "var(--ls-display)", maxWidth: "20ch" }}>Orchestrated intelligence</h1>
          <p style={{ margin: 0, maxWidth: "var(--measure)", font: "var(--type-body-lg)", color: "var(--text-secondary)" }}>
            Agents don't just chat. They work together — one hands off to the next through a shared
            knowledge graph and policy model, and a human only steps in above the authority threshold.
          </p>
        </div>
      </section>

      {FLOWS.map((flow, i) => (
        <section key={flow.title} style={{ padding: "48px 32px", borderTop: "1px solid var(--border-hairline)", background: i % 2 ? "var(--surface-sunken)" : "var(--surface-page)" }}>
          <div style={{ maxWidth: "var(--container-w)", margin: "0 auto", display: "grid", gap: "20px" }}>
            <div style={{ display: "grid", gap: "6px" }}>
              <h2 style={{ font: "var(--type-h3)", fontSize: "var(--fs-xl)" }}>{flow.title}</h2>
              <p style={{ margin: 0, font: "var(--type-body)", color: "var(--text-secondary)" }}>{flow.desc}</p>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "4px", flexWrap: "wrap" }}>
              {flow.nodes.map((n, j) => n.arrow
                ? <FlowArrow key={j} label={n.arrow} />
                : <FlowNode key={j} agent={n.agent} role={n.role} output={Boolean(n.output)} label={n.output} />)}
            </div>
          </div>
        </section>
      ))}

      <section style={{ padding: "64px 32px", borderTop: "1px solid var(--border-hairline)" }}>
        <div style={{ maxWidth: "var(--container-w)", margin: "0 auto", display: "flex", alignItems: "center", gap: "20px", flexWrap: "wrap" }}>
          <h2 style={{ font: "var(--type-h2)" }}>Build your fleet</h2>
          <span style={{ marginLeft: "auto" }}>
            <Button size="lg" variant="primary" onClick={onAccess} iconRight={<Icon name="chevronRight" size={16} />}>Request access</Button>
          </span>
        </div>
      </section>
    </>
  );
}

Object.assign(window, { OrchestrationPage });
