import { Icon } from "../console/Icon";
import type { CSSProperties } from "react";
import type { TaskProgressView } from "./progress";
import { Spinner } from "../components/Feedback";

const stateLabels = { upcoming: "Not started", done: "Done", active: "In progress", waiting: "Waiting", attention: "Needs input", failed: "Needs attention" };

export function TaskProgress({ view, stale = false }: { view: TaskProgressView; stale?: boolean }) {
  const active = view.running && !stale;
  return <section className={`task-progress workflow-progress${stale ? " is-stale" : ""}`} aria-label="Workflow progress" style={{ "--checkpoint-count": view.stages.length } as CSSProperties}>
    <div className="workflow-progress-heading">
      <span className={`workflow-progress-mark${view.finished ? " is-done" : ""}`} aria-hidden="true">
        {active ? <Spinner /> : <Icon name={view.finished ? "check" : view.states.includes("failed") ? "x" : "tasks"} size={20} />}
      </span>
      <h3>{stale ? "Updates interrupted" : view.label}</h3>
      <span className="workflow-progress-state">{stale ? "Reconnecting" : view.finished ? "Complete" : view.running ? "Auto-updating" : ""}</span>
    </div>
    <ol className="workflow-checkpoints" aria-label="Task stages">{view.stages.map((stage, index) => {
      const state = view.states[index];
      return <li key={stage} className={`is-${state}`} aria-current={!view.finished && index === view.current ? "step" : undefined}>
        <span className="checkpoint-icon" aria-hidden="true">{state === "done" ? <Icon name="check" size={15} />
          : state === "active" && active ? <Spinner /> : state === "failed" ? <Icon name="x" size={15} />
            : state === "attention" ? <Icon name="bell" size={15} /> : index + 1}</span>
        <span>{stage}<small>{stale && index === view.current ? "Last known state" : state === "failed" && view.label === "Stopped" ? "Stopped" : stateLabels[state]}</small></span>
      </li>;
    })}</ol>
    <div className="workflow-meter-label"><span>{view.meterLabel}</span><span>{view.percent != null ? `${view.percent}%` : active ? "In progress" : ""}</span></div>
    <div className={`workflow-meter${view.percent == null && active ? " is-indeterminate" : ""}`} role="progressbar"
      aria-label={view.meterLabel} aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={view.percent ?? undefined} aria-valuetext={stale ? "Updates interrupted" : view.percent == null ? view.label : `${view.percent}%`}>
      <span style={{ width: view.percent == null ? "0%" : `${view.percent}%` }} />
    </div>
    <p className="workflow-activity" title={view.activity} role="status" aria-live="polite" aria-atomic="true">
      {stale ? "Connection lost. Showing the last received results; retrying automatically." : view.activity}
    </p>
  </section>;
}
