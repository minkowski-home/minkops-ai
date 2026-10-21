type Observation = { status: string; progress: number; summary?: string; stage?: string; execution?: import("../api").RunExecution; events: { event_type: string; summary?: string }[] };

export type ProgressState = "upcoming" | "done" | "active" | "waiting" | "attention" | "failed";
export interface TaskProgressView {
  stages: string[];
  states: ProgressState[];
  current: number;
  finished: boolean;
  running: boolean;
  label: string;
  activity?: string;
  percent: number | null;
  meterLabel: string;
  countLabel?: string;
}

/** Execution observations define the current stage. Percentages are not ETAs. */
export type ProgressMode =
  | "bill-entry"
  | "source-discovery"
  | "tally.probe"
  | "files.refresh"
  | "proposal"
  | "simple";
export function progressView(task: Observation, mode: ProgressMode = "bill-entry"): TaskProgressView {
  const local = ["tally.probe", "files.refresh"].includes(mode);
  const stages = local
    ? ["Your PC", mode === "tally.probe" ? "Check Tally" : "Read folder", "Finished"]
    : mode === "source-discovery" || mode === "proposal"
      ? ["Get ready", "Work", "Review", "Finished"]
      : mode === "simple"
        ? ["Get ready", "Work", "Finished"]
        : ["Get ready", "Read bills", "Review", "Save", "Finished"];
  const event = task.execution?.stage ?? task.stage ?? task.events
    .filter((e) => !["failed", "cancelled"].includes(e.event_type) && !e.event_type.startsWith("control."))
    .at(-1)?.event_type;
  const observed: Record<string, number> = local
    ? { queued: 0, executing: 1, completed: 2 }
    : {
        queued: 0,
        received: 0,
        executing: 1,
        extracted: 1,
        routing: 1,
        learning_pattern: 1,
        awaiting_input: 1,
        reading: 1,
        recovering: 1,
        review: 2,
        approved: 2,
        writing: 3,
        local_waiting: 3,
        local_saving: 3,
        local_verified: 3,
        local_failed: 3,
        completed: stages.length - 1
      };
  const fallback: Record<string, number> = {
    running: 0,
    attention: 2,
    handoff: 3,
    failed: 0,
    completed: stages.length - 1
  };
  const current = Math.min(
    stages.length - 1,
    task.status === "completed"
      ? stages.length - 1
      : (observed[event ?? ""] ?? fallback[task.status] ?? 0)
  );
  const finished = task.status === "completed";
  const localLabels: Record<string, string> = {
    local_waiting: "Waiting for your PC",
    local_saving: "Saving and checking",
    local_verified: "Saving and checking",
    local_failed: "Needs attention"
  };
  const label =
    task.status === "failed"
      ? "Needs attention"
      : finished
        ? "Finished and checked"
        : (event === "awaiting_input" ? "Waiting for your confirmation" : event === "routing" ? "Choosing companies"
          : event === "learning_pattern" ? "Learning the posting pattern" : event === "recovering" ? "Recovering processing"
          : localLabels[event ?? ""] ??
          (task.status === "attention"
            ? "Ready for your review"
            : task.status === "handoff"
              ? "Ready to save"
              : current === 0
                ? local
                  ? "Waiting for your PC"
                  : "Waiting to start"
                : local
                  ? mode === "tally.probe"
                    ? "Checking Tally"
                    : "Reading your folder"
                  : event === "writing"
                    ? "Saving and checking"
                    : "Working on your files"));
  const controlled = ["paused", "stopped"].includes(task.status);
  const stopSummary = task.events.filter(e => e.event_type === "control.stop").at(-1)?.summary;
  const waiting = current === 0 || event === "local_waiting";
  const needsInput = task.status === "attention" || event === "local_failed" || event === "awaiting_input";
  const running = !finished && !controlled && task.status !== "failed" && !needsInput && event !== "recovering";
  const states: ProgressState[] = stages.map((_, index) => index < current || finished ? "done" : index > current ? "upcoming"
    : task.status === "failed" || task.status === "stopped" ? "failed" : controlled || waiting ? "waiting" : needsInput ? "attention" : "active");
  return { stages, current, finished, states, running, label: controlled ? task.status === "paused" ? "Paused" : "Stopped" : label,
    activity: controlled ? task.status === "paused" ? "Resume to continue. An operation already underway may finish." : stopSummary || "Remaining work stopped. Completed saves remain." : task.summary,
    percent: finished ? 100 : null, meterLabel: finished ? "Workflow complete" : controlled ? "Run paused or stopped" : label,
    countLabel: task.execution?.total ? `${task.execution.ready ?? 0} of ${task.execution.total} read` : undefined };
}

/** Wall-clock run time from recorded timestamps; never a guess for missing or future starts. */
export function elapsedLabel(start: string, end: number): string | null {
  const beginning = Date.parse(start);
  if (!Number.isFinite(beginning) || !Number.isFinite(end) || beginning > end) return null;
  const seconds = Math.floor((end - beginning) / 1000);
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}
