const { Button, Eyebrow, OptionRow, ProgressSteps, Card, Icon, Badge } = window.MinkopsDesignSystem_6c27f0;

const QUESTIONS = [
  { id: "revenue", kicker: "Step 01 / Store stage", question: "What does your store pull in monthly?", subtext: "We use this to surface agents that match your operational scale.", type: "single",
    options: [ { value: "pre", label: "Under $2,000", meta: "Early stage" }, { value: "growth", label: "$2,000 – $15,000", meta: "Growth" }, { value: "scale", label: "$15,000 – $75,000", meta: "Scaling" }, { value: "established", label: "$75,000+", meta: "Established" } ] },
  { id: "time_sink", kicker: "Step 02 / Time audit", question: "Where does your week actually disappear?", subtext: "Select every area that pulls you away from the store itself.", type: "multi",
    options: [ { value: "support", label: "Answering customer support calls & tickets" }, { value: "leads", label: "Following up on leads and abandoned carts" }, { value: "email", label: "Writing and sending email campaigns" }, { value: "social", label: "Creating social media content" }, { value: "ads", label: "Writing ad copy and creative assets" }, { value: "analytics", label: "Pulling reports and making sense of data" } ] },
  { id: "pain", kicker: "Step 03 / Biggest bottleneck", question: "If you could eliminate one thing tomorrow, what would it be?", subtext: "This shapes which agent we recommend as your starting point.", type: "single",
    options: [ { value: "support_calls", label: "The volume of inbound support calls" }, { value: "lead_calls", label: "Chasing leads that go cold after browsing" }, { value: "email_grind", label: "The constant grind of email marketing" }, { value: "social_content", label: "Showing up consistently on social media" }, { value: "ad_copy", label: "Writing ad creative that actually converts" }, { value: "reporting", label: "Making sense of performance numbers" } ] },
  { id: "hours", kicker: "Step 04 / Weekly hours", question: "How many hours a week go into these tasks right now?", subtext: "Be honest — this is where your ROI calculation starts.", type: "single",
    options: [ { value: "2", label: "Under 2 hours", meta: "Light lift" }, { value: "8", label: "2 – 8 hours", meta: "A full day" }, { value: "15", label: "8 – 15 hours", meta: "Nearly half your week" }, { value: "20", label: "15+ hours", meta: "This is a second job" } ] }
];

const AGENT_MAP = {
  support: { name: "Kall", role: "Customer support rep", glyph: "support", desc: "Handles inbound customer calls autonomously — returns, refunds, FAQs, order status — without a single human touchpoint.", save: "8–12 hrs / wk" },
  leads: { name: "Leed", role: "Lead generation caller", glyph: "sales", desc: "Follows up on abandoned carts and browse-abandons via outbound call within minutes.", save: "4–7 hrs / wk" },
  email: { name: "Imel", role: "Email handler", glyph: "email", desc: "Writes, segments, schedules and sends full campaigns. Handles reply triage and follow-up sequences automatically.", save: "5–9 hrs / wk" },
  social: { name: "Eko", role: "Social media handler", glyph: "social", desc: "Generates branded posts, captions and scheduling queues across channels on autopilot.", save: "4–6 hrs / wk" },
  ads: { name: "Floc", role: "Content creator", glyph: "writer", desc: "Produces high-converting ad creative variants and branded content.", save: "3–5 hrs / wk" },
  analytics: { name: "Insi", role: "Business analyst", glyph: "analyst", desc: "Pulls cross-channel metrics into plain-language weekly digests. No dashboards, no spreadsheets — just answers.", save: "3–4 hrs / wk" }
};

const PRIORITY_MAP = { support_calls: "support", lead_calls: "leads", email_grind: "email", social_content: "social", ad_copy: "ads", reporting: "analytics" };
const REVENUE_LABELS = { pre: "Early stage store", growth: "Growth stage store", scale: "Scaling store", established: "Established brand" };

function Results({ answers, onAccess, onRestart }) {
  const sinks = answers.time_sink || [];
  const key = PRIORITY_MAP[answers.pain] || sinks[0] || "support";
  const hours = parseInt(answers.hours || "8", 10);
  const min = Math.round(hours * 0.45), max = Math.round(hours * 0.7);
  const pct = Math.min(100, Math.round((max / hours) * 100));
  const primary = AGENT_MAP[key];
  const secondary = sinks.filter((k) => k !== key).slice(0, 2).map((k) => AGENT_MAP[k]).filter(Boolean);

  return (
    <div style={{ display: "grid", gap: "20px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <Badge tone="ok">Analysis complete</Badge>
        <span style={{ font: "var(--type-mono)", color: "var(--text-muted)" }}>{REVENUE_LABELS[answers.revenue] || "Your store"}</span>
      </div>
      <h3 style={{ font: "var(--type-h2)", maxWidth: "24ch" }}>
        You're losing <span style={{ color: "var(--brand-rust)" }}>{hours}+ hours</span> a week to work Minkops can own.
      </h3>

      <Card tone="sunken" style={{ display: "grid", gap: "12px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
          <span style={{ font: "var(--type-eyebrow)", letterSpacing: "var(--ls-eyebrow)", textTransform: "uppercase", color: "var(--text-muted)" }}>Estimated weekly hours recovered</span>
          <strong style={{ marginLeft: "auto", font: "var(--fw-semibold) var(--fs-xl)/1 var(--font-display)", letterSpacing: "var(--ls-display)" }}>{min}–{max} hrs</strong>
        </div>
        <div style={{ height: 6, background: "var(--n-100)", borderRadius: "var(--radius-1)", overflow: "hidden" }}>
          <div style={{ width: pct + "%", height: "100%", background: "var(--brand-ember)", transition: "width var(--dur-slow) var(--ease-out)" }} />
        </div>
        <span style={{ font: "var(--type-mono)", color: "var(--text-muted)" }}>Current load {hours} hrs · up to {pct}% automated</span>
      </Card>

      <Card accentEdge style={{ display: "grid", gap: "10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={{ display: "grid", placeItems: "center", width: 34, height: 34, borderRadius: "var(--radius-2)", background: "var(--surface-inset)", color: "var(--brand-rust)" }}>
            <Icon name={primary.glyph} size={22} />
          </span>
          <span style={{ display: "grid", gap: "2px" }}>
            <span style={{ font: "var(--fw-semibold) var(--fs-lg)/1.1 var(--font-display)", letterSpacing: "var(--ls-display)" }}>{primary.name}</span>
            <span style={{ font: "var(--type-body-sm)", color: "var(--text-secondary)" }}>{primary.role}</span>
          </span>
          <span style={{ marginLeft: "auto", font: "var(--type-mono)", color: "var(--brand-rust)" }}>Saves {primary.save}</span>
        </div>
        <p style={{ margin: 0, font: "var(--type-body-sm)", color: "var(--text-secondary)", maxWidth: "var(--measure)" }}>{primary.desc}</p>
      </Card>

      {secondary.length ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(" + secondary.length + ", 1fr)", gap: "10px" }}>
          {secondary.map((a) => (
            <Card key={a.name} tone="sunken" style={{ display: "grid", gap: "6px" }}>
              <span style={{ font: "var(--fw-medium) var(--fs-md)/1.1 var(--font-display)" }}>{a.name}</span>
              <span style={{ font: "var(--type-body-sm)", color: "var(--text-secondary)" }}>{a.role}</span>
              <span style={{ font: "var(--type-mono)", color: "var(--text-muted)" }}>{a.save}</span>
            </Card>
          ))}
        </div>
      ) : null}

      <div style={{ display: "flex", alignItems: "center", gap: "12px", paddingTop: "4px" }}>
        <Button size="lg" variant="primary" onClick={onAccess}>Request access</Button>
        <Button size="lg" variant="ghost" onClick={onRestart}>Start over</Button>
        <span style={{ font: "var(--type-mono)", color: "var(--text-muted)" }}>No credit card. No setup fee.</span>
      </div>
    </div>
  );
}

function Funnel({ onAccess }) {
  const [step, setStep] = React.useState(0);
  const [answers, setAnswers] = React.useState({});
  const [selected, setSelected] = React.useState([]);
  const [done, setDone] = React.useState(false);
  const q = QUESTIONS[step];

  const pick = (v) => setSelected((s) => q.type === "multi" ? (s.includes(v) ? s.filter((x) => x !== v) : [...s, v]) : [v]);
  const advance = () => {
    const next = { ...answers, [q.id]: q.type === "multi" ? selected : selected[0] };
    setAnswers(next);
    setSelected([]);
    if (step < QUESTIONS.length - 1) setStep(step + 1); else setDone(true);
  };
  const back = () => { setSelected([]); setStep(Math.max(0, step - 1)); };
  const restart = () => { setStep(0); setAnswers({}); setSelected([]); setDone(false); };

  return (
    <Section eyebrow="Find your agent stack" title="Tell us about your store. We'll tell you what to automate."
      lead="Four honest questions, ninety seconds, a specific answer — no sales call required to get it.">
      <div style={{ maxWidth: 720, border: "1px solid var(--border-default)", borderRadius: "var(--radius-3)", padding: "28px", background: "var(--surface-page)" }}>
        {done ? <Results answers={answers} onAccess={onAccess} onRestart={restart} /> : (
          <div style={{ display: "grid", gap: "18px" }}>
            <ProgressSteps total={QUESTIONS.length} current={step} />
            <div style={{ display: "grid", gap: "8px" }}>
              <Eyebrow>{q.kicker}</Eyebrow>
              <h3 style={{ font: "var(--type-h3)", fontSize: "var(--fs-xl)" }}>{q.question}</h3>
              <p style={{ margin: 0, font: "var(--type-body-sm)", color: "var(--text-muted)" }}>
                {q.subtext}{q.type === "multi" ? " Select all that apply." : ""}
              </p>
            </div>
            <div style={{ display: "grid", gap: "8px" }} role="group" aria-label={q.question}>
              {q.options.map((o) => (
                <OptionRow key={o.value} label={o.label} meta={o.meta} multi={q.type === "multi"}
                  selected={selected.includes(o.value)} onSelect={() => pick(o.value)} />
              ))}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <Button size="lg" variant="primary" disabled={!selected.length} onClick={advance}
                iconRight={<Icon name="chevronRight" size={16} />}>
                {step === QUESTIONS.length - 1 ? "Show my results" : "Continue"}
              </Button>
              {step > 0 ? <Button variant="ghost" onClick={back} iconLeft={<Icon name="chevronLeft" size={14} />}>Back</Button> : null}
            </div>
          </div>
        )}
      </div>
    </Section>
  );
}

Object.assign(window, { Funnel });
