import test from "node:test";
import assert from "node:assert/strict";
import { progressView } from "../src/starter/workspace/progress.ts";

test("progress describes waiting, work and review without inventing completion", () => {
  assert.equal(
    progressView({ status: "running", progress: 0, events: [] }).label,
    "Waiting to start"
  );
  const review = progressView({
    status: "attention",
    progress: 60,
    events: [{ event_type: "review" }]
  });
  assert.equal(review.label, "Ready for your review");
  assert.equal(review.current, 2);
  assert.equal(review.finished, false);
  assert.equal(review.stages[3], "Save");
});

test("failed work stays at its last observed stage, not at a fictional 100 percent", () => {
  const failed = progressView({
    status: "failed",
    progress: 100,
    events: [{ event_type: "executing" }, { event_type: "failed" }]
  });
  assert.equal(failed.current, 1);
  assert.equal(failed.finished, false);
  assert.equal(failed.label, "Needs attention");
});

test("native save stages distinguish a waiting PC, actual saving and required attention", () => {
  for (const [event_type, label] of [
    ["local_waiting", "Waiting for your PC"],
    ["local_saving", "Saving and checking"],
    ["local_failed", "Needs attention"]
  ]) {
    const view = progressView({
      status: "handoff",
      progress: 85,
      events: [{ event_type }]
    });
    assert.equal(view.current, 3);
    assert.equal(view.label, label);
    assert.equal(view.finished, false);
  }
});

test("local Tally checks have their own short stages without a review stage", () => {
  const view = progressView(
    { status: "completed", progress: 100, events: [] },
    "tally.probe"
  );
  assert.deepEqual(view.stages, ["Your PC", "Check Tally", "Finished"]);
  assert.equal(view.finished, true);
});

test("discovery has no fictional save step and a folder refresh has no review step", () => {
  const task = { status: "running", progress: 0, events: [{ event_type: "queued" }] };
  assert.deepEqual(progressView(task, "source-discovery").stages, [
    "Get ready",
    "Work",
    "Review",
    "Finished"
  ]);
  assert.deepEqual(progressView(task, "files.refresh").stages, [
    "Your PC",
    "Read folder",
    "Finished"
  ]);
});
