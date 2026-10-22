/** Read-only incremental collection of the user's Tally for the server mirror.
 *
 * Sync protocol 1. The server decides what to fetch; this module only reads,
 * with fixed TDL, one request at a time and with long timeouts, because Tally
 * serves one request at a time and an abandoned request still keeps it busy.
 * Company markers are read first, so changes made during collection are
 * fetched again next time rather than missed. Records are compacted (empty
 * native fields dropped) before upload; nothing is interpreted here.
 */
import { XMLParser, XMLValidator } from "fast-xml-parser";
import { boundedText, openCompanyScope, requireOwnTally, tallyCompanyNumber } from "./tally-session.js";

export const PROTOCOL = 1;
/** Native master types mirrored for lookups, checks and the writer's references. */
export const MASTER_TYPES = Object.freeze(["Group", "Ledger", "VoucherType", "CostCategory", "CostCentre", "Currency",
  "Unit", "Godown", "StockGroup", "StockCategory", "StockItem", "TaxUnit"]);
const DAY = "($$YearOfDate:$Date * 10000 + $$MonthOfDate:$Date * 100 + $$DayOfDate:$Date)";
const VOUCHER_FETCH = "*,AllLedgerEntries.*,LedgerEntries.*,AllInventoryEntries.*,InventoryEntries.*";
const TIMEOUT = 300_000;
const RESPONSE_LIMIT = 32_000_000;
const PAGE_BYTES = 3_000_000;

const parser = new XMLParser({ ignoreAttributes: false, parseTagValue: false, parseAttributeValue: false, trimValues: true });
const list = (v) => (v == null ? [] : Array.isArray(v) ? v : [v]);
const scalar = (v) => String(v && typeof v === "object" ? v["#text"] ?? "" : v ?? "").trim();
const xml = (v) => String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" })[c]);
const compactDate = (iso) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) throw new Error("Invalid sync window.");
  return iso.replaceAll("-", "");
};
const isoDay = (day) => `${day.slice(0, 4)}-${day.slice(4, 6)}-${day.slice(6, 8)}`;

/** Drop empty and whitespace-only native fields; meaningful values ("No", "0") stay. */
export function compact(value) {
  if (Array.isArray(value)) return value.map(compact).filter((v) => !empty(v));
  if (value && typeof value === "object")
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, compact(v)]).filter(([, v]) => !empty(v)));
  return typeof value === "string" && !value.trim() ? "" : value;
}
const empty = (v) => v === "" || v == null || (Array.isArray(v) && !v.length) || (typeof v === "object" && !Object.keys(v).length);

/** One bounded export; refuses malformed or failed responses before parsing values. */
async function exportCollection(request, port, company, id, tdl) {
  const statics = `${company ? `<SVCURRENTCOMPANY>${xml(company)}</SVCURRENTCOMPANY>` : ""}<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>`;
  const body = `<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>${id}</ID></HEADER><BODY><DESC><STATICVARIABLES>${statics}</STATICVARIABLES><TDL><TDLMESSAGE>${tdl}</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>`;
  const response = await request(`http://127.0.0.1:${port}`, {
    method: "POST", body, headers: { "Content-Type": "text/xml; charset=utf-8" }, redirect: "error",
    signal: AbortSignal.timeout(TIMEOUT),
  });
  const source = await boundedText(response, RESPONSE_LIMIT);
  if (/<!DOCTYPE|<!ENTITY|<LINEERROR\b/i.test(source) || XMLValidator.validate(source) !== true)
    throw new Error("Tally returned an invalid export.");
  const envelope = parser.parse(source).ENVELOPE;
  if (envelope === "") return {};
  if (!envelope || scalar(envelope.HEADER?.STATUS) !== "1") throw new Error("Tally did not confirm the export.");
  return envelope.BODY?.DATA?.COLLECTION ?? {};
}

const windowFilter = (from, to, after) =>
  `<SYSTEM TYPE="Formulae" NAME="MkSyncWindow">(${DAY} &gt;= ${compactDate(from)}) AND (${DAY} &lt;= ${compactDate(to)})${
    after ? ` AND ($AlterID &gt; ${Number(after)})` : ""}</SYSTEM>`;

/** Every open company with its markers, read before anything else. */
export async function readCompanies({ port, request = fetch, pc = "this PC" }) {
  const collection = await exportCollection(request, port, null, "MkSyncCompanies",
    '<COLLECTION NAME="MkSyncCompanies" ISMODIFY="No"><TYPE>Company</TYPE><FETCH>Name,GUID,CompanyNumber,BooksFrom,AltMstId,AltVchId,LastVoucherDate</FETCH></COLLECTION>');
  const companies = list(collection.COMPANY).map((record) => {
    const books = scalar(record.BOOKSFROM);
    if (!/^\d{8}$/.test(books)) throw new Error("Tally did not report when a company's books begin.");
    const last = scalar(record.LASTVOUCHERDATE);
    return {
      company: (record["@_NAME"] ?? scalar(record.NAME)).trim(), company_guid: scalar(record.GUID),
      company_number: tallyCompanyNumber(record.COMPANYNUMBER), books_from: isoDay(books),
      // A company with no vouchers reports no AltVchId; it counts as 0.
      markers: { alt_mst_id: Number(scalar(record.ALTMSTID)) || 0, alt_vch_id: Number(scalar(record.ALTVCHID)) || 0,
                 last_voucher_date: /^\d{8}$/.test(last) ? isoDay(last) : null },
    };
  });
  // Every request names its company, so names must be unique; GUIDs must be too.
  return openCompanyScope(companies, { pc }).map((c) => ({
    name: c.company, guid: c.company_guid, company_number: c.company_number, books_from: c.books_from, markers: c.markers,
  }));
}

/** The company's own record, kept in the mirror as its identity. */
export async function readIdentity({ port, company, request = fetch }) {
  const collection = await exportCollection(request, port, company, "MkSyncIdentity",
    '<COLLECTION NAME="MkSyncIdentity" ISMODIFY="No"><TYPE>Company</TYPE><FETCH>*</FETCH></COLLECTION>');
  const record = list(collection.COMPANY).find((r) => (r["@_NAME"] ?? scalar(r.NAME)) === company);
  if (!record) throw new Error("Company identity is unavailable.");
  return { type: "COMPANY", data: compact(record) };
}

/** Masters of one type, optionally only those altered after a marker. */
export async function readMasters({ port, company, type, after = 0, request = fetch }) {
  if (!MASTER_TYPES.includes(type)) throw new Error("Unsupported master type.");
  const filter = after ? `<FILTER>MkSyncAfter</FILTER>` : "";
  const formula = after ? `<SYSTEM TYPE="Formulae" NAME="MkSyncAfter">$AlterID &gt; ${Number(after)}</SYSTEM>` : "";
  const collection = await exportCollection(request, port, company, "MkSyncMasters",
    `<COLLECTION NAME="MkSyncMasters" ISMODIFY="No"><TYPE>${type}</TYPE><FETCH>*</FETCH>${filter}</COLLECTION>${formula}`);
  return list(collection[type.toUpperCase()]).map((data) => ({ type: type.toUpperCase(), data: compact(data) }));
}

/** An independent count of one master type, for the census guard. */
export async function countMasters({ port, company, type, request = fetch }) {
  const collection = await exportCollection(request, port, company, "MkSyncMasterCount",
    `<COLLECTION NAME="MkSyncMasterSource" ISMODIFY="No"><TYPE>${type}</TYPE></COLLECTION><COLLECTION NAME="MkSyncMasterCount" ISMODIFY="No"><SOURCECOLLECTION>MkSyncMasterSource</SOURCECOLLECTION><BY>All:1</BY><AGGRCOMPUTE>Items:Sum:1</AGGRCOMPUTE><FETCH>All,Items</FETCH></COLLECTION>`);
  return list(collection.OBJECT).reduce((n, o) => n + (Number(scalar(o.ITEMS)) || 0), 0);
}

/** GUID and AlterID of every master of one type. */
export async function censusMasters({ port, company, type, request = fetch }) {
  const collection = await exportCollection(request, port, company, "MkSyncMasterCensus",
    `<COLLECTION NAME="MkSyncMasterCensus" ISMODIFY="No"><TYPE>${type}</TYPE><FETCH>GUID,AlterID</FETCH></COLLECTION>`);
  return list(collection[type.toUpperCase()]).map((r) => ({ guid: scalar(r.GUID), alter_id: Number(scalar(r.ALTERID)) || 0 }));
}

/** Voucher counts per day in a window, from a source collection: {YYYY-MM-DD: n}. */
export async function countVouchers({ port, company, from, to, after = 0, request = fetch }) {
  const collection = await exportCollection(request, port, company, "MkSyncCounts",
    `<COLLECTION NAME="MkSyncSource" ISMODIFY="No"><TYPE>Voucher</TYPE><FILTER>MkSyncWindow</FILTER></COLLECTION><COLLECTION NAME="MkSyncCounts" ISMODIFY="No"><SOURCECOLLECTION>MkSyncSource</SOURCECOLLECTION><BY>VchDay:${DAY}</BY><AGGRCOMPUTE>VchCount:Sum:1</AGGRCOMPUTE><FETCH>VchDay,VchCount</FETCH></COLLECTION>${windowFilter(from, to, after)}`);
  const counts = {};
  for (const object of list(collection.OBJECT)) {
    const day = scalar(object.VCHDAY);
    if (!/^\d{8}$/.test(day)) throw new Error("Tally returned an invalid voucher count.");
    counts[isoDay(day)] = (counts[isoDay(day)] ?? 0) + (Number(scalar(object.VCHCOUNT)) || 0);
  }
  return counts;
}

/** Complete vouchers in a window, optionally only those altered after a marker. */
export async function readVouchers({ port, company, from, to, after = 0, request = fetch }) {
  const collection = await exportCollection(request, port, company, "MkSyncVouchers",
    `<COLLECTION NAME="MkSyncVouchers" ISMODIFY="No"><TYPE>Voucher</TYPE><FETCH>${VOUCHER_FETCH}</FETCH><FILTER>MkSyncWindow</FILTER></COLLECTION>${windowFilter(from, to, after)}`);
  const records = list(collection.VOUCHER).map(compact);
  for (const record of records) {
    const day = scalar(record.DATE);
    if (day < compactDate(from) || day > compactDate(to)) throw new Error("Tally returned a voucher outside the window.");
  }
  return records;
}

/** GUID, AlterID, number and date of every voucher in a window. */
export async function censusVouchers({ port, company, from, to, request = fetch }) {
  const collection = await exportCollection(request, port, company, "MkSyncCensus",
    `<COLLECTION NAME="MkSyncCensus" ISMODIFY="No"><TYPE>Voucher</TYPE><FETCH>GUID,AlterID,VoucherNumber,Date</FETCH><FILTER>MkSyncWindow</FILTER></COLLECTION>${windowFilter(from, to)}`);
  return list(collection.VOUCHER).map((r) => ({ guid: scalar(r.GUID), alter_id: Number(scalar(r.ALTERID)) || 0,
    number: scalar(r.VOUCHERNUMBER), date: isoDay(scalar(r.DATE)) }));
}

/** Complete vouchers by GUID, for what a census found changed. */
export async function readVouchersByGuid({ port, company, guids, request = fetch }) {
  const records = [];
  for (let at = 0; at < guids.length; at += 50) {
    const formula = guids.slice(at, at + 50).map((g) => `($GUID = "${xml(g)}")`).join(" OR ");
    const collection = await exportCollection(request, port, company, "MkSyncByGuid",
      `<COLLECTION NAME="MkSyncByGuid" ISMODIFY="No"><TYPE>Voucher</TYPE><FETCH>${VOUCHER_FETCH}</FETCH><FILTER>MkSyncGuids</FILTER></COLLECTION><SYSTEM TYPE="Formulae" NAME="MkSyncGuids">${formula}</SYSTEM>`);
    records.push(...list(collection.VOUCHER).map(compact));
  }
  return records;
}

/** Contiguous day spans covering [from, to] whole, each holding at most `limit`
 * vouchers by the counts; one busy day stands alone. Days without vouchers are
 * covered too, because a census of an empty day is how a deletion is found. */
export function batches(counts, from, to, limit) {
  const spans = [];
  let current = { from, n: 0 };
  for (const [day, n] of Object.entries(counts).filter(([d]) => d >= from && d <= to).sort()) {
    if (current.n && current.n + n > limit) {
      spans.push({ from: current.from, to: previousDay(day) });
      current = { from: day, n: 0 };
    }
    current.n += n;
  }
  spans.push({ from: current.from, to });
  return spans;
}
const previousDay = (day) => new Date(Date.parse(`${day}T00:00:00Z`) - 86_400_000).toISOString().slice(0, 10);

/** Records in pages bounded by count and size. */
export function pages(records, limit, bytes = PAGE_BYTES) {
  const out = [];
  let page = [], size = 0;
  for (const record of records) {
    const length = JSON.stringify(record).length;
    if (page.length && (page.length >= limit || size + length > bytes)) {
      out.push(page);
      page = [];
      size = 0;
    }
    page.push(record);
    size += length;
  }
  if (page.length) out.push(page);
  return out;
}

/** Run one sync: report companies, then collect what the server asks for each.
 *
 * `upload(kind, body)` sends one page and returns the server's answer; it
 * owns sequence numbers and retries. A company that cannot be collected is
 * reported incomplete so its version is never published; a closed Tally or a
 * stopped task ends the whole sync with its own message.
 */
export async function runSync(plan, { request = fetch, upload, onProgress = async () => {}, pc = "this PC", observe, shared }) {
  if (plan?.protocol !== PROTOCOL) throw new Error("Update Minkops on this PC to sync with this server.");
  const { port } = plan;
  // Books are read only from this Windows user's own Tally.
  await requireOwnTally({ port, pc, ...(observe ? { observe } : {}), ...(shared === undefined ? {} : { shared }) });
  const companies = await readCompanies({ port, request, pc });
  await onProgress({ activity: "Read open companies", companies: companies.length });
  const { instructions } = await upload("companies", { companies });
  const results = [];
  for (const step of instructions.filter((s) => s.mode !== "skip")) {
    const company = step.name, key = step.company, after = step.after ?? {};
    try {
      await onProgress({ activity: `Reading ${company}`, company });
      const identity = await readIdentity({ port, company, request });
      if (scalar(identity.data.GUID) !== step.guid) throw new Error("Company identity changed during the sync.");
      await upload("masters", { company: key, records: [identity] });
      for (const type of MASTER_TYPES) {
        const records = await readMasters({ port, company, type, after: after.alt_mst_id, request });
        for (const page of pages(records, plan.page_records)) await upload("masters", { company: key, records: page });
      }
      const { from, to } = step.window;
      const changed = await countVouchers({ port, company, from, to, after: after.alt_vch_id, request });
      // Only spans holding changed vouchers are read; a quiet window costs one count.
      for (const span of batches(changed, from, to, plan.batch).filter((s) =>
        Object.keys(changed).some((day) => day >= s.from && day <= s.to))) {
        const records = await readVouchers({ port, company, ...span, after: after.alt_vch_id, request });
        for (const page of pages(records, plan.page_records)) await upload("vouchers", { company: key, records: page });
        await onProgress({ activity: `Collected vouchers to ${span.to}`, company });
      }
      if (step.sweep) await sweep({ plan, request, upload, company, key, from, to, onProgress });
      results.push({ company: key, complete: true });
    } catch (error) {
      if (error.code === "TASK_STOPPED" || error.userSafe || error.status) throw error;
      results.push({ company: key, complete: false,
        error: "Could not collect complete company data. Keep the company open in Tally and refresh again." });
    }
  }
  return { protocol: PROTOCOL, companies: results };
}

/** The deletion sweep: counts, then a census of the days the server names. */
async function sweep({ plan, request, upload, company, key, from, to, onProgress }) {
  const { port } = plan;
  const counts = await countVouchers({ port, company, from, to, request });
  const { census } = await upload("counts", { company: key, counts });
  for (const span of census) {
    for (const part of batches(counts, span.from, span.to, plan.batch)) {
      const entries = await censusVouchers({ port, company, ...part, request });
      const { refetch } = await upload("census", { company: key, ...part, entries });
      if (refetch.length) {
        const records = await readVouchersByGuid({ port, company, guids: refetch, request });
        for (const page of pages(records, plan.page_records)) await upload("vouchers", { company: key, records: page });
      }
    }
    await onProgress({ activity: `Checked vouchers to ${span.to}`, company });
  }
  for (const type of MASTER_TYPES) {
    const count = await countMasters({ port, company, type, request });
    const entries = await censusMasters({ port, company, type, request });
    await upload("master_census", { company: key, type: type.toUpperCase(), count, entries });
  }
}
