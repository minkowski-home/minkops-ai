import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile, symlink, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { inventory, readOpenCompanies } from "../src/index.js";

test("open-company read sends only a fixed company export and parses names", async () => {
  let sent;
  const result = await readOpenCompanies({
    request: async (url, options) => {
      sent = { url, ...options };
      return new Response(
        '<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><COMPANY NAME="Minkops Test"><NAME>Minkops Test</NAME><GUID>g1</GUID></COMPANY><COMPANY NAME="Second &amp; Co"><NAME>Second &amp; Co</NAME><GUID>g2</GUID></COMPANY></COLLECTION></DATA></BODY></ENVELOPE>',
      );
    },
  });
  assert.deepEqual(result.map((c) => c.company), ["Minkops Test", "Second & Co"]);
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
      readOpenCompanies({ request: async () => new Response(text) }),
    );
  }
});

test("Tally typed company names retain text and never become object strings", async () => {
  const result = await readOpenCompanies({
    request: async () =>
      new Response(
        "<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>" +
          '<COMPANY NAME="Minkops Test" RESERVEDNAME=""><NAME TYPE="String">Minkops Test</NAME><GUID TYPE="String">g1</GUID></COMPANY>' +
          '<COMPANY NAME="Attribute &amp; Co"><GUID>g2</GUID></COMPANY>' +
          "</COLLECTION></DATA></BODY></ENVELOPE>",
      ),
  });
  assert.deepEqual(result.map((c) => c.company), ["Minkops Test", "Attribute & Co"]);
  await assert.rejects(
    readOpenCompanies({
      request: async () =>
        new Response(
          "<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><COMPANY><NAME><UNEXPECTED>nested</UNEXPECTED></NAME><GUID>g</GUID></COMPANY></COLLECTION></DATA></BODY></ENVELOPE>",
        ),
    }),
    { tallyState: "invalid_response" },
  );
});

test("Tally rejects configurable remote addresses and invalid ports", async () => {
  for (const port of [0, -1, "9000", 65536])
    await assert.rejects(readOpenCompanies({ port }));
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
