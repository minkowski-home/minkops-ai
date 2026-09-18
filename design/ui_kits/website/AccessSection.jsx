const { Button, Field, Input, Select, Textarea, Card, Eyebrow, Badge } = window.MinkopsDesignSystem_6c27f0;

function InterestForm() {
  const [sent, setSent] = React.useState(false);
  return (
    <Card style={{ display: "grid", gap: "16px", alignContent: "start" }}>
      <div style={{ display: "grid", gap: "6px" }}>
        <h3 style={{ font: "var(--type-h3)" }}>Request access</h3>
        <p style={{ margin: 0, font: "var(--type-body-sm)", color: "var(--text-secondary)" }}>Join the waiting list for our autonomous workforce.</p>
      </div>
      {sent ? (
        <div style={{ display: "grid", gap: "8px", padding: "20px 0" }}>
          <Badge tone="ok">Received</Badge>
          <p style={{ margin: 0, font: "var(--type-body)" }}>Thanks — we'll be in touch. We read every one of these ourselves.</p>
        </div>
      ) : (
        <form style={{ display: "grid", gap: "12px" }} onSubmit={(e) => { e.preventDefault(); setSent(true); }}>
          <Field label="Full name" htmlFor="if-name" required><Input id="if-name" placeholder="Sarah Connor" /></Field>
          <Field label="Work email" htmlFor="if-email" required><Input id="if-email" type="email" placeholder="sarah@company.com" /></Field>
          <Field label="Company" htmlFor="if-co"><Input id="if-co" placeholder="Cyberdyne Systems" /></Field>
          <Field label="Primary interest" htmlFor="if-int">
            <Select id="if-int" options={[
              { value: "general", label: "General enquiry" },
              { value: "sales", label: "Sales & lead gen" },
              { value: "support", label: "Customer support" },
              { value: "marketing", label: "Marketing & content" },
              { value: "operations", label: "Operations & HR" },
              { value: "enterprise", label: "Enterprise custom solutions" }
            ]} />
          </Field>
          <Field label="Message" htmlFor="if-msg" hint="Optional."><Textarea id="if-msg" rows={3} placeholder="Tell us about your needs…" /></Field>
          <Button type="submit" variant="primary" size="lg" fullWidth>Join waitlist</Button>
        </form>
      )}
    </Card>
  );
}

function AccessSection() {
  return (
    <Section eyebrow="Get access" title="Hire your first agent" tone="sunken"
      lead="Minkops is pre-sale. Early tenants get their fleet provisioned by hand, by us.">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 420px", gap: "24px", alignItems: "start" }}>
        <div style={{ display: "grid", gap: "16px" }}>
          {[
            ["Built before it's sold", "We run our own company on these agents first. Imel reads our inbox and drafts replies before a human opens it."],
            ["One agent, one role", "Each agent takes a whole job with disjoint skills — not a workflow step. They talk to each other and share one knowledge graph."],
            ["Humans stay in the loop", "Anything above an agent's authority threshold lands in your queue with a drafted answer. You approve, modify, or escalate."],
            ["Runs continuously", "A fleet runs 24×7, not as one-off jobs. Every human correction becomes training signal."]
          ].map(([h, b]) => (
            <div key={h} style={{ display: "grid", gap: "5px", paddingLeft: "14px", borderLeft: "2px solid var(--brand-ember)" }}>
              <span style={{ font: "var(--type-h4)" }}>{h}</span>
              <p style={{ margin: 0, maxWidth: "var(--measure)", font: "var(--type-body)", color: "var(--text-secondary)" }}>{b}</p>
            </div>
          ))}
        </div>
        <InterestForm />
      </div>
    </Section>
  );
}

Object.assign(window, { AccessSection, InterestForm });
