import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtemp,
  readFile,
  writeFile,
  symlink,
  readdir,
  rm,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { saveCatalogSnapshot } from "../src/index.js";

test("a chosen catalog export is complete, atomic and bounded", async () => {
  const root = await mkdtemp(join(tmpdir(), "minkops-catalog-"));
  try {
    const path = join(root, "catalog.json");
    await saveCatalogSnapshot(path, {
      sources: [{ tool: "tally", company: "Test" }],
    });
    assert.equal(
      JSON.parse(await readFile(path, "utf8")).sources[0].company,
      "Test",
    );
    await saveCatalogSnapshot(path, { sources: [], version: 2 });
    assert.equal(JSON.parse(await readFile(path, "utf8")).version, 2);
    assert.deepEqual(await readdir(root), ["catalog.json"]);
    await assert.rejects(
      saveCatalogSnapshot(join(root, "large.json"), {
        value: "x".repeat(64000001),
      }),
      /64 MB/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test(
  "catalog export refuses a symlink destination",
  { skip: process.platform === "win32" },
  async () => {
    // Windows file symlinks require an additional OS privilege. Linux exercises
    // this guard; native Windows still checks lstat before any replacement.
    const root = await mkdtemp(join(tmpdir(), "minkops-catalog-link-"));
    try {
      await writeFile(join(root, "original.json"), "original");
      await symlink(join(root, "original.json"), join(root, "link.json"));
      await assert.rejects(
        saveCatalogSnapshot(join(root, "link.json"), { sources: [] }),
        /regular file/,
      );
      assert.equal(
        await readFile(join(root, "original.json"), "utf8"),
        "original",
      );
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  },
);
