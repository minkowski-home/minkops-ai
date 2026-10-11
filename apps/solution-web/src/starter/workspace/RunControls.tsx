import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../contexts/AuthContext";
import { Spinner } from "../components/Feedback";
import type { TaskDetails } from "./taskDetail";

/** Controls express durable intent; completed destination changes are retained. */
export function RunControls({ tenant, task, onChanged }: {
  tenant: string; task: TaskDetails; onChanged: (task: TaskDetails) => void;
}) {
  const { user } = useAuth();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  if (!task.can_control || ["completed", "failed", "stopped"].includes(task.status)) return null;
  async function act(action: "pause" | "resume" | "stop") {
    if (!user || busy) return;
    setBusy(action); setError("");
    try {
      onChanged(await api<TaskDetails>(`/api/tenants/${tenant}/tasks/${task.id}/control`, {
        method: "POST", body: JSON.stringify({ action })
      }, user.csrf_token));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not change this run."); }
    finally { setBusy(null); }
  }
  return <div className="run-controls">
    <div className="accounts-toolbar">
      <button className="button button-ghost" disabled={Boolean(busy)} onClick={() => void act(task.status === "paused" ? "resume" : "pause")}>
        {busy && busy !== "stop" && <Spinner />}{task.status === "paused" ? "Resume" : "Pause"}
      </button>
      <button className="button button-ghost" disabled={Boolean(busy)} onClick={() => void act("stop")}>{busy === "stop" && <Spinner />}Stop</button>
      <small>An operation already underway may finish. Completed saves remain.</small>
    </div>
    {error && <p className="form-message" role="alert">{error}</p>}
  </div>;
}
