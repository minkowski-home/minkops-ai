/** Opt-in live Windows + Tally + real Excel collection against the mock client. */
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve, join } from "node:path";
import ExcelJS from "../../../connectors/desktop/node_modules/exceljs/excel.js";
import {
  inventory,
  inspectExcel,
  discoverTally,
} from "../../../connectors/desktop/src/index.js";
import { collectSources } from "../../../platform/desktop-runtime/src/discovery.js";

const origin = process.env.MINKOPS_SMOKE_URL ?? "http://127.0.0.1:8117";
assert.match(origin, /^http:\/\/(127\.0\.0\.1|localhost):\d+$/);
const root = resolve(
  process.env.MINKOPS_DEMO_FOLDER ??
    join(process.env.TEMP ?? ".", "Minkops Mock Client"),
);
await mkdir(root, { recursive: true });
const w = new ExcelJS.Workbook();
const vendors = w.addWorksheet("Suppliers");
vendors.addTable({
  name: "Suppliers",
  ref: "A3",
  columns: [{ name: "Supplier ID" }, { name: "Supplier" }, { name: "GSTIN" }],
  rows: [
    ["0001", "API Vendor Local", "27AABCM1234C1Z5"],
    ["0002", "API Vendor Interstate", "29AABCM1234C1Z1"],
  ],
});
const codes = w.addWorksheet("Projects");
codes.addTable({
  name: "Projects",
  ref: "B4",
  columns: [{ name: "Cost Code" }, { name: "Project" }],
  rows: [
    ["MOCK-01", "Mock Office"],
    ["MOCK-02", "Mock Warehouse"],
  ],
});
const bills = w.addWorksheet("Bill register");
bills.getCell("A1").value = "Mock client purchase register";
bills.addTable({
  name: "Bills",
  ref: "A5",
  columns: [
    { name: "Entry ID" },
    { name: "Invoice Number" },
    { name: "Supplier ID" },
    { name: "Date" },
    { name: "Subtotal" },
    { name: "CGST" },
    { name: "SGST" },
    { name: "IGST" },
    { name: "Total" },
    { name: "Cost Code" },
  ],
  rows: [
    [
      "seed-1",
      "00017",
      "0001",
      new Date("2026-04-05T00:00:00Z"),
      1000,
      90,
      90,
      0,
      1180,
      "MOCK-01",
    ],
  ],
});
const file = join(root, "Mock Accounts.xlsx");
if (process.env.MINKOPS_CREATE_FIXTURE !== "0")
  await writeFile(file, Buffer.from(await w.xlsx.writeBuffer()));
let cookie = "",
  csrf = "";
async function api(
  path,
  body,
  credential,
  method = body === undefined ? "GET" : "POST",
) {
  const form = body instanceof FormData;
  const r = await fetch(origin + path, {
    method,
    redirect: "error",
    headers: {
      ...(form ? {} : { "Content-Type": "application/json" }),
      ...(credential
        ? { Authorization: `Bearer ${credential}` }
        : { Cookie: cookie, "x-csrf-token": csrf }),
    },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status} ${path}: ${await r.text()}`);
  if (r.headers.get("set-cookie"))
    cookie = r.headers.get("set-cookie").split(";")[0];
  return r.json();
}
await api("/api/auth/login", {
  email: "demo@example.com",
  password: process.env.MINKOPS_DEMO_PASSWORD ?? "long test password 123!",
});
const user = await api("/api/auth/me");
csrf = user.csrf_token;
const base = "/api/tenants/mock-tenant";
const device = await api(base + "/desktop/devices", {
  name: "Windows discovery demo",
  installation_id: randomUUID(),
});
const files = await inventory(root);
const form = new FormData();
form.append("label", "Mock client accounts");
form.append("writable", "true");
form.append("paths", JSON.stringify(files.map((f) => f.path)));
for (const f of files)
  form.append("files", new Blob([Buffer.from(f.content, "base64")]), f.path);
const source = await api(base + "/accounts/sources", form);
await api(base + `/desktop/devices/${device.id}/sources/${source.id}`, {});
const config = {
  depth: "business_mappings",
  excel_source_ids: [source.id],
  tally: {
    company: process.env.MINKOPS_TALLY_COMPANY ?? "Minkops Test",
    port: 9000,
    categories: [
      "company",
      "groups",
      "ledgers",
      "voucher_types",
      "stock_items",
      "stock_groups",
      "units",
      "godowns",
      "cost_centres",
      "cost_categories",
      "currencies",
    ],
  },
};
const run = await api(base + "/discovery/runs", {
  device_id: device.id,
  request_key: randomUUID(),
  config,
});
const claim = await api("/api/desktop/worker/claim", {}, device.credential);
assert.equal(claim.operation, "sources.discover");
const plan = await api(
  `/api/desktop/worker/jobs/${claim.id}/plan?claim_token=${claim.claim_token}`,
  undefined,
  device.credential,
);
const result = await collectSources(plan, {
  folderFor: (id) => {
    assert.equal(id, source.id);
    return root;
  },
  inventory,
  inspectExcel,
  discoverTally,
  onProgress: (source_key, status, category = null) =>
    api(
      `/api/desktop/worker/jobs/${claim.id}/progress`,
      { claim_token: claim.claim_token, source_key, status, category },
      device.credential,
    ),
});
assert.equal(result.sources[0].workbooks[0].structure.sheets.length, 3);
assert.ok(
  result.sources[1].snapshot.collections.every((c) => c.status === "ready"),
);
for (let n = 0; n < 2; n++)
  await api(
    `/api/desktop/worker/jobs/${claim.id}/finish`,
    { claim_token: claim.claim_token, result },
    device.credential,
  );
const saved = await api(base + `/discovery/runs/${run.id}`);
assert.equal(saved.catalog.partial, false);
assert.equal(saved.mapping_run.state, "queued");
const catalog = await api(base + `/discovery/runs/${run.id}/catalog.json`);
assert.equal(
  catalog.sources[0].workbooks[0].structure.sheets[0].tables[0].header_row,
  3,
);
console.log(
  JSON.stringify(
    {
      result: "Live Tally and Excel collected, replayed and persisted",
      folder: root,
      task_id: run.task_id,
      discovery_run_id: run.id,
      mapping_run_id: saved.mapping_run.id,
      source_id: source.id,
      device_id: device.id,
      tally: result.sources[1].snapshot.collections.map((c) => ({
        category: c.category,
        count: c.count,
      })),
      next: "Run the configured hosted worker, review and confirm the proposed mappings.",
    },
    null,
    2,
  ),
);
// This test device is not the interactive desktop app. It leaves no active credential.
await api(
  base + `/desktop/devices/${device.id}`,
  undefined,
  undefined,
  "DELETE",
);
