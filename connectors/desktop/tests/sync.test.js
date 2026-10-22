import assert from "node:assert/strict";
import test from "node:test";
import { batches, compact, countVouchers, pages, readCompanies, readVouchers, runSync } from "../src/sync.js";

/** A Tally that answers the sync's fixed TDL from in-memory companies. */
class FakeTally {
  constructor() {
    this.companies = [];
    this.requests = [];
  }
  add(name, guid, { books = "20260401", alt = { mst: 0, vch: 0 } } = {}) {
    const company = { name, guid, books, alt, masters: [], vouchers: [] };
    this.companies.push(company);
    return company;
  }
  request = async (url, { body }) => {
    this.requests.push(body);
    const id = body.match(/<ID>([^<]+)<\/ID>/)[1];
    const name = body.match(/<SVCURRENTCOMPANY>([^<]*)<\/SVCURRENTCOMPANY>/)?.[1];
    const company = this.companies.find((c) => c.name === name);
    const from = body.match(/&gt;= (\d{8})/)?.[1], to = body.match(/&lt;= (\d{8})/)?.[1];
    const after = Number(body.match(/\$AlterID &gt; (\d+)/)?.[1] ?? 0);
    const guids = [...body.matchAll(/\$GUID = "([^"]+)"/g)].map((m) => m[1]);
    // The collection's own type, not the envelope header's <TYPE>Collection</TYPE>.
    const kind = body.slice(body.indexOf("<TDL>")).match(/<TYPE>([^<]+)<\/TYPE>/)?.[1].toUpperCase();
    const inWindow = (v) => (!from || (v.date >= from && v.date <= to)) && v.alter > after && (!guids.length || guids.includes(v.guid));
    const voucherXml = (v) => `<VOUCHER><GUID>${v.guid}</GUID><ALTERID> ${v.alter}</ALTERID><DATE>${v.date}</DATE><VOUCHERNUMBER>${v.number ?? 1}</VOUCHERNUMBER><NARRATION>${v.narration ?? ""}</NARRATION><EMPTY>  </EMPTY></VOUCHER>`;
    let data = "";
    if (id === "MkSyncCompanies")
      data = this.companies.map((c) => `<COMPANY NAME="${c.name}"><GUID>${c.guid}</GUID><COMPANYNUMBER> 100000</COMPANYNUMBER><BOOKSFROM>${c.books}</BOOKSFROM><ALTMSTID> ${c.alt.mst}</ALTMSTID>${c.alt.vch ? `<ALTVCHID> ${c.alt.vch}</ALTVCHID>` : ""}</COMPANY>`).join("");
    else if (id === "MkSyncIdentity") data = `<COMPANY NAME="${company.name}"><GUID>${company.guid}</GUID><BOOKSFROM>${company.books}</BOOKSFROM></COMPANY>`;
    else if (id === "MkSyncMasters") {
      const type = kind;
      data = company.masters.filter((m) => m.type === type && m.alter > after)
        .map((m) => `<${type} NAME="${m.name}"><GUID>${m.guid}</GUID><ALTERID> ${m.alter}</ALTERID></${type}>`).join("");
    } else if (id === "MkSyncMasterCount") {
      const type = kind;
      data = `<OBJECT><ITEMS> ${company.masters.filter((m) => m.type === type).length}</ITEMS></OBJECT>`;
    } else if (id === "MkSyncMasterCensus") {
      const type = kind;
      data = company.masters.filter((m) => m.type === type).map((m) => `<${type}><GUID>${m.guid}</GUID><ALTERID> ${m.alter}</ALTERID></${type}>`).join("");
    } else if (id === "MkSyncCounts") {
      const counts = {};
      for (const v of company.vouchers.filter(inWindow)) counts[v.date] = (counts[v.date] ?? 0) + 1;
      data = Object.entries(counts).map(([d, n]) => `<OBJECT><VCHCOUNT> ${n}</VCHCOUNT><VCHDAY>${d}</VCHDAY></OBJECT>`).join("");
    } else if (["MkSyncVouchers", "MkSyncCensus", "MkSyncByGuid"].includes(id)) data = company.vouchers.filter(inWindow).map(voucherXml).join("");
    return new Response(`<ENVELOPE><HEADER><VERSION>1</VERSION><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>${data}</COLLECTION></DATA></BODY></ENVELOPE>`);
  };
}

/** A server double that records pages and answers like accounts/sync.py. */
function server(instructions, { census = [], refetch = [] } = {}) {
  const pages = [];
  const upload = async (kind, body) => {
    pages.push({ kind, ...body });
    if (kind === "companies") return { instructions };
    if (kind === "counts") return { census };
    // Like the server, name only changed vouchers of this census page's span.
    if (kind === "census") return { refetch: refetch.filter((g) => body.entries.some((e) => e.guid === g)), tombstoned: 0 };
    return {};
  };
  return { pages, upload };
}
const PLAN = { protocol: 1, port: 9000, batch: 2, page_records: 2 };
const WINDOW = { from: "2026-04-01", to: "2027-03-31" };

test("compaction drops only empty native fields", () => {
  assert.deepEqual(compact({ A: "", B: "  ", C: "No", D: { E: " " }, F: [{ G: "" }, "x"], H: "0" }), { C: "No", F: ["x"], H: "0" });
});

test("companies come with markers, and an empty voucher counter is 0", async () => {
  const tally = new FakeTally();
  tally.add("Fresh Books", "g-1", { alt: { mst: 12, vch: 0 } });
  assert.deepEqual(await readCompanies({ port: 9000, request: tally.request }), [{
    name: "Fresh Books", guid: "g-1", company_number: "100000", books_from: "2026-04-01",
    markers: { alt_mst_id: 12, alt_vch_id: 0, last_voucher_date: null } }]);
  tally.add("Fresh Books Copy", "g-1");
  await assert.rejects(readCompanies({ port: 9000, request: tally.request }), { tallyState: "duplicate_company" });
});

test("counts and vouchers stay inside their window and above their marker", async () => {
  const tally = new FakeTally();
  const company = tally.add("Books", "g-1");
  company.vouchers.push({ guid: "v1", alter: 1, date: "20260901" }, { guid: "v2", alter: 5, date: "20260902" },
    { guid: "v3", alter: 6, date: "20250101" });
  const options = { port: 9000, company: "Books", from: "2026-04-01", to: "2027-03-31", request: tally.request };
  assert.deepEqual(await countVouchers(options), { "2026-09-01": 1, "2026-09-02": 1 });
  assert.deepEqual((await readVouchers({ ...options, after: 1 })).map((v) => v.GUID), ["v2"]);
  assert.equal((await readVouchers({ ...options, after: 1 }))[0].EMPTY, undefined);
});

test("batches cover the whole span contiguously, including empty days", () => {
  const counts = { "2026-09-01": 2, "2026-09-03": 1, "2026-09-05": 5, "2026-09-09": 1 };
  assert.deepEqual(batches(counts, "2026-09-01", "2026-09-10", 3), [
    { from: "2026-09-01", to: "2026-09-04" }, { from: "2026-09-05", to: "2026-09-08" },
    { from: "2026-09-09", to: "2026-09-10" }]);
  assert.deepEqual(batches({}, "2026-09-01", "2026-09-10", 3), [{ from: "2026-09-01", to: "2026-09-10" }]);
});

test("pages respect both the record count and the byte budget", () => {
  const records = Array.from({ length: 5 }, (_, i) => ({ n: i, pad: "x".repeat(40) }));
  assert.deepEqual(pages(records, 2).map((p) => p.length), [2, 2, 1]);
  assert.deepEqual(pages(records, 10, 120).map((p) => p.length), [2, 2, 1]);
});

test("a delta reads only masters and vouchers above the stored markers, then sweeps", async () => {
  const tally = new FakeTally();
  const company = tally.add("Books", "g-1", { alt: { mst: 3, vch: 9 } });
  company.masters.push({ type: "LEDGER", name: "Old", guid: "m1", alter: 1 }, { type: "LEDGER", name: "New", guid: "m2", alter: 3 });
  company.vouchers.push({ guid: "v1", alter: 2, date: "20260901" }, { guid: "v2", alter: 8, date: "20260902" },
    { guid: "v3", alter: 9, date: "20260902" });
  const { pages, upload } = server([{ company: "c-1", guid: "g-1", name: "Books", mode: "delta", window: WINDOW, sweep: true,
    after: { alt_mst_id: 2, alt_vch_id: 7 } }], { census: [{ from: "2026-09-01", to: "2026-09-02" }], refetch: ["v1"] });
  const result = await runSync(PLAN, { request: tally.request, upload });
  assert.deepEqual(result, { protocol: 1, companies: [{ company: "c-1", complete: true }] });
  const masters = pages.filter((p) => p.kind === "masters").flatMap((p) => p.records.map((r) => r.data.GUID));
  assert.deepEqual(masters, ["g-1", "m2"]);
  const vouchers = pages.filter((p) => p.kind === "vouchers").map((p) => p.records.map((r) => r.GUID));
  assert.deepEqual(vouchers, [["v2", "v3"], ["v1"]]);  // The delta, then the census refetch.
  const counts = pages.find((p) => p.kind === "counts");
  assert.deepEqual(counts.counts, { "2026-09-01": 1, "2026-09-02": 2 });
  // The census respects the batch limit of two vouchers per request.
  assert.deepEqual(pages.filter((p) => p.kind === "census").map((p) => [p.from, p.to, p.entries.length]),
    [["2026-09-01", "2026-09-01", 1], ["2026-09-02", "2026-09-02", 2]]);
  assert.equal(pages.filter((p) => p.kind === "master_census").length, 12);
});

test("skipped companies are never read and a failing company does not hide the others", async () => {
  const tally = new FakeTally();
  tally.add("Quiet", "g-1");
  tally.add("Busy", "g-2").vouchers.push({ guid: "v1", alter: 1, date: "20260901" });
  const broken = { ...tally, request: async (url, options) => {
    if (options.body.includes("<SVCURRENTCOMPANY>Busy</SVCURRENTCOMPANY>") && options.body.includes("MkSyncIdentity"))
      return new Response("not xml <");
    return tally.request(url, options);
  } };
  const { upload } = server([
    { company: "c-1", guid: "g-1", name: "Quiet", mode: "skip", reason: "unchanged" },
    { company: "c-2", guid: "g-2", name: "Busy", mode: "full", window: WINDOW, sweep: false }]);
  const result = await runSync(PLAN, { request: broken.request, upload });
  assert.equal(result.companies.length, 1);
  assert.deepEqual([result.companies[0].company, result.companies[0].complete], ["c-2", false]);
  assert.ok(!tally.requests.some((b) => b.includes("<SVCURRENTCOMPANY>Quiet</SVCURRENTCOMPANY>")));
});

test("a company whose identity changed mid-sync is reported incomplete", async () => {
  const tally = new FakeTally();
  tally.add("Books", "g-other");
  const { upload } = server([{ company: "c-1", guid: "g-1", name: "Books", mode: "full", window: WINDOW, sweep: false }]);
  const result = await runSync(PLAN, { request: tally.request, upload });
  assert.equal(result.companies[0].complete, false);
});

test("another Windows user's Tally on this port is never read or uploaded", async () => {
  let asked = 0, sent = 0;
  await assert.rejects(runSync(PLAN, {
    request: async () => { asked++; throw new Error("read"); }, upload: async () => { sent++; return {}; },
    observe: async () => ({ own: 2, listener: { pid: 7, session: 5 }, processes: [{ pid: 7 }] }),
  }), { tallyState: "other_session" });
  assert.deepEqual([asked, sent], [0, 0]);
});

test("an unsupported protocol asks for an update before reading Tally", async () => {
  const tally = new FakeTally();
  await assert.rejects(runSync({ ...PLAN, protocol: 2 }, { request: tally.request, upload: async () => ({}) }),
    /Update Minkops/);
  assert.equal(tally.requests.length, 0);
});
