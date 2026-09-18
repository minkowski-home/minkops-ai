const { Eyebrow, Card, Badge, Button, Icon } = window.MinkopsDesignSystem_6c27f0;

const POSTS = [
  { tag: "Product proof", title: "Real, not a mockup", date: "2026-03-12", read: "3 min",
    excerpt: "A lot of AI agent demos are a slide deck wearing a UI skin. Here's the opposite: Imel handed an email it has never seen, start to finish, no cuts." },
  { tag: "Founder", title: "A five-person team needs leverage, not headcount", date: "2026-02-18", read: "4 min",
    excerpt: "The moment founders want to move faster, their first move is to hire. We've gone the opposite way — we build the AI employees we're selling, and run our own company on them first." },
  { tag: "Engineering", title: "Why our agents wait for a human at first", date: "2026-02-06", read: "5 min",
    excerpt: "Early graphs are deliberately more deterministic: more interrupts, more waiting for feedback. That human interaction data is the training signal." }
];

function BlogPage() {
  return (
    <Section eyebrow="Blog" title="Notes from a company that runs on its own product"
      lead="No invented metrics, no implied customers. We write about what is actually running.">
      <div style={{ display: "grid", gap: "12px", maxWidth: 860 }}>
        {POSTS.map((p) => (
          <Card key={p.title} style={{ display: "grid", gap: "8px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <Badge tone="neutral">{p.tag}</Badge>
              <span style={{ marginLeft: "auto", font: "var(--type-mono)", color: "var(--text-faint)" }}>{p.date} · {p.read}</span>
            </div>
            <h3 style={{ font: "var(--type-h3)" }}>{p.title}</h3>
            <p style={{ margin: 0, maxWidth: "var(--measure)", font: "var(--type-body)", color: "var(--text-secondary)" }}>{p.excerpt}</p>
            <a href="#" style={{ font: "var(--type-body-sm)", fontWeight: "var(--fw-medium)", justifySelf: "start" }}>Read the post</a>
          </Card>
        ))}
      </div>
    </Section>
  );
}

function AboutPage() {
  return (
    <>
      <Section eyebrow="About" title="Minkops is under ten people"
        lead="Most of us are wearing four or five hats before lunch. What makes that possible isn't hustle — it's that we build the AI employees we're selling before we sell them, and run our own company on them first.">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "12px" }}>
          {[["Under 10", "People on the team"], ["2", "Agents running in production"], ["24×7", "How a fleet runs — continuously, not as jobs"]].map(([n, l]) => (
            <Card key={l} tone="sunken" style={{ display: "grid", gap: "6px" }}>
              <span style={{ font: "var(--fw-semibold) var(--fs-3xl)/1 var(--font-display)", letterSpacing: "var(--ls-display)" }}>{n}</span>
              <span style={{ font: "var(--type-body-sm)", color: "var(--text-secondary)" }}>{l}</span>
            </Card>
          ))}
        </div>
      </Section>
      <Section eyebrow="Family" title="A product of Minkowski Home" tone="sunken"
        lead="Minkops sits alongside Myndral and Minkowski Home. Frontends live in apps/, agents and data work in services/ — the same discipline applies to the brand." />
    </>
  );
}

const ROLES = [
  { title: "Agent runtime engineer", place: "Toronto / Remote", type: "Full-time" },
  { title: "Applied AI engineer — evaluation", place: "Remote", type: "Full-time" },
  { title: "Founding designer", place: "Toronto / Remote", type: "Full-time" },
  { title: "Data engineer — knowledge graph", place: "Remote", type: "Contract" }
];

function CareersPage() {
  return (
    <Section eyebrow="Careers" title="Work on the thing that replaces the work"
      lead="Small team, real responsibility, no hand-holding. Verification and HR enquiries go to hr@minkops.com.">
      <div style={{ border: "1px solid var(--border-default)", borderRadius: "var(--radius-3)", overflow: "hidden", maxWidth: 860 }}>
        {ROLES.map((r, i) => (
          <div key={r.title} style={{ display: "flex", alignItems: "center", gap: "12px", padding: "14px 16px", borderTop: i ? "1px solid var(--border-hairline)" : "none" }}>
            <span style={{ display: "grid", gap: "3px" }}>
              <span style={{ font: "var(--type-h4)" }}>{r.title}</span>
              <span style={{ font: "var(--type-mono)", color: "var(--text-muted)" }}>{r.place} · {r.type}</span>
            </span>
            <span style={{ marginLeft: "auto" }}>
              <Button variant="secondary" size="sm" iconRight={<Icon name="chevronRight" size={12} />}>Apply</Button>
            </span>
          </div>
        ))}
      </div>
    </Section>
  );
}

Object.assign(window, { BlogPage, AboutPage, CareersPage });
