import "./AgentRosterCard.css";

type AgentKind = "research" | "inbox" | "reporting" | "scheduling";

const AGENTS: Array<{
  name: string;
  role: string;
  description: string;
  kind: AgentKind;
}> = [
  {
    name: "Scout",
    role: "Lead Research",
    description: "Researches leads, summarises web content, and populates CRM fields.",
    kind: "research"
  },
  {
    name: "Imel",
    role: "Inbox Triage",
    description: "Handles inbound email triage, drafts responses, and routes tickets.",
    kind: "inbox"
  },
  {
    name: "Synapse",
    role: "Structured Reporting",
    description: "Aggregates data from multiple sources and produces structured reports.",
    kind: "reporting"
  },
  {
    name: "Aria",
    role: "Calendar Ops",
    description: "Manages scheduling, sends invites, and handles rescheduling.",
    kind: "scheduling"
  }
];

function AgentRoleIcon({ kind }: { kind: AgentKind }) {
  switch (kind) {
    case "research":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="11" cy="11" r="5.5" />
          <path d="M15.5 15.5L20 20" />
          <path d="M11 8.5V13.5" />
          <path d="M8.5 11H13.5" />
        </svg>
      );
    case "inbox":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 7.5L12 13.5L20 7.5" />
          <rect x="3.5" y="5.5" width="17" height="13" rx="3" />
          <path d="M7.5 15.5H16.5" />
        </svg>
      );
    case "reporting":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M6 18.5V10.5" />
          <path d="M12 18.5V6.5" />
          <path d="M18 18.5V13.5" />
          <path d="M4.5 18.5H19.5" />
        </svg>
      );
    case "scheduling":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <rect x="4" y="5.5" width="16" height="14" rx="3" />
          <path d="M8 3.5V7.5" />
          <path d="M16 3.5V7.5" />
          <path d="M4 10H20" />
          <path d="M9 14H12.5" />
        </svg>
      );
  }
}

export default function AgentRosterCard() {
  return (
    <aside className="access-agent-card glass-panel-vibrant soft-enter">
      <div className="access-agent-card-header">
        <p className="access-agent-kicker">Known agents</p>
        <h2 className="access-agent-title">Start with specialists that already know the work.</h2>
        <p className="access-agent-copy">
          A first fleet can begin with proven roles across research, inbox handling,
          reporting, and scheduling.
        </p>
      </div>

      <div className="access-agent-list">
        {AGENTS.map((agent) => (
          <article key={agent.name} className="access-agent-item glass-panel">
            <div className="access-agent-icon" aria-hidden="true">
              <AgentRoleIcon kind={agent.kind} />
            </div>

            <div className="access-agent-body">
              <div className="access-agent-meta">
                <strong>{agent.name}</strong>
                <span>{agent.role}</span>
              </div>
              <p>{agent.description}</p>
            </div>
          </article>
        ))}
      </div>
    </aside>
  );
}
