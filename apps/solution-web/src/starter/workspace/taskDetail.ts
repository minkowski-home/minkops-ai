import type { Task, TaskEvent } from "../api";

/** A run's task names its run and client, whose review it shows. */
export type TaskDetails = Task & { events: TaskEvent[]; run?: { id: string; client: string } };

export function taskSnapshot(tasks: Task[], id: string): TaskDetails | null {
  const task = tasks.find((item) => item.id === id);
  return task ? { ...task, events: [] } : null;
}
