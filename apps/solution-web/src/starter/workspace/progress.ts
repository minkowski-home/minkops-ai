type Observation = { status: string; progress: number; summary?: string; events: { event_type: string }[] };

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
  const event = task.events
    .filter((e) => !["failed", "cancelled"].includes(e.event_type) && !e.event_type.startsWith("control."))
    .at(-1)?.event_type;
  const observed: Record<string, number> = local
    ? { queued: 0, executing: 1, completed: 2 }
    : {
        queued: 0,
        received: 0,
        executing: 1,
        extracted: 1,
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
        : (localLabels[event ?? ""] ??
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
  const waiting = current === 0 || event === "local_waiting";
  const needsInput = task.status === "attention" || event === "local_failed";
  const running = !finished && !controlled && task.status !== "failed" && !needsInput;
  const states: ProgressState[] = stages.map((_, index) => index < current || finished ? "done" : index > current ? "upcoming"
    : task.status === "failed" || task.status === "stopped" ? "failed" : controlled || waiting ? "waiting" : needsInput ? "attention" : "active");
  return { stages, current, finished, states, running, label: controlled ? task.status === "paused" ? "Paused" : "Stopped" : label,
    activity: controlled ? task.status === "paused" ? "Resume to continue. An operation already underway may finish." : "Remaining work stopped. Completed saves remain." : task.summary,
    percent: finished ? 100 : null, meterLabel: finished ? "Workflow complete" : controlled ? "Run paused or stopped" : label };
}
