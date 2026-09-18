import type { ReactNode } from "react";
import { Icon, type AgentGlyph } from "./Icon";
import { cx } from "./primitives";

/* Product components from design/components/product and /feedback. */

/**
 * One employee in the roster: role glyph, name, role, team, what they're doing
 * right now, and an optional action (e.g. "Add to team"). `selected` marks an
 * employee already on the visitor's team.
 */
export function AgentTile({
  name,
  role,
  department,
  glyph,
  now,
  selected = false,
  action
}: {
  name: string;
  role: string;
  department: string;
  glyph: AgentGlyph;
  now: string;
  selected?: boolean;
  action?: ReactNode;
}) {
  return (
    <article className={cx("mk-agent-tile", selected && "is-selected")}>
      <div className="mk-agent-tile__top">
        <span className="mk-glyph-tile">
          <Icon name={glyph} size={22} />
        </span>
        <span className="mk-agent-tile__department">{department}</span>
      </div>
      <div className="mk-agent-tile__id">
        <h3 className="mk-agent-tile__name">{name}</h3>
        <p className="mk-agent-tile__role">{role}</p>
      </div>
      <p className="mk-agent-tile__now">
        <span className="mk-agent-tile__now-dot" aria-hidden="true" />
        <span className="mk-visually-hidden">Right now: </span>
        {now}
      </p>
      {action ? <div className="mk-agent-tile__action">{action}</div> : null}
    </article>
  );
}

/**
 * A step in an agent handoff diagram. Agents carry a 2px Ember top edge;
 * the terminal output is a graphite block.
 */
export function FlowNode({
  agent,
  role,
  output
}:
  | { agent: string; role: string; output?: never }
  | { output: string; agent?: never; role?: never }) {
  if (output) {
    return (
      <div className="mk-flow-node mk-flow-node--output">
        <span className="mk-flow-node__output">{output}</span>
      </div>
    );
  }
  return (
    <div className="mk-flow-node">
      <span className="mk-flow-node__agent">{agent}</span>
      <span className="mk-flow-node__role">{role}</span>
    </div>
  );
}

export function FlowArrow({ label }: { label: string }) {
  return (
    <div className="mk-flow-arrow">
      <span className="mk-flow-arrow__label">{label}</span>
      <svg
        className="mk-flow-arrow__line"
        width="72"
        height="8"
        viewBox="0 0 72 8"
        fill="none"
        aria-hidden="true"
      >
        <path d="M0 4H66" stroke="currentColor" strokeWidth="1.5" />
        <path
          d="M63 1L67 4L63 7"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

/** Three Ember dots pulsing in opacity: the one looping motion the system allows. */
export function TypingIndicator({ name }: { name: string }) {
  return (
    <div className="mk-typing" role="status">
      <span className="mk-typing__dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span className="mk-typing__label">{name} is working</span>
    </div>
  );
}
