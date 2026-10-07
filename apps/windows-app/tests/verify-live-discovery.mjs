/** Confirm a real hosted proposal, then verify live unchanged/partial/recovery refreshes. */
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { writeFile, unlink } from "node:fs/promises";
import { join } from "node:path";
import {
  inventory,
  inspectExcel,
  discoverTally,
} from "../../../connectors/desktop/src/index.js";
import { collectSources } from "../../../platform/desktop-runtime/src/discovery.js";
const origin = process.env.MINKOPS_SMOKE_URL ?? "http://127.0.0.1:8117";
assert.match(origin, /^http:\/\/(127\.0\.0\.1|localhost):\d+$/);
const root = process.env.MINKOPS_DEMO_FOLDER;
assert.ok(root);
const id = process.argv[2];
assert.match(id, /^[a-f0-9-]{36}$/);
let cookie = "",
  csrf = "";
async function api(path, body, credential, expected = 200) {
  const r = await fetch(origin + path, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      "Content-Type": "application/json",
      ...(credential
        ? { Authorization: `Bearer ${credential}` }
        : { Cookie: cookie, "x-csrf-token": csrf }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  assert.equal(r.status, expected, `HTTP ${r.status}: ${path}`);
  if (r.headers.get("set-cookie"))
    cookie = r.headers.get("set-cookie").split(";")[0];
  return r.json();
}
await api("/api/auth/login", {
  email: "demo@example.com",
  password: process.env.MINKOPS_DEMO_PASSWORD ?? "long test password 123!",
});
csrf = (await api("/api/auth/me")).csrf_token;
const base = "/api/tenants/mock-tenant";
let run = await api(base + `/discovery/runs/${id}`);
assert.ok(["review", "completed"].includes(run.state));
const mappings = run.catalog.excel_mappings ?? run.mapping_run.result;
assert.equal(mappings.sheets.length, 3);
console.log(
  JSON.stringify({
    hosted_mapping: mappings.sheets.map((s) => ({
      sheet: s.sheet,
      table: s.table,
      role: s.role,
      header_row: s.header_row,
      columns: s.columns.length,
    })),
  }),
);
run = await api(base + `/discovery/runs/${id}/confirm`, {
  excel_mappings: mappings,
});
assert.equal(run.ready, true);
const devices = await api(base + "/desktop/devices");
const prior = devices.find((d) => d.id === run.device_id);
const device = await api(
  base + "/desktop/devices",
  { name: prior.name, installation_id: prior.installation_id },
  undefined,
  201,
);
const config = run.config;
async function refresh(cfg) {
  const fresh = await api(
    base + "/discovery/runs",
    { device_id: device.id, request_key: randomUUID(), config: cfg },
    undefined,
    202,
  );
  const claim = await api("/api/desktop/worker/claim", {}, device.credential);
  const plan = await api(
    `/api/desktop/worker/jobs/${claim.id}/plan?claim_token=${claim.claim_token}`,
    undefined,
    device.credential,
  );
  const result = await collectSources(plan, {
    folderFor: (sourceId) => {
      assert.ok(config.excel_source_ids.includes(sourceId));
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
  await api(
    `/api/desktop/worker/jobs/${claim.id}/finish`,
    { claim_token: claim.claim_token, result },
    device.credential,
  );
  return api(base + `/discovery/runs/${fresh.id}`);
}
const unchanged = await refresh(config);
assert.equal(unchanged.state, "completed");
assert.equal(unchanged.ready, true);
assert.ok(unchanged.catalog.review.reused_from);
const partial = await refresh({
  ...config,
  tally: { ...config.tally, port: 65534 },
});
assert.equal(partial.catalog.partial, true);
assert.equal(partial.ready, false);
assert.equal(
  partial.catalog.sources.find((s) => s.tool === "excel").workbooks[0].status,
  "ready",
);
await api(base + `/discovery/runs/${partial.id}/confirm`, {}, undefined, 409);
const recovery = await refresh(config);
assert.equal(recovery.ready, true);
const damaged = join(root, "Corrupt for testing.xlsx");
await writeFile(damaged, "Intentional invalid xlsx test fixture", {
  flag: "wx",
});
try {
  const partialBook = await refresh(config);
  assert.equal(partialBook.catalog.partial, true);
  assert.equal(partialBook.ready, false);
  assert.equal(partialBook.mapping_run, null);
  assert.equal(
    partialBook.catalog.sources.find((s) => s.tool === "tally").status,
    "ready",
  );
  assert.equal(
    partialBook.catalog.sources
      .find((s) => s.tool === "excel")
      .workbooks.find((b) => b.path === "Corrupt for testing.xlsx").status,
    "unavailable",
  );
  await api(
    base + `/discovery/runs/${partialBook.id}/confirm`,
    {},
    undefined,
    409,
  );
} finally {
  await unlink(damaged);
}
const final = await refresh(config);
assert.equal(final.ready, true);
console.log(
  JSON.stringify(
    {
      result:
        "Real hosted mappings confirmed; live unchanged refresh, unavailable Tally and damaged workbook partial results, blocked confirmation and recovery passed",
      confirmed_run_id: id,
      latest_run_id: final.id,
      task_id: final.task_id,
    },
    null,
    2,
  ),
);
// Revoke only this test registration. The interactive desktop pairs separately.
const response = await fetch(origin + base + `/desktop/devices/${device.id}`, {
  method: "DELETE",
  headers: { Cookie: cookie, "x-csrf-token": csrf },
});
assert.equal(response.status, 200);
