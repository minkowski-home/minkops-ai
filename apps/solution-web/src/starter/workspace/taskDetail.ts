import type { Task, TaskEvent } from "../api";

export type TaskDetails = Task & { events: TaskEvent[] };

export function taskSnapshot(tasks: Task[], id: string): TaskDetails | null {
  const task = tasks.find((item) => item.id === id);
  return task ? { ...task, events: [] } : null;
}
