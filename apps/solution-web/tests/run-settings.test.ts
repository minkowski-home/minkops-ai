import test from "node:test";
import assert from "node:assert/strict";
import { defaultableValues, billOutcome, elapsedLabel } from "../src/starter/workflows/runSettings.ts";

test("save defaults excludes run resources and unsupported fields", () => {
  assert.deepEqual(defaultableValues({review_mode:'only_exceptions', device_id:'pc', discovery_id:'run', checks:['totals']}, {review_mode:{type:'string'}}), {review_mode:'only_exceptions'});
});
test("write outcomes take precedence over findings and retain attention", () => {
  assert.equal(billOutcome('saved', true), 'Saved and verified · check Attention');
  assert.equal(billOutcome('saved', false), 'Saved and verified');
  assert.equal(billOutcome('duplicate', true), 'Duplicate skipped · check Attention');
  assert.equal(billOutcome('writing', true), 'Saving and checking');
  assert.equal(billOutcome('held', true), 'Needs attention');
});

test("elapsed time uses recorded timestamps and refuses missing or future starts", () => {
  assert.equal(elapsedLabel('2026-10-12T10:00:00Z', Date.parse('2026-10-12T10:01:29Z')), '1m 29s');
  assert.equal(elapsedLabel('missing', Date.now()), null);
  assert.equal(elapsedLabel('2099-01-01', Date.now()), null);
});
