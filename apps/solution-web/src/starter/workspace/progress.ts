type Observation = { status: string; progress: number; summary?: string; stage?: string; events: { event_type: string; summary?: string }[] };

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
}

/** A workflow run, a check on a PC, or any other task. Percentages are not ETAs. */
export type ProgressMode = "run" | "tally.probe" | "files.refresh" | "simple";

/** The task's stage comes from its recorded events; its summary says what is happening within it. */
export function progressView(task: Observation, mode: ProgressMode = "run"): TaskProgressView {
  const local = mode === "tally.probe" || mode === "files.refresh";
  const stages = local
    ? ["Your PC", mode === "tally.probe" ? "Check Tally" : "Read folder", "Finished"]
    : mode === "simple"
      ? ["Get ready", "Work", "Finished"]
      : ["Get ready", "Read", "Review", "Save", "Finished"];
  const event = task.stage ?? task.events
    .filter((e) => !["failed", "cancelled"].includes(e.event_type) && !e.event_type.startsWith("control."))
    .at(-1)?.event_type;
  const observed: Record<string, number> = local
    ? { queued: 0, executing: 1, completed: 2 }
    : { queued: 0, executing: 1, review: 2, writing: 3, completed: stages.length - 1 };
  const fallback: Record<string, number> = { running: 0, attention: 2, handoff: 3, failed: 0, completed: stages.length - 1 };
  const current = Math.min(stages.length - 1, task.status === "completed"
    ? stages.length - 1
    : (observed[event ?? ""] ?? fallback[task.status] ?? 0));
  const finished = task.status === "completed";
  const label = task.status === "failed"
    ? "Needs attention"
    : finished
      ? "Finished and checked"
      : task.status === "attention"
        ? "Ready for your review"
        : task.status === "handoff"
          ? "Saving and checking"
          : current === 0
            ? local ? "Waiting for your PC" : "Waiting to start"
            : local
              ? mode === "tally.probe" ? "Checking Tally" : "Reading your folder"
              : "Working on your files";
  const controlled = ["paused", "stopped"].includes(task.status);
  const stopSummary = task.events.filter(e => e.event_type === "control.stop").at(-1)?.summary;
  const needsInput = task.status === "attention";
  const running = !finished && !controlled && task.status !== "failed" && !needsInput;
  const states: ProgressState[] = stages.map((_, index) => index < current || finished ? "done" : index > current ? "upcoming"
    : task.status === "failed" || task.status === "stopped" ? "failed" : controlled || current === 0 ? "waiting"
      : needsInput ? "attention" : "active");
  return { stages, current, finished, states, running, label: controlled ? task.status === "paused" ? "Paused" : "Stopped" : label,
    activity: controlled ? task.status === "paused" ? "Resume to continue. An operation already underway may finish." : stopSummary || "Remaining work stopped. Completed saves remain." : task.summary,
    percent: finished ? 100 : null, meterLabel: finished ? "Workflow complete" : controlled ? "Run paused or stopped" : label };
}

/** Wall-clock run time from recorded timestamps; never a guess for missing or future starts. */
export function elapsedLabel(start: string, end: number): string | null {
  const beginning = Date.parse(start);
  if (!Number.isFinite(beginning) || !Number.isFinite(end) || beginning > end) return null;
  const seconds = Math.floor((end - beginning) / 1000);
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}
