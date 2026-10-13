import { useEffect, useState } from "react";
import type { Task } from "../api";
import { elapsedLabel } from "../workflows/runSettings";

/** Overall wall time includes waits and pauses; it is never a completion estimate. */
export function RunTiming({ task }: { task: Task }) {
  const [now, setNow] = useState(Date.now());
  const terminal = ["completed", "failed", "stopped"].includes(task.status);
  useEffect(() => {
    if (terminal) return;
    const timer = setInterval(() => setNow(Date.now()), 10000);
    return () => clearInterval(timer);
  }, [terminal]);
  const elapsed = elapsedLabel(task.created_at, terminal ? Date.parse(task.updated_at) : now);
  const updated = Date.parse(task.updated_at);
  if (!elapsed) return null;
  return <p className="quiet-state">{terminal ? "Run duration" : "Time since started"}: {elapsed} · Includes waits and pauses.
    {Number.isFinite(updated) && <> Last update: <time dateTime={task.updated_at}>{new Date(updated).toLocaleTimeString()}</time>.</>}
  </p>;
}
