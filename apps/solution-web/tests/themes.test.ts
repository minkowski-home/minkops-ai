import assert from "node:assert/strict";
import test from "node:test";
import { THEMES, resolveTheme } from "../src/starter/theme/options.ts";

test("the four brand themes have stable names and a safe default", () => {
  assert.deepEqual(THEMES.map(({ id, label }) => [id, label]), [
    ["minkops-light", "Minkops Light"],
    ["minkops-dark", "Minkops Dark"],
    ["slate-light", "Slate Light"],
    ["slate-dark", "Slate Dark"],
  ]);
  assert.equal(resolveTheme("slate-dark"), "slate-dark");
  assert.equal(resolveTheme("unknown"), "minkops-light");
  assert.equal(resolveTheme(null), "minkops-light");
});
