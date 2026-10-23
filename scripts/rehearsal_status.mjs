// Is the five-company rehearsal ready? Read-only: the companion's own
// readOpenCompanies, compared with each package company's pinned GUID.
//
//   node scripts/rehearsal_status.mjs [PACKAGE] [--port 9000]
//
// Exits non-zero when a rehearsal company is closed or a same-named company
// with another GUID is open instead. Never opens, closes or writes to Tally.
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import { readOpenCompanies } from "../connectors/desktop/src/tally-session.js";

const args = process.argv.slice(2);
const portAt = args.indexOf("--port");
const port = portAt >= 0 ? Number(args[portAt + 1]) : 9000;
const pkg = args.find((arg, i) => !arg.startsWith("--") && args[i - 1] !== "--port") ?? "packages/tally-demo-20261018";

const expected = [];
for (const entry of (await readdir(pkg, { withFileTypes: true })).filter((e) => e.isDirectory() && /^\d\d-/.test(e.name))) {
  const bills = JSON.parse(await readFile(join(pkg, entry.name, "evidence/expected-bills.json"), "utf8"));
  expected.push({ folder: entry.name, company: bills[0].company, company_guid: bills[0].company_guid, bills: bills.length });
}
const open = await readOpenCompanies({ port });
let ready = true;
for (const company of expected) {
  const found = open.find((c) => c.company === company.company);
  const state = !found ? "closed" : found.company_guid !== company.company_guid ? "different company open" : "ready";
  ready &&= state === "ready";
  console.log(`${state.padEnd(22)} ${company.company} (${company.bills} labelled bills, books from ${found?.books_from ?? "?"})`);
}
for (const extra of open.filter((c) => !expected.some((e) => e.company === c.company)))
  console.log(`${"also open".padEnd(22)} ${extra.company}`);
process.exit(ready ? 0 : 1);
