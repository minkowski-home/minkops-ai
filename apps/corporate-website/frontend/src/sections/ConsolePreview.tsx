import { Fragment, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { getAgent } from "../content/agents";
import {
  WORKFLOWS,
  type Choice,
  type Decision,
  type LogEntry,
  type PipelineStep,
  type Workflow
} from "../content/consoleWorkflows";
import { Section } from "../layout/Section";
import Wordmark from "../layout/Wordmark";
import { Icon } from "../ui/Icon";
import { TypingIndicator } from "../ui/product";
import { Badge, Button, Eyebrow, StatusDot, cx } from "../ui/primitives";

/*
 * An illustrative Minkops console, framed as an app window so it reads as
 * product rather than page. Four businesses, one shape: agents report finished
 * work in plain sentences and turn anything above their authority into one
 * question with the answers already worked out. The operator never types.
 *
 * Each workflow keeps its own state, so switching back and forth mid-morning
 * never loses a decision. Content lives in content/consoleWorkflows.ts.
 */

type LiveEntry = LogEntry & { fresh?: boolean };

type WorkflowState = {
  log: readonly LiveEntry[];
  chosen: Readonly<Record<string, Choice>>;
  done: readonly string[];
};

/** Long enough to read "Tali is working", short enough not to feel staged. */
const AGENT_WORK_MS = 1200;

function initialState(workflow: Workflow): WorkflowState {
  return { log: workflow.log, chosen: {}, done: [] };
}

function initialStates(): Record<string, WorkflowState> {
  return Object.fromEntries(
    WORKFLOWS.map((workflow) => [workflow.id, initialState(workflow)])
  );
}

function awaitingCount(workflow: Workflow, state: WorkflowState) {
  return workflow.decisions.filter((decision) => !state.chosen[decision.id]).length;
}

function AgentGlyphTile({ name, size = "sm" }: { name: string; size?: "sm" | "md" }) {
  return (
    <span className={cx("mk-app-glyph", `mk-app-glyph--${size}`)} title={name}>
      <Icon name={getAgent(name).glyph} size={size === "sm" ? 14 : 18} />
    </span>
  );
}

function Pipeline({ steps }: { steps: readonly PipelineStep[] }) {
  return (
    <ol className="mk-pipeline" aria-label="How work moves">
      {steps.map((step, index) => (
        <Fragment key={index}>
          {index > 0 ? (
            <li className="mk-pipeline__arrow" aria-hidden="true">
              <Icon name="chevronRight" size={12} />
            </li>
          ) : null}
          <li className={cx("mk-pipeline__step", `mk-pipeline__step--${step.kind}`)}>
            {step.kind === "agent" ? (
              <>
                <Icon name={getAgent(step.agent).glyph} size={14} />
                {step.agent}
              </>
            ) : (
              step.label
            )}
          </li>
        </Fragment>
      ))}
    </ol>
  );
}

function LogRow({ entry }: { entry: LiveEntry }) {
  return (
    <li className={cx("mk-log__row", entry.fresh && "is-fresh")}>
      <AgentGlyphTile name={entry.agent} size="md" />
      <div className="mk-log__body">
        <p className="mk-log__text">{entry.text}</p>
        {entry.attachments ? (
          <ul className="mk-log__files" aria-label="Attachments">
            {entry.attachments.map((file) => (
              <li key={file}>{file}</li>
            ))}
          </ul>
        ) : null}
        <p className="mk-log__meta">
          {entry.agent} · {entry.time}
        </p>
      </div>
      <Badge tone={entry.outcome.tone} className="mk-log__outcome">
        {entry.outcome.label}
      </Badge>
    </li>
  );
}

function DecisionCard({
  decision,
  chosen,
  onChoose
}: {
  decision: Decision;
  chosen: Choice | undefined;
  onChoose: (choice: Choice) => void;
}) {
  const questionId = `decision-${decision.id}`;
  return (
    <article
      className={cx("mk-decision", chosen && "is-chosen")}
      aria-labelledby={questionId}
    >
      <p className="mk-decision__meta">
        <strong>{decision.agent}</strong> · {decision.context}
      </p>
      <h4 className="mk-decision__question" id={questionId}>
        {decision.question}
      </h4>
      <p className="mk-decision__why">{decision.why}</p>

      {chosen ? (
        <div className="mk-decision__handoff">
          <p className="mk-decision__chosen">
            <Icon name="check" size={14} />
            {chosen.label}
          </p>
          <TypingIndicator name={decision.agent} />
        </div>
      ) : (
        <div className="mk-decision__choices" role="group" aria-labelledby={questionId}>
          {decision.choices.map((choice) => (
            <button
              key={choice.label}
              type="button"
              className="mk-choice"
              onClick={() => onChoose(choice)}
            >
              <span className="mk-choice__label">{choice.label}</span>
              {choice.suggested ? <Badge tone="approval">Suggested</Badge> : null}
            </button>
          ))}
        </div>
      )}
    </article>
  );
}

export default function ConsolePreview() {
  const [activeId, setActiveId] = useState(WORKFLOWS[0].id);
  const [states, setStates] = useState<Record<string, WorkflowState>>(initialStates);
  const tabRefs = useRef(new Map<string, HTMLButtonElement>());

  // One timer per decision, started on click and keyed by workflow + decision, so
  // a second choice never restarts the first and switching tabs never cancels one.
  const timers = useRef(new Map<string, number>());

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((timer) => window.clearTimeout(timer));
  }, []);

  // On narrow screens the tabs become a horizontal strip. Keep the active one in
  // view by scrolling the strip itself; scrollIntoView would also move the page.
  useEffect(() => {
    const tab = tabRefs.current.get(activeId);
    const strip = tab?.parentElement;
    if (!tab || !strip || strip.scrollWidth <= strip.clientWidth) return;
    const tabBox = tab.getBoundingClientRect();
    const stripBox = strip.getBoundingClientRect();
    if (tabBox.left < stripBox.left) strip.scrollLeft -= stripBox.left - tabBox.left;
    else if (tabBox.right > stripBox.right)
      strip.scrollLeft += tabBox.right - stripBox.right;
  }, [activeId]);

  const workflow =
    WORKFLOWS.find((candidate) => candidate.id === activeId) ?? WORKFLOWS[0];
  const state = states[workflow.id];
  const pending = workflow.decisions.filter(
    (decision) => !state.done.includes(decision.id)
  );
  const awaiting = awaitingCount(workflow, state);

  const updateWorkflow = (
    id: string,
    update: (current: WorkflowState) => WorkflowState
  ) => setStates((current) => ({ ...current, [id]: update(current[id]) }));

  // Choosing hands the work back to the agent; a moment later the finished work
  // lands at the top of the log and the entry that flagged it is marked resolved.
  const choose = (target: Workflow, decision: Decision, choice: Choice) => {
    updateWorkflow(target.id, (current) => ({
      ...current,
      chosen: { ...current.chosen, [decision.id]: choice }
    }));

    const key = `${target.id}:${decision.id}`;
    const timer = window.setTimeout(() => {
      timers.current.delete(key);
      updateWorkflow(target.id, (current) => ({
        ...current,
        done: [...current.done, decision.id],
        log: [
          {
            id: `${decision.id}-result`,
            agent: decision.agent,
            time: "09:02",
            text: choice.result,
            outcome: { label: "Done · your call", tone: "ok" },
            fresh: true
          },
          ...current.log.map((entry) =>
            entry.id === decision.flaggedEntryId
              ? { ...entry, outcome: { label: "Resolved", tone: "neutral" as const } }
              : entry
          )
        ]
      }));
    }, AGENT_WORK_MS);
    timers.current.set(key, timer);
  };

  const reset = (target: Workflow) => {
    timers.current.forEach((timer, key) => {
      if (!key.startsWith(`${target.id}:`)) return;
      window.clearTimeout(timer);
      timers.current.delete(key);
    });
    updateWorkflow(target.id, () => initialState(target));
  };

  // Roving focus across the workflow tabs: arrows move, Home/End jump.
  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = WORKFLOWS.length - 1;
    let next: number | null = null;
    if (event.key === "ArrowDown" || event.key === "ArrowRight")
      next = index === last ? 0 : index + 1;
    if (event.key === "ArrowUp" || event.key === "ArrowLeft")
      next = index === 0 ? last : index - 1;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = last;
    if (next === null) return;
    event.preventDefault();
    const target = WORKFLOWS[next];
    setActiveId(target.id);
    tabRefs.current.get(target.id)?.focus();
  };

  return (
    <Section
      eyebrow="Inside the console · an illustration"
      title="Nothing to type. Just decide."
      lead="No chat window, no empty box asking what you want. Your employees work from rules you set once and tell you what they finished. When something sits above their authority, you get one short question with the answers already worked out. Pick a business and try it."
    >
      <div className="mk-app" role="group" aria-label="Illustrative Minkops console">
        <div className="mk-app__titlebar">
          <Wordmark inverse />
          <span className="mk-app__crumb">
            console <span aria-hidden="true">/</span> {workflow.tenant}
          </span>
          <span className="mk-app__titlebar-status">
            <StatusDot
              status="active"
              label={`${workflow.agents.length} employees on shift`}
            />
          </span>
        </div>

        <div className="mk-app__body">
          <div className="mk-app__sidebar">
            <Eyebrow className="mk-app__sidebar-title">Businesses</Eyebrow>
            <div className="mk-app__tabs" role="tablist" aria-label="Businesses">
              {WORKFLOWS.map((candidate, index) => {
                const selected = candidate.id === workflow.id;
                const count = awaitingCount(candidate, states[candidate.id]);
                return (
                  <button
                    key={candidate.id}
                    ref={(node) => {
                      if (node) tabRefs.current.set(candidate.id, node);
                      else tabRefs.current.delete(candidate.id);
                    }}
                    type="button"
                    role="tab"
                    id={`wf-tab-${candidate.id}`}
                    aria-selected={selected}
                    aria-controls="wf-panel"
                    tabIndex={selected ? 0 : -1}
                    className={cx("mk-app-tab", selected && "is-selected")}
                    onClick={() => setActiveId(candidate.id)}
                    onKeyDown={(event) => onTabKeyDown(event, index)}
                  >
                    <span className="mk-app-tab__glyphs" aria-hidden="true">
                      {candidate.agents.map((name) => (
                        <AgentGlyphTile key={name} name={name} />
                      ))}
                    </span>
                    <span className="mk-app-tab__text">
                      <span className="mk-app-tab__name">{candidate.name}</span>
                      <span className="mk-app-tab__business">{candidate.business}</span>
                    </span>
                    {count > 0 ? (
                      <span className="mk-app-tab__count" aria-label={`${count} waiting`}>
                        {count}
                      </span>
                    ) : (
                      <span className="mk-app-tab__clear" aria-label="All clear">
                        <Icon name="check" size={12} />
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <div
            className="mk-app__main"
            role="tabpanel"
            id="wf-panel"
            aria-labelledby={`wf-tab-${workflow.id}`}
            key={workflow.id}
          >
            <header className="mk-app__head">
              <div className="mk-app__title">
                <h3 className="mk-app__business">{workflow.business}</h3>
                <p className="mk-app__descriptor">{workflow.descriptor}</p>
              </div>
              <Pipeline steps={workflow.pipeline} />
            </header>

            <div className="mk-app__metrics">
              {workflow.metrics.map((metric) => (
                <div key={metric.label} className="mk-app__metric">
                  <strong>{metric.value}</strong>
                  <span>{metric.label}</span>
                  {metric.bar !== undefined ? (
                    <span className="mk-app__metric-bar" aria-hidden="true">
                      <span style={{ width: `${metric.bar}%` }} />
                    </span>
                  ) : null}
                </div>
              ))}
              <div className={cx("mk-app__metric", awaiting > 0 && "is-waiting")}>
                <strong>{awaiting}</strong>
                <span>{awaiting === 1 ? "decision" : "decisions"} for you</span>
              </div>
            </div>

            <div className="mk-app__panes">
              <section className="mk-app__log" aria-label="Work finished since yesterday">
                <header className="mk-app__pane-head">
                  <Eyebrow>Done while you were away</Eyebrow>
                </header>
                <ol className="mk-log" aria-live="polite">
                  {state.log.map((entry) => (
                    <LogRow key={entry.id} entry={entry} />
                  ))}
                </ol>
              </section>

              <aside className="mk-app__attention" aria-label="Needs you">
                <header className="mk-app__pane-head">
                  <Eyebrow>Needs you ({awaiting})</Eyebrow>
                </header>

                <div className="mk-app__attention-body">
                  {pending.map((decision) => (
                    <DecisionCard
                      key={decision.id}
                      decision={decision}
                      chosen={state.chosen[decision.id]}
                      onChoose={(choice) => choose(workflow, decision, choice)}
                    />
                  ))}

                  {pending.length === 0 ? (
                    <div className="mk-app__clear mk-enter">
                      <span className="mk-app__clear-icon">
                        <Icon name="check" size={18} />
                      </span>
                      <p className="mk-app__clear-title">
                        That&apos;s everything for today.
                      </p>
                      <p className="mk-app__clear-body">{workflow.allClear}</p>
                      <Button size="sm" variant="ghost" onClick={() => reset(workflow)}>
                        Run the morning again
                      </Button>
                    </div>
                  ) : null}
                </div>
              </aside>
            </div>
          </div>
        </div>
      </div>

      <p className="mk-app__disclaimer">
        Illustrative examples. The businesses, people and figures are invented.
      </p>
    </Section>
  );
}
