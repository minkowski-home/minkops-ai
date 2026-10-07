import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile, readFile, symlink, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { inventory, replaceApproved, tallyProbe } from "../src/index.js";
import { createHash } from "node:crypto";

const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");

test("Tally probe sends only a fixed company export and parses names", async () => {
  let sent;
  const result = await tallyProbe({
    request: async (url, options) => {
      sent = { url, ...options };
      return new Response(
        '<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><COMPANY NAME="Minkops Test"><NAME>Minkops Test</NAME></COMPANY><COMPANY NAME="Second &amp; Co"><NAME>Second &amp; Co</NAME></COMPANY></COLLECTION></DATA></BODY></ENVELOPE>',
      );
    },
  });
  assert.deepEqual(result, {
    available: true,
    companies: ["Minkops Test", "Second & Co"],
  });
  assert.equal(sent.url, "http://127.0.0.1:9000");
  assert.equal(sent.redirect, "error");
  assert.match(sent.body, /<TALLYREQUEST>Export<\/TALLYREQUEST>/);
  assert.doesNotMatch(sent.body, /Import|Execute/);
});

test("Tally rejects errors, malformed XML, entity definitions and large responses", async () => {
  for (const text of [
    "<ENVELOPE><LINEERROR>Denied</LINEERROR></ENVELOPE>",
    "<broken",
    '<!DOCTYPE x [<!ENTITY a "b">]><ENVELOPE/>',
    "x".repeat(1_000_001),
  ]) {
    await assert.rejects(
      tallyProbe({ request: async () => new Response(text) }),
    );
  }
});

test("Tally typed company names retain text and never become object strings", async () => {
  const result = await tallyProbe({
    request: async () =>
      new Response(
        "<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>" +
          '<COMPANY NAME="Minkops Test" RESERVEDNAME=""><NAME TYPE="String">Minkops Test</NAME></COMPANY>' +
          '<COMPANY NAME="Attribute &amp; Co"/>' +
          "</COLLECTION></DATA></BODY></ENVELOPE>",
      ),
  });
  assert.deepEqual(result, {
    available: true,
    companies: ["Minkops Test", "Attribute & Co"],
  });
  await assert.rejects(
    tallyProbe({
      request: async () =>
        new Response(
          "<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><COMPANY><NAME><UNEXPECTED>nested</UNEXPECTED></NAME></COMPANY></COLLECTION></DATA></BODY></ENVELOPE>",
        ),
    }),
    /company name/i,
  );
});

test("Tally rejects configurable remote addresses and invalid ports", async () => {
  for (const port of [0, -1, "9000", 65536])
    await assert.rejects(tallyProbe({ port }));
});

test("native folder inventory skips hidden files and refuses symlink escape", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "minkops-source-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  await writeFile(join(root, "bill.pdf"), "%PDF-1.4 dummy");
  await writeFile(join(root, ".private.pdf"), "%PDF-private");
  await writeFile(join(root, "notes.txt"), "not selected");
  assert.deepEqual(
    (await inventory(root)).map((f) => f.path),
    ["bill.pdf"],
  );
  await symlink(
    tmpdir(),
    join(root, "escape"),
    process.platform === "win32" ? "junction" : "dir",
  );
  await assert.rejects(inventory(root), /link/i);
});

test("approved native replacement verifies before/after, replay, backup and conflicts", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "minkops-write-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const before = Buffer.from("original workbook");
  const after = Buffer.from("approved workbook");
  await writeFile(join(root, "register.xlsx"), before);
  const backups = [];
  const spec = {
    path: "register.xlsx",
    before_sha256: hash(before),
    after_sha256: hash(after),
  };
  assert.deepEqual(
    await replaceApproved(root, spec, after, async (b) => backups.push(b)),
    after,
  );
  assert.deepEqual(backups, [before]);
  await replaceApproved(root, spec, after, async () =>
    assert.fail("replay backed up again"),
  );
  await writeFile(join(root, "register.xlsx"), "external edit");
  await assert.rejects(
    replaceApproved(root, spec, after, async () => {}),
    /changed/,
  );
  assert.equal(
    await readFile(join(root, "register.xlsx"), "utf8"),
    "external edit",
  );
  await assert.rejects(
    replaceApproved(
      root,
      { ...spec, path: "../escape.xlsx" },
      after,
      async () => {},
    ),
  );
  await assert.rejects(
    replaceApproved(root, spec, Buffer.from("corrupt"), async () => {}),
    /integrity/,
  );
});

test("native write never follows a symlink destination", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "minkops-link-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  await writeFile(join(root, "original.xlsx"), "original");
  let path = "alias.xlsx";
  if (process.platform === "win32") {
    // Directory junctions need no elevated privilege and exercise the Windows
    // reparse-point boundary. Linux additionally covers a direct file symlink.
    await symlink(root, join(root, "alias"), "junction");
    path = "alias/original.xlsx";
  } else await symlink(join(root, "original.xlsx"), join(root, path));
  await assert.rejects(
    replaceApproved(
      root,
      { path, before_sha256: hash("original"), after_sha256: hash("after") },
      Buffer.from("after"),
      async () => {},
    ),
    /link/i,
  );
  assert.equal(await readFile(join(root, "original.xlsx"), "utf8"), "original");
});
