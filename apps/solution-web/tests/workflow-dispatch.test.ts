import test from "node:test";
import assert from "node:assert/strict";
import { presentationFor } from "../src/starter/workflows/presentation.ts";

test("installed presentation selects existing screens independently of the workflow key", () => {
  assert.equal(presentationFor({ key: "another-client-discovery", presentation: "accounts-discovery" }), "accounts-discovery");
  assert.equal(presentationFor({ key: "another-bill", presentation: "accounts-bill" }), "accounts-bill");
});

test("legacy metadata resolves current screens and unknown presentations fail closed", () => {
  assert.equal(presentationFor({ key: "source-discovery" }), "accounts-discovery");
  assert.equal(presentationFor({ key: "bill-entry" }), "accounts-bill");
  assert.equal(presentationFor({ key: "planned-demo" }), null);
  assert.equal(presentationFor({ key: "unknown", presentation: "remote-import" }), null);
});
