import type { CSSProperties } from "react";
import { AGENT_DIRECTORY, type AgentIllustration } from "../agentDirectory";
import "./AgentRosterCard.css";

function AgentRoleIcon({ kind }: { kind: AgentIllustration }) {
  switch (kind) {
    case "designer":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z" />
          <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
          <path d="M17 6.5L18 7.5L20.5 5" />
          <path d="M17.25 11.75L20.5 12.75L18.75 15.75L16 14.75Z" />
        </svg>
      );
    case "social":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z" />
          <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
          <path d="M17.5 8.25H20.5V11.25H18.75L17.5 12.5V8.25Z" />
          <path d="M3.5 10.25H6.5V13.25H4.75L3.5 14.5V10.25Z" />
        </svg>
      );
    case "writer":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" />
          <path d="M7.5 18.5L8.75 13L12 11.75L15.25 13L16.5 18.5" />
          <path d="M15.75 10.5L19.75 8.75" />
          <path d="M17 12.5L20.5 11.75" />
        </svg>
      );
    case "manager":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" />
          <path d="M8 18.5V14.25C8 12.73 9.23 11.5 10.75 11.5H13.25C14.77 11.5 16 12.73 16 14.25V18.5" />
          <path d="M12 11.5V16.5" />
          <path d="M10.75 13L12 14.25L13.25 13" />
        </svg>
      );
    case "host":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" />
          <path d="M12 11.5V18.5" />
          <path d="M12 12L6 14.75" />
          <path d="M12 12L18 14.75" />
          <path d="M9.5 18.5H14.5" />
        </svg>
      );
    case "kitchen":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M8.5 8.25C8.5 6.18 10.18 4.5 12.25 4.5C14.32 4.5 16 6.18 16 8.25V9.5H8.5V8.25Z" />
          <path d="M9.25 6.75A2.75 2.75 0 1 0 14.75 6.75A2.75 2.75 0 0 0 9.25 6.75Z" />
          <path d="M8.25 18.5V13.5C8.25 11.84 9.59 10.5 11.25 10.5H12.75C14.41 10.5 15.75 11.84 15.75 13.5V18.5" />
        </svg>
      );
    case "support":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z" />
          <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
          <path d="M7 10.5A5 5 0 0 1 17 10.5" />
          <path d="M6.5 11.5V14" />
          <path d="M17.5 11.5V14" />
          <path d="M17.5 14C17.5 15.66 16.16 17 14.5 17H13.75" />
        </svg>
      );
    case "sales":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z" />
          <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
          <path d="M17.5 8.5L20 11L17.5 13.5" />
          <path d="M20 11H15.75" />
        </svg>
      );
    case "retail":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" />
          <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
          <path d="M17.25 9.25H20.5V15.5H17.25Z" />
          <path d="M18.75 11H19" />
        </svg>
      );
    case "analyst":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" />
          <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
          <path d="M17.25 15.5V11.5" />
          <path d="M19 15.5V9.5" />
          <path d="M20.75 15.5V13" />
        </svg>
      );
    case "email":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z" />
          <path d="M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5" />
          <path d="M17.25 10H20.5V14H17.25Z" />
          <path d="M17.25 10L18.88 11.5L20.5 10" />
        </svg>
      );
  }
}

export default function AgentRosterCard() {
  return (
    <aside className="access-agent-card glass-panel-vibrant soft-enter">
      <div className="access-agent-card-header">
        <h2 className="access-agent-title">Know your future employees</h2>
      </div>

      <div className="access-agent-list">
        {AGENT_DIRECTORY.map((agent) => (
          <article
            key={agent.name}
            className="access-agent-item glass-panel"
            style={{ "--agent-color": agent.color } as CSSProperties}
          >
            <div className="access-agent-heading">
              <span className="access-agent-icon" aria-hidden="true">
                <AgentRoleIcon kind={agent.illustration} />
              </span>
              <strong>{agent.name}</strong>
            </div>

            <div className="access-agent-roleline">
              <span>{agent.tool}</span>
              <span>{agent.persona}</span>
            </div>
          </article>
        ))}
      </div>
    </aside>
  );
}
