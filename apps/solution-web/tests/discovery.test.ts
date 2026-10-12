import test from "node:test";
import assert from "node:assert/strict";
import { discoveryProgress, discoverySources, sourcePage, type DiscoveryRun } from "../src/starter/accounts/discoveryView.ts";

const run = (extra: Partial<DiscoveryRun> = {}): DiscoveryRun => ({
  id: "run", task_id: "task", device_id: "pc", state: "queued", ready: false,
  config: { depth: "client_context", excel_source_ids: [], tally: { port: 9000, period: { from: "2026-10-01", to: "2026-10-02" } } },
  observations: [], mapping_run: null, catalog: null, ...extra
});

test("13 companies remain separate and searchable, with bounded pages and counts by type", () => {
  const sources = discoverySources(run({ catalog: {
    partial: false, review: { status: "required", reused_from: null }, excel_mappings: null,
    sources: [{ key: "tally", tool: "tally", status: "ready", snapshot: { companies: Array.from({ length: 13 }, (_, i) => ({
      company: `Company ${i}`, company_guid: `guid-${i}`, status: "ready",
      master_summary: { exported_count: 7, unique_count: 5, duplicate_count: 1, metadata_count: 1, counts_by_type: { LEDGER: 3, STOCKITEM: 2 } },
      masters: { status: "ready", count: 7, records: [] }, vouchers: { status: "ready", count: 0, records: [] }
    })) } }]
  } }));
  assert.equal(sources.length, 13);
  assert.equal(new Set(sources.map(s => s.key)).size, 13);
  assert.deepEqual(sources[0].collections[0].counts, { LEDGER: 3, STOCKITEM: 2 });
  assert.equal(sources[0].collections[0].count, 5);
  assert.equal(sources[0].collections[1].count, 0);
  assert.equal(sourcePage(sources, "", 0).items.length, 8);
  assert.equal(sourcePage(sources, "", 1).items.length, 5);
  assert.equal(sourcePage(sources, "Company 12", 9).items[0].label, "Company 12");
  assert.equal(sourcePage(sources, "missing", 0).items.length, 0);
});

test("legacy catalogs count typed masters without exposing names or inventing unique counts", () => {
  const sources = discoverySources(run({ catalog: {
    partial: false, review: { status: "required", reused_from: null }, excel_mappings: null,
    sources: [{ key: "tally", tool: "tally", status: "ready", snapshot: { companies: [{ company: "Legacy", status: "ready",
      masters: { status: "ready", count: 3, records: [{ type: "LEDGER", data: { NAME: "Secret supplier" } }, { type: "LEDGER", data: {} }, { type: "CUSTOMMASTER", data: {} }] }
    }] } }]
  } }));
  const masters = sources[0].collections[0];
  assert.deepEqual(masters.counts, { LEDGER: 2, CUSTOMMASTER: 1 });
  assert.equal(masters.label, "Exported masters");
  assert.ok(!JSON.stringify(sources).includes("Secret supplier"));
  assert.equal(sources[0].collections[1].count, undefined);
});

test("company lookup failures and source failures remain visible", () => {
  const sources = discoverySources(run({ catalog: {
    partial: true, review: { status: "required", reused_from: null }, excel_mappings: null,
    sources: [{ key: "tally", tool: "tally", status: "ready", snapshot: { companies: [{ company: "Conflicting", status: "ready", master_lookup_error: "Conflicting identity", masters: { status: "ready", count: 2, records: [] } }] } }]
  } }));
  assert.equal(sources[0].status, "unavailable");
  assert.equal(sources[0].collections[0].status, "unavailable");
  assert.equal(sources[0].error, "Conflicting identity");
});

test("progress distinguishes PC wait, measured collection, hosted work, review and verified completion", () => {
  assert.equal(discoveryProgress(run()).states[0], "waiting");
  const collecting = discoveryProgress(run({ state: "executing", observations: [{ key: "tally", status: "reading", category: "Company A", progress: { completed: 2, total: 7, activity: "Collected masters", item: "Company A" } }] }));
  assert.equal(collecting.states[1], "active");
  assert.equal(collecting.percent, 29);
  assert.equal(collecting.activity, "Collected masters · Company A");
  assert.equal(collecting.countLabel, "2 of 7 native reads");
  const catalog = { partial: false, review: { status: "required", reused_from: null }, sources: [], excel_mappings: null };
  const interpreting = discoveryProgress(run({ catalog, state: "executing" }));
  assert.equal(interpreting.current, 1);
  assert.equal(interpreting.percent, null, "AI duration is unknown");
  assert.equal(interpreting.activity, "Checking context and mappings");
  assert.equal(discoveryProgress(run({ catalog, state: "review" })).states[2], "attention");
  assert.equal(discoveryProgress(run({ catalog, state: "completed", ready: true })).percent, 100);
});

test("partial or failed runs never show finished or continue animating", () => {
  for (const value of [run({ state: "failed" }), run({ state: "review", catalog: { partial: true, review: { status: "required", reused_from: null }, sources: [], excel_mappings: null } }), run({ state: "completed", ready: false })]) {
    const view = discoveryProgress(value);
    assert.equal(view.finished, false);
    assert.equal(view.running, false);
    assert.ok(view.percent !== 100);
  }
});

test("company activity is visible before the receipt and switching sources does not reuse an old percentage", () => {
  const current = run({ state: "executing", observations: [{ key: "tally", category: "A", status: "reading", progress: { completed: 3, total: 7, activity: "Collected masters", item: "A" } }] });
  assert.equal(discoverySources(current)[0].status, "reading");
  current.observations.push({ key: "folder", status: "reading" });
  assert.equal(discoveryProgress(current).percent, null);
  assert.equal(discoveryProgress(current).activity, "Reading · Excel folder");
  assert.equal(discoverySources(run({ state: "failed" }))[0].status, "unavailable");
});
