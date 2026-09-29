import assert from "node:assert/strict";
import test from "node:test";
import { groupWorkflows, greetingFor, sortWorkflows } from "../src/starter/workspace/presentation.ts";
import { taskSnapshot } from "../src/starter/workspace/taskDetail.ts";

const employees = [
  { id: "e1", name: "Image desk" },
  { id: "e2", name: "Accounts desk" },
];
const workflows = [
  { id: "w2", name: "Vendor intake", status: "planned", employee_ids: ["e1", "e2"] },
  { id: "w1", name: "Image to Excel", status: "active", employee_ids: ["e1"] },
  { id: "w3", name: "Reconciliation", status: "paused", employee_ids: ["e2"] },
];

test("welcome includes the signed-in user's name and is stable for the day", () => {
  const first = greetingFor("Casey Morgan", "2026-09-29");
  assert.match(first, /Casey/);
  assert.equal(first, greetingFor("Casey Morgan", "2026-09-29"));
});

test("workflows sort by name and group by every associated employee", () => {
  assert.deepEqual(sortWorkflows(workflows, "name").map((item) => item.id), ["w1", "w3", "w2"]);
  const groups = groupWorkflows(workflows, employees, "employee");
  assert.deepEqual(groups.map((group) => group.label), ["Accounts desk", "Image desk"]);
  assert.deepEqual(groups[0].items.map((item) => item.id), ["w3", "w2"]);
  assert.deepEqual(groups[1].items.map((item) => item.id), ["w1", "w2"]);
});

test("workflows group by lifecycle status", () => {
  const groups = groupWorkflows(workflows, employees, "status");
  assert.deepEqual(groups.map((group) => group.label), ["Active", "Paused", "Planned"]);
});

test("task detail can render from the dashboard snapshot while events load", () => {
  const tasks = [{
    id: "t1", workflow_id: "w1", title: "Check receipt", status: "running" as const,
    progress: 65, summary: "Fields are being checked.",
    created_at: "2026-09-29T04:59:18Z", updated_at: "2026-09-29T04:59:18Z",
  }];

  assert.deepEqual(taskSnapshot(tasks, "t1"), { ...tasks[0], events: [] });
  assert.equal(taskSnapshot(tasks, "missing"), null);
});
