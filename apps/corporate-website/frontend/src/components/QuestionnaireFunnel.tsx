import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import "./QuestionnaireFunnel.css";

type QuestionType = "single" | "multi";

interface Option {
  value: string;
  label: string;
  sub?: string;
  tag?: string;
}

interface Question {
  id: string;
  kicker: string;
  question: string;
  subtext: string;
  type: QuestionType;
  options: Option[];
}

interface AgentResult {
  name: string;
  role: string;
  desc: string;
  save: string;
}

type Answers = Record<string, string | string[]>;

// ---------------------------------------------------------------------------
// Questionnaire data — scoped to e-commerce operators (Minkops' core market)
// ---------------------------------------------------------------------------
const QUESTIONS: Question[] = [
  {
    id: "revenue",
    kicker: "Step 01 / Store Stage",
    question: "What does your store pull in monthly?",
    subtext:
      "We use this to surface agents that match your operational scale.",
    type: "single",
    options: [
      { value: "pre",         label: "Under $2,000",        tag: "Early Stage"  },
      { value: "growth",      label: "$2,000 – $15,000",    tag: "Growth"       },
      { value: "scale",       label: "$15,000 – $75,000",   tag: "Scaling"      },
      { value: "established", label: "$75,000+",            tag: "Established"  },
    ],
  },
  {
    id: "time_sink",
    kicker: "Step 02 / Time Audit",
    question: "Where does your week actually disappear?",
    subtext: "Select every area that pulls you away from the store itself.",
    type: "multi",
    options: [
      { value: "support",   label: "Answering customer support calls & tickets" },
      { value: "leads",     label: "Following up on leads and abandoned carts"  },
      { value: "email",     label: "Writing and sending email campaigns"        },
      { value: "social",    label: "Creating social media content"              },
      { value: "ads",       label: "Writing ad copy and creative assets"        },
      { value: "analytics", label: "Pulling reports and making sense of data"   },
    ],
  },
  {
    id: "pain",
    kicker: "Step 03 / Biggest Bottleneck",
    question: "If you could eliminate one thing tomorrow, what would it be?",
    subtext:
      "This shapes which agent we recommend as your starting point.",
    type: "single",
    options: [
      { value: "support_calls",  label: "The volume of inbound support calls"        },
      { value: "lead_calls",     label: "Chasing leads that go cold after browsing"  },
      { value: "email_grind",    label: "The constant grind of email marketing"       },
      { value: "social_content", label: "Showing up consistently on social media"     },
      { value: "ad_copy",        label: "Writing ad creative that actually converts"  },
      { value: "reporting",      label: "Making sense of performance numbers"         },
    ],
  },
  {
    id: "hours",
    kicker: "Step 04 / Weekly Hours",
    question: "How many hours a week go into these tasks right now?",
    subtext: "Be honest — this is where your ROI calculation starts.",
    type: "single",
    options: [
      { value: "2",  label: "Under 2 hours",  sub: "Light lift"           },
      { value: "8",  label: "2 – 8 hours",    sub: "A full day"           },
      { value: "15", label: "8 – 15 hours",   sub: "Nearly half your week" },
      { value: "20", label: "15+ hours",       sub: "This is a second job"  },
    ],
  },
];

// Maps time-sink keys to Minkops agent names from the agent directory
const AGENT_MAP: Record<string, AgentResult> = {
  support: {
    name: "Kall",
    role: "Customer Support Rep",
    desc: "Handles inbound customer calls autonomously — returns, refunds, FAQs, order status — without a single human touchpoint.",
    save: "8–12 hrs / wk",
  },
  leads: {
    name: "Leed",
    role: "Lead Generation Caller",
    desc: "Follows up on abandoned carts and browse-abandons via outbound call within minutes. Closes the gap between intent and purchase.",
    save: "4–7 hrs / wk",
  },
  email: {
    name: "Imel",
    role: "Email Handler",
    desc: "Writes, segments, schedules, and sends full campaigns. Handles reply triage and follow-up sequences automatically.",
    save: "5–9 hrs / wk",
  },
  social: {
    name: "Eko",
    role: "Social Media Handler",
    desc: "Generates branded posts, captions, and scheduling queues across Instagram, TikTok, and Facebook on autopilot.",
    save: "4–6 hrs / wk",
  },
  ads: {
    name: "Floc",
    role: "Content Creator",
    desc: "Produces high-converting ad creative variants and branded content so your budget goes further and your store stays loud.",
    save: "3–5 hrs / wk",
  },
  analytics: {
    name: "Insi",
    role: "Business Analyst",
    desc: "Pulls cross-channel metrics into plain-language weekly digests. No dashboards, no spreadsheets — just answers.",
    save: "3–4 hrs / wk",
  },
};

// Maps the "biggest pain" answer back to the corresponding agent key
const PRIORITY_MAP: Record<string, string> = {
  support_calls:  "support",
  lead_calls:     "leads",
  email_grind:    "email",
  social_content: "social",
  ad_copy:        "ads",
  reporting:      "analytics",
};

const REVENUE_LABELS: Record<string, string> = {
  pre:         "Early Stage Store",
  growth:      "Growth Stage Store",
  scale:       "Scaling Store",
  established: "Established Brand",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ProgressBar({ current, total }: { current: number; total: number }) {
  return (
    <div className="funnel-progress" role="progressbar" aria-valuenow={current + 1} aria-valuemax={total}>
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          className={`funnel-progress-seg${i <= current ? " funnel-progress-seg--active" : ""}`}
        />
      ))}
    </div>
  );
}

function ResultsScreen({ answers }: { answers: Answers }) {
  const timeSinks  = (answers.time_sink as string[]) || [];
  const priorityKey = PRIORITY_MAP[answers.pain as string] || timeSinks[0] || "support";
  const hours      = parseInt((answers.hours as string) || "8", 10);
  const savedMin   = Math.round(hours * 0.45);
  const savedMax   = Math.round(hours * 0.7);
  const autoPct    = Math.min(100, Math.round((savedMax / hours) * 100));

  const primaryAgent    = AGENT_MAP[priorityKey];
  const secondaryAgents = timeSinks
    .filter((k) => k !== priorityKey)
    .slice(0, 2)
    .map((k) => AGENT_MAP[k])
    .filter(Boolean) as AgentResult[];

  return (
    <motion.div
      className="funnel-results"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      {/* Status badge */}
      <div className="funnel-results-badge glass-pill">
        <span className="funnel-badge-pulse" aria-hidden="true" />
        Analysis Complete — {REVENUE_LABELS[answers.revenue as string] ?? "Your Store"}
      </div>

      <h2 className="funnel-results-heading">
        You're losing{" "}
        <span className="text-accent">{hours}+ hours</span> a week
        <br />
        to work Minkops can own.
      </h2>

      <p className="funnel-results-subtext">
        Based on your answers, here's the agent stack we'd deploy first — and a
        conservative estimate of what you get back.
      </p>

      {/* Time recovery bar */}
      <div className="funnel-recovery glass-panel">
        <div className="funnel-recovery-stat">
          <p className="funnel-recovery-stat-label">Estimated weekly hours recovered</p>
          <strong className="funnel-recovery-value">{savedMin}–{savedMax} hrs</strong>
        </div>

        <div className="funnel-recovery-track-wrap">
          <div className="funnel-recovery-track-header">
            <span>Current load</span>
            <span>{hours} hrs</span>
          </div>
          <div className="funnel-recovery-track">
            <motion.div
              className="funnel-recovery-fill"
              initial={{ width: 0 }}
              animate={{ width: `${autoPct}%` }}
              transition={{ duration: 1, delay: 0.3, ease: "easeOut" }}
            />
          </div>
          <p className="funnel-recovery-track-footer">Up to {autoPct}% automated</p>
        </div>
      </div>

      {/* Primary agent recommendation */}
      {primaryAgent && (
        <div className="funnel-agent-primary glass-panel-strong">
          <span className="funnel-agent-badge">Primary Agent</span>
          <div className="funnel-agent-body">
            <strong className="funnel-agent-name">{primaryAgent.name}</strong>
            <div>
              <p className="funnel-agent-role">{primaryAgent.role}</p>
              <p className="funnel-agent-desc">{primaryAgent.desc}</p>
              <p className="funnel-agent-save">↗ Saves {primaryAgent.save}</p>
            </div>
          </div>
        </div>
      )}

      {/* Supporting agent recommendations */}
      {secondaryAgents.length > 0 && (
        <div className="funnel-agents-secondary">
          {secondaryAgents.map((agent, i) => (
            <div key={i} className="funnel-agent-secondary glass-panel">
              <strong className="funnel-agent-name">{agent.name}</strong>
              <p className="funnel-agent-role">{agent.role}</p>
              <p className="funnel-agent-desc">{agent.desc}</p>
              <p className="funnel-agent-save">↗ {agent.save}</p>
            </div>
          ))}
        </div>
      )}

      {/* CTA */}
      <div className="funnel-cta-row glass-panel">
        <div>
          <p className="funnel-cta-heading">Get early access to Minkops</p>
          <p className="funnel-cta-sub">
            No credit card. No setup fee. Your agents live in 24 hours.
          </p>
        </div>
        <a href="#access" className="cta-button large-cta">
          Request Access →
        </a>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function QuestionnaireFunnel() {
  const [step,     setStep]     = useState(0);
  const [answers,  setAnswers]  = useState<Answers>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [complete, setComplete] = useState(false);

  const q = QUESTIONS[step];

  // Restore any prior selection when navigating between steps
  useEffect(() => {
    if (!q) return;
    const prev = answers[q.id];
    if (q.type === "multi") {
      setSelected(Array.isArray(prev) ? prev : []);
    } else {
      setSelected(prev && typeof prev === "string" ? [prev] : []);
    }
  }, [step]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (value: string) => {
    if (q.type === "multi") {
      setSelected((s) =>
        s.includes(value) ? s.filter((v) => v !== value) : [...s, value]
      );
    } else {
      setSelected([value]);
    }
  };

  const advance = () => {
    const val     = q.type === "multi" ? selected : selected[0];
    const updated = { ...answers, [q.id]: val };
    setAnswers(updated);
    if (step < QUESTIONS.length - 1) {
      setStep((s) => s + 1);
    } else {
      setComplete(true);
    }
  };

  const canContinue = selected.length > 0;
  const isLastStep  = step === QUESTIONS.length - 1;

  return (
    <motion.section
      className="funnel-section"
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.8 }}
    >
      {/* Section header — sits above the card */}
      <div className="funnel-section-header">
        <span className="section-kicker">Find your agent stack</span>
        <h2 className="funnel-section-title">
          Tell us about your store.{" "}
          <span className="text-accent">We'll tell you what to automate.</span>
        </h2>
      </div>

      {/* Questionnaire card */}
      <div className="funnel-shell glass-panel-vibrant">
        {!complete ? (
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              className="funnel-step"
              initial={{ opacity: 0, x: 18 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -18 }}
              transition={{ duration: 0.28, ease: "easeInOut" }}
            >
              <ProgressBar current={step} total={QUESTIONS.length} />

              <p className="funnel-kicker">{q.kicker}</p>

              <h3 className="funnel-question">{q.question}</h3>

              <p className="funnel-subtext">
                {q.subtext}
                {q.type === "multi" && (
                  <span className="funnel-multi-hint"> Select all that apply.</span>
                )}
              </p>

              <div className="funnel-options" role="group" aria-label={q.question}>
                {q.options.map((opt) => {
                  const isSelected = selected.includes(opt.value);
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      role={q.type === "multi" ? "checkbox" : "radio"}
                      aria-checked={isSelected}
                      className={`funnel-option${isSelected ? " funnel-option--selected" : ""}`}
                      onClick={() => toggle(opt.value)}
                    >
                      <span
                        className={[
                          "funnel-option-indicator",
                          q.type === "multi" ? "funnel-option-indicator--square" : "",
                          isSelected           ? "funnel-option-indicator--checked" : "",
                        ].join(" ")}
                        aria-hidden="true"
                      >
                        {isSelected && "✓"}
                      </span>
                      <span className="funnel-option-content">
                        <span className="funnel-option-label">{opt.label}</span>
                        {(opt.sub ?? opt.tag) && (
                          <span className="funnel-option-meta">{opt.sub ?? opt.tag}</span>
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>

              <div className="funnel-actions">
                <button
                  type="button"
                  className="cta-button large-cta"
                  onClick={advance}
                  disabled={!canContinue}
                >
                  {isLastStep ? "Show My Results →" : "Continue →"}
                </button>
                {step > 0 && (
                  <button
                    type="button"
                    className="funnel-back-btn"
                    onClick={() => setStep((s) => s - 1)}
                  >
                    ← Back
                  </button>
                )}
              </div>
            </motion.div>
          </AnimatePresence>
        ) : (
          <ResultsScreen answers={answers} />
        )}
      </div>
    </motion.section>
  );
}
