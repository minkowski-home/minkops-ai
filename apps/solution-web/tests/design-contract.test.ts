import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import test from "node:test";

const design = new URL("../../../design/", import.meta.url);
const read = (path: string) => readFileSync(new URL(path, design), "utf8");

test("design assets and registry include the four theme source", () => {
  const manifest = JSON.parse(read("_ds_manifest.json"));
  assert.ok(manifest.globalCssPaths.includes("tokens/themes.css"));
  assert.ok(existsSync(new URL("assets/logos/logo-slate.PNG", design)));
  assert.ok(existsSync(new URL("assets/logos/logo-orange.PNG", design)));
});
