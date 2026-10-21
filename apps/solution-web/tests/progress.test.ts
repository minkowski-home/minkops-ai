import test from "node:test";
import assert from "node:assert/strict";
import { elapsedLabel, progressView } from "../src/starter/workspace/progress.ts";

test("a durable stage keeps a dashboard snapshot at the same checkpoint before events load", () => {
  const snapshot = { status: "running", progress: 0, stage: "executing", events: [] };
  assert.equal(progressView(snapshot).current, 1);
  assert.equal(progressView(snapshot).current, progressView({ ...snapshot, events: [{ event_type: "executing" }] }).current);
});

test("a run moves through reading, review and saving as its task records them", () => {
  const at = (event_type: string, status: string) => progressView({ status, progress: 0, events: [{ event_type }] });
  assert.equal(at("queued", "running").label, "Waiting to start");
  assert.equal(at("executing", "running").stages[1], "Read");
  const review = at("review", "attention");
  assert.deepEqual([review.current, review.label], [2, "Ready for your review"]);
  assert.equal(review.states[2], "attention");
  const saving = at("writing", "handoff");
  assert.deepEqual([saving.current, saving.label, saving.finished], [3, "Saving and checking", false]);
  assert.equal(progressView({ status: "completed", progress: 100, events: [] }).percent, 100);
});

test("automatic stops show the recorded active-time limit and retained-progress explanation", () => {
  const summary = "Stopped after 45 minutes of active processing. Progress and completed saves are retained; an underway save may still finish.";
  const task = {status: "stopped", progress: 40, events: [
    {event_type: "executing"}, {event_type: "control.stop", summary}
  ]};
  for (const mode of ["run", "simple", "tally.probe"] as const) {
    const view = progressView(task, mode);
    assert.equal(view.activity, summary);
    assert.equal(view.running, false);
    assert.equal(view.finished, false);
  }
});

test("paused and stopped tasks retain their last stage without spinning or completing", () => {
  for (const status of ["paused", "stopped"]) {
    const view = progressView({status, progress: 85, events: [{event_type: "writing"}, {event_type: `control.${status === "paused" ? "pause" : "stop"}`}]});
    assert.equal(view.current, 3);
    assert.equal(view.finished, false); assert.equal(view.running, false);
    assert.equal(view.percent, null);
  }
});

test("failed work stays at its last observed stage, not at a fictional 100 percent", () => {
  const failed = progressView({ status: "failed", progress: 100, events: [{ event_type: "executing" }, { event_type: "failed" }] });
  assert.equal(failed.current, 1);
  assert.equal(failed.finished, false);
  assert.equal(failed.label, "Needs attention");
});

test("checks on a PC have their own short stages without a review stage", () => {
  const probe = progressView({ status: "completed", progress: 100, events: [] }, "tally.probe");
  assert.deepEqual(probe.stages, ["Your PC", "Check Tally", "Finished"]);
  assert.equal(probe.finished, true);
  const folder = progressView({ status: "running", progress: 0, events: [{ event_type: "executing" }] }, "files.refresh");
  assert.deepEqual([folder.stages[1], folder.label], ["Read folder", "Reading your folder"]);
});

test("elapsed time uses recorded timestamps and refuses missing or future starts", () => {
  assert.equal(elapsedLabel('2026-10-12T10:00:00Z', Date.parse('2026-10-12T10:01:29Z')), '1m 29s');
  assert.equal(elapsedLabel('missing', Date.now()), null);
  assert.equal(elapsedLabel('2099-01-01', Date.now()), null);
});
