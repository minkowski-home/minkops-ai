export interface NamedEmployee {
  id: string;
  name: string;
}

export interface GroupableWorkflow {
  id: string;
  name: string;
  status: string;
  employee_ids: string[];
}

export type WorkflowGroup = "none" | "employee" | "status";
export type WorkflowSort = "name" | "status";

const greetings = [
  (name: string) => `Let's start the day, ${name}.`,
  (name: string) => `What can I take off your plate today, ${name}?`,
  (name: string) => `Good to see you, ${name}.`,
  (name: string) => `Ready when you are, ${name}.`,
];

export function greetingFor(fullName: string, dateKey: string): string {
  const firstName = fullName.trim().split(/\s+/)[0] || "there";
  const seed = `${fullName}:${dateKey}`;
  const hash = [...seed].reduce((value, character) => value * 31 + character.charCodeAt(0), 0);
  return greetings[Math.abs(hash) % greetings.length](firstName);
}

export function sortWorkflows<T extends GroupableWorkflow>(items: T[], by: WorkflowSort): T[] {
  const rank: Record<string, number> = { active: 0, paused: 1, planned: 2 };
  return [...items].sort((a, b) => by === "status"
    ? (rank[a.status] ?? 9) - (rank[b.status] ?? 9) || a.name.localeCompare(b.name)
    : a.name.localeCompare(b.name));
}

export function groupWorkflows<T extends GroupableWorkflow>(
  items: T[], employees: NamedEmployee[], by: WorkflowGroup,
): { label: string; items: T[] }[] {
  if (by === "none") return [{ label: "All workflows", items: sortWorkflows(items, "name") }];
  if (by === "status") {
    return ["active", "paused", "planned"].map((status) => ({
      label: status[0].toUpperCase() + status.slice(1),
      items: sortWorkflows(items.filter((item) => item.status === status), "name"),
    })).filter((group) => group.items.length);
  }
  const groups = [...employees].sort((a, b) => a.name.localeCompare(b.name)).map((employee) => ({
    label: employee.name,
    items: sortWorkflows(items.filter((item) => item.employee_ids.includes(employee.id)), "name"),
  })).filter((group) => group.items.length);
  const unassigned = sortWorkflows(items.filter((item) => !item.employee_ids.length), "name");
  if (unassigned.length) groups.push({ label: "Unassigned", items: unassigned });
  return groups;
}
