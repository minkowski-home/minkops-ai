import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import test from "node:test";

const design = new URL("../../../design/", import.meta.url);
const read = (path: string) => readFileSync(new URL(path, design), "utf8");

test("design source reflects the shared employee and workflow console", () => {
  const guide = read("readme.md");
  const preview = read("ui_kits/console/index.html");
  const kitGuide = read("ui_kits/console/README.md");
  for (const label of ["Employees", "Workflows", "Activity"]) {
    assert.match(preview, new RegExp(label));
    assert.match(kitGuide, new RegExp(label));
  }
  assert.doesNotMatch(preview + kitGuide, /Agent Teams|CX Response Team|agent catalogue/i);
  for (const theme of ["Minkops Light", "Minkops Dark", "Slate Light", "Slate Dark"]) {
    assert.match(guide + preview, new RegExp(theme));
  }
});

test("design assets and registry include the four theme source", () => {
  const manifest = JSON.parse(read("_ds_manifest.json"));
  assert.ok(manifest.globalCssPaths.includes("tokens/themes.css"));
  assert.ok(existsSync(new URL("assets/logos/logo-slate.PNG", design)));
  assert.ok(existsSync(new URL("assets/logos/logo-orange.PNG", design)));
});
