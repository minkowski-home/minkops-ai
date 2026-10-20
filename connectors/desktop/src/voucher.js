/** Native accounting-voucher adapter, plan protocol 5. One writer for every
 * supported family: a plan states a header and balanced ledger lines; this
 * module rechecks the pinned Tally identities, reads before writing, imports at
 * most once per attempt and accepts only an exact readback. XML/TDL, endpoints
 * and amounts are fixed here; the renderer and the server supply only data.
 *
 * Inventory, bill-wise and multi-centre allocations are outside this contract:
 * the server holds them as named connector limitations before a plan exists. */
import {createHash} from 'node:crypto';
import {XMLParser, XMLValidator} from 'fast-xml-parser';
import {readTallyReferences} from './tally-references.js';
import {boundedText, requireOpenCompany, TallyUnavailable} from './tally-session.js';

/** Plan family -> Tally's predefined base voucher type. */
export const FAMILIES = Object.freeze({
  purchase: 'purchase', journal: 'journal', debit_note: 'debit note',
  payment: 'payment', receipt: 'receipt', contra: 'contra',
});
const BASE_FAMILY = new Map(Object.entries(FAMILIES).map(([family, base]) => [base, family]));
/** Families whose party ledger has a fixed side; others carry no party rule here. */
const PARTY_SIDE = {purchase: 'credit', debit_note: 'debit'};
const NUMBER_FIELDS = new Set(['REFERENCE', 'VOUCHERNUMBER', 'NARRATION']);
const MAX_WINDOW_DAYS = 366;

const list = v => v == null ? [] : Array.isArray(v) ? v : [v];
const raw = v => String(v && typeof v === 'object' ? v['#text'] ?? '' : v ?? '');
const scalar = v => raw(v).trim();
const norm = v => scalar(v).toLowerCase();
const nameOf = r => scalar(r?.['@_NAME'] ?? r?.NAME);
const hash = v => createHash('sha256').update(JSON.stringify(v)).digest('hex');
const xml = v => String(v).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;'}[c]));
const compact = date => date.replaceAll('-', '');
const isoDate = v => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v) && !Number.isNaN(Date.parse(`${v}T00:00:00Z`));
const safeText = (v, max = 200) => typeof v === 'string' && v.trim() !== '' && v.length <= max && !/[\x00-\x1f]/.test(v);
/** Tally's native sign: credits are positive, debits negative. */
const signed = line => line.side === 'credit' ? line.amount_cents : -line.amount_cents;
const byLedger = (a, b) => a.ledger.localeCompare(b.ledger) || a.amount_cents - b.amount_cents;
const nativeCents = v => {
  const n = Number(scalar(v)) * 100;
  if (!Number.isSafeInteger(Math.round(n)) || Math.abs(n - Math.round(n)) > 0.00001) throw new Error('Invalid native money.');
  return Math.round(n);
};
const populated = v => typeof v === 'object' && v !== null ? Object.values(v).some(populated) : v != null && String(v).trim() !== '';

/** One bounded XML exchange with the local Tally HTTP server. */
export async function tallyExchange(company, port, body, request) {
  if (
    typeof company !== "string" ||
    !company.trim() ||
    company.length > 200 ||
    /[\x00-\x1f]/.test(company) ||
    !Number.isInteger(port) ||
    port < 1 ||
    port > 65535
  )
    throw new Error("Invalid Tally target.");
  const response = await request(`http://127.0.0.1:${port}`, {
    method: "POST",
    body,
    headers: { "Content-Type": "text/xml; charset=utf-8" },
    redirect: "error",
    signal: AbortSignal.timeout(20000),
  });
  const source = await boundedText(response, 5_000_000);
  // Tally emits XML 1.0-invalid control-character references in some system
  // fields. Never silently normalize them in a financial write response.
  if (
    /<!DOCTYPE|<!ENTITY|<LINEERROR\b/i.test(source) ||
    XMLValidator.validate(source) !== true
  )
    throw new Error("Tally returned an invalid financial response.");
  return new XMLParser({
    ignoreAttributes: false,
    parseTagValue: false,
    parseAttributeValue: false,
    trimValues: true,
  }).parse(source);
}

// Tally's native reasons stay in diagnostics; users get one short action.
const REJECTIONS = [
  ["date", /\bdate\b|financial year|books? beginning/i,
    "Tally rejected the voucher date. Check the bill date against the company's financial year, then use Retry save."],
  ["permission", /not (?:authori[sz]ed|allowed|permitted)|access denied|no (?:access|rights)|security/i,
    "The Tally user who is logged in cannot create this voucher. Log in as a user allowed to enter purchases, then use Retry save."],
  ["voucher_type", /voucher ?type/i,
    "Tally rejected the purchase voucher type. Check it in Tally, refresh Source Discovery, then start a new run."],
  ["voucher_number", /voucher (?:no\b|number)/i,
    "Tally needs a voucher number for this voucher type. Check its numbering in Tally, then use Retry save."],
  ["ledger", /ledger|does not exist|not found/i,
    "Tally rejected a ledger on this bill. Check the ledgers in Tally, then use Retry save."],
];
export function classifyRejection(reason) {
  const match = REJECTIONS.find(([, pattern]) => pattern.test(String(reason ?? "")));
  return match
    ? { code: match[0], message: match[2] }
    : { code: "other", message: "Tally rejected this bill. Check its voucher settings in Tally, then use Retry save." };
}

/** Classify voucher types by predefined base: RESERVEDNAME for a predefined
 * type, otherwise the base of its PARENT chain. Inactive types stay classified:
 * vouchers recorded under them can still be duplicates. */
export function voucherFamilies(records) {
  const byName = new Map();
  for (const record of records) if (nameOf(record)) byName.set(nameOf(record).toLowerCase(), record);
  const base = (name, depth) => {
    const record = byName.get(name.toLowerCase());
    if (!record) return name.toLowerCase();
    const reserved = scalar(record['@_RESERVEDNAME']);
    if (reserved) return reserved.toLowerCase();
    const parent = scalar(record.PARENT);
    if (!parent || parent.toLowerCase() === name.toLowerCase()) return name.toLowerCase();
    return depth >= 10 ? null : base(parent, depth + 1);
  };
  const family = new Map(), active = new Set();
  for (const [key, record] of byName) {
    const found = BASE_FAMILY.get(base(nameOf(record), 0));
    if (found) family.set(key, found);
    if (norm(record.ISACTIVE) !== 'no') active.add(key);
  }
  return {family, active};
}

/** Structural checks only; business rules are the server's. Throws before any native call. */
export function validatePlan(plan) {
  const fail = reason => { throw new Error(`Unsupported voucher plan: ${reason}.`); };
  if (plan?.format_version !== 5) fail('format');
  if (!Object.hasOwn(FAMILIES, plan.family)) fail('family');
  if (!['append', 'update'].includes(plan.operation)) fail('operation');
  if (!safeText(plan.company) || !safeText(plan.company_guid) || !Number.isInteger(plan.port) || plan.port < 1 || plan.port > 65535) fail('company');
  if (!/^[a-f0-9-]{36}$/.test(plan.remote_id ?? '')) fail('remote id');
  if (!safeText(plan.voucher_type?.NAME) || !safeText(plan.voucher_type?.GUID)) fail('voucher type');
  if (!['strict', 'retry_after_read'].includes(plan.fence)) fail('fence');
  const header = plan.header ?? {};
  if (!isoDate(header.date)) fail('date');
  if (header.reference != null && !safeText(header.reference, 100)) fail('reference');
  if (header.party_ledger != null && !safeText(header.party_ledger)) fail('party');
  if (header.narration != null && (typeof header.narration !== 'string' || header.narration.length > 500)) fail('narration');
  if (header.tag != null && !/^[a-z]{1,20}$/.test(header.tag)) fail('tag');

  const lines = plan.lines;
  if (!Array.isArray(lines) || lines.length < 2 || lines.length > 40) fail('line count');
  let debit = 0, credit = 0;
  for (const line of lines) {
    if (!safeText(line?.ledger) || !['debit', 'credit'].includes(line.side) || !Number.isSafeInteger(line.amount_cents) || line.amount_cents <= 0) fail('line');
    if (line.allocation != null && !['category', 'category_guid', 'centre', 'centre_guid'].every(k => safeText(line.allocation[k]))) fail('allocation');
    if (line.side === 'debit') debit += line.amount_cents; else credit += line.amount_cents;
  }
  if (!Number.isSafeInteger(debit) || debit !== credit) fail('unbalanced');
  if (new Set(lines.map(l => l.ledger)).size !== lines.length) fail('repeated ledger');
  if (plan.references?.company_guid !== plan.company_guid || lines.some(l => !safeText(plan.references.ledgers?.[l.ledger]?.GUID))) fail('references');
  const party = header.party_ledger == null ? null : lines.find(l => l.ledger === header.party_ledger);
  if (header.party_ledger != null && !party) fail('party line');
  if (PARTY_SIDE[plan.family] && party?.side !== PARTY_SIDE[plan.family]) fail('party side');

  const duplicate = plan.duplicate ?? {};
  const {from, to} = duplicate.window ?? {};
  if (!isoDate(from) || !isoDate(to) || from > header.date || to < header.date
      || (Date.parse(to) - Date.parse(from)) / 86_400_000 > MAX_WINDOW_DAYS) fail('window');
  if (duplicate.strategy === 'document') {
    if (header.party_ledger == null || duplicate.party_ledger !== header.party_ledger || !safeText(duplicate.number, 100)
        || !Array.isArray(duplicate.number_fields) || !duplicate.number_fields.length || duplicate.number_fields.some(f => !NUMBER_FIELDS.has(f))
        || !Array.isArray(duplicate.families) || !duplicate.families.includes(plan.family) || duplicate.families.some(f => !Object.hasOwn(FAMILIES, f)))
      fail('document duplicate');
  } else if (duplicate.strategy === 'tag' || duplicate.strategy === 'counterpart') {
    const match = duplicate.match;
    if (header.tag == null || !lines.some(l => l.ledger === match?.ledger && l.side === match.side && l.amount_cents === match.amount_cents)) fail('match');
    if (!Array.isArray(duplicate.distinct) || duplicate.distinct.length > 1000 || duplicate.distinct.some(t => !/^[a-f0-9-]{36}$/.test(t))) fail('distinct');
    if (duplicate.strategy === 'counterpart' && plan.family !== 'contra') fail('counterpart family');
  } else fail('duplicate');
  if (plan.operation === 'update' && (duplicate.strategy !== 'document' || typeof plan.expected?.fingerprint !== 'string')) fail('correction');
  return plan;
}

/** Every voucher in an inclusive calendar window. Native date variables can be
 * coerced differently, so the filter compares calendar components. */
export async function readVouchers({company, port = 9000, window}, {request = fetch} = {}) {
  if (!isoDate(window?.from) || !isoDate(window?.to)) throw new Error('Invalid voucher window.');
  const from = compact(window.from), to = compact(window.to);
  const day = '($$YearOfDate:$Date * 10000 + $$MonthOfDate:$Date * 100 + $$DayOfDate:$Date)';
  const body = `<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>MinkopsVouchers</ID></HEADER><BODY><DESC><STATICVARIABLES><SVCURRENTCOMPANY>${xml(company)}</SVCURRENTCOMPANY><SVFROMDATE TYPE="Date">${from}</SVFROMDATE><SVTODATE TYPE="Date">${to}</SVTODATE><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="MinkopsVouchers"><TYPE>Voucher</TYPE><FETCH>MasterID,GUID,AlterID,Date,VoucherNumber,Reference,Narration,PartyLedgerName,VoucherTypeName,IsInvoice,AllLedgerEntries.*,LedgerEntries.*,AllInventoryEntries.*,InventoryEntries.*</FETCH><FILTER>MinkopsVoucherWindow</FILTER></COLLECTION><SYSTEM TYPE="Formulae" NAME="MinkopsVoucherWindow">(${day} >= ${from}) AND (${day} &lt;= ${to})</SYSTEM></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>`;
  const envelope = (await tallyExchange(company, port, body, request)).ENVELOPE;
  if (scalar(envelope?.HEADER?.STATUS) !== '1' || !Object.hasOwn(envelope?.BODY?.DATA ?? {}, 'COLLECTION'))
    throw new Error('Tally did not confirm the voucher collection.');
  const vouchers = list(envelope.BODY.DATA.COLLECTION?.VOUCHER);
  if (vouchers.length > 10000) throw new Error('The voucher window exceeds 10,000 records.');
  return vouchers.map(v => {
    const date = scalar(v.DATE);
    if (date < from || date > to) throw new Error('Tally returned a voucher outside the requested window.');
    const entries = list(v['ALLLEDGERENTRIES.LIST'] ?? v['LEDGERENTRIES.LIST']);
    const allocations = [];
    let unsupported = scalar(v.ISINVOICE).toLowerCase() === 'yes'
      || ['ALLINVENTORYENTRIES.LIST', 'INVENTORYENTRIES.LIST'].some(key => populated(v[key]));
    for (const entry of entries) {
      if (['BILLALLOCATIONS.LIST', 'INVENTORYALLOCATIONS.LIST'].some(key => populated(entry[key]))) unsupported = true;
      const centres = list(entry['CATEGORYALLOCATIONS.LIST']).flatMap(category =>
        list(category['COSTCENTREALLOCATIONS.LIST']).filter(populated).map(centre => ({
          ledger: scalar(entry.LEDGERNAME), category: scalar(category.CATEGORY), centre: scalar(centre.NAME), amount_cents: nativeCents(centre.AMOUNT)})));
      // One centre per line is the contract; anything richer cannot be preserved or compared.
      if (centres.length > 1) unsupported = true;
      allocations.push(...centres);
    }
    return {
      guid: scalar(v.GUID), master_id: scalar(v.MASTERID), date, voucher_type: scalar(v.VOUCHERTYPENAME),
      reference: scalar(v.REFERENCE), number: scalar(v.VOUCHERNUMBER), narration: scalar(v.NARRATION),
      party_ledger: scalar(v.PARTYLEDGERNAME), tag: scalar(v.NARRATION).match(/\[Minkops [a-z]+:([a-f0-9-]{36})\]/)?.[1] ?? null,
      unsupported, fingerprint: `v5:${hash(v)}`,
      entries: entries.map(e => ({ledger: scalar(e.LEDGERNAME), amount_cents: nativeCents(e.AMOUNT)})).sort(byLedger),
      allocations: allocations.sort(byLedger),
    };
  });
}

/** Pinned company, ledgers, voucher type and allocation masters must still be
 * exactly the discovered ones. Returns null when anything moved. */
async function recheck(plan, {request, readReferences}) {
  const allocations = plan.lines.filter(l => l.allocation).map(l => l.allocation);
  const categories = ['company', 'ledgers', 'voucher_types', ...(allocations.length ? ['cost_centres', 'cost_categories'] : [])];
  const snapshot = await readReferences({company: plan.company, port: plan.port, categories}, {request});
  if (snapshot.collections.some(c => c.status !== 'ready')) return null;
  const records = category => snapshot.collections.find(c => c.category === category)?.records ?? [];
  const companies = records('company');
  if (companies.length !== 1 || scalar(companies[0].GUID) !== plan.company_guid) return null;
  // Detailed XML pads numeric ALTERID text; every other identity field is exact.
  const same = (field, live, pinned) => field === 'ALTERID' ? scalar(live) === scalar(pinned) : raw(live) === raw(pinned);
  for (const line of plan.lines) {
    const found = records('ledgers').filter(r => nameOf(r) === line.ledger), pinned = plan.references.ledgers[line.ledger];
    if (found.length !== 1 || ['GUID', 'PARENT', 'ALTERID'].some(k => pinned[k] != null && !same(k, found[0][k], pinned[k]))) return null;
  }
  for (const allocation of allocations)
    for (const [category, name, guid] of [['cost_centres', 'centre', 'centre_guid'], ['cost_categories', 'category', 'category_guid']]) {
      const found = records(category).filter(r => nameOf(r) === allocation[name]);
      if (found.length !== 1 || scalar(found[0].GUID) !== allocation[guid]) return null;
    }
  const typeRecords = records('voucher_types'), types = voucherFamilies(typeRecords);
  const key = plan.voucher_type.NAME.toLowerCase(), live = typeRecords.filter(r => nameOf(r).toLowerCase() === key);
  if (live.length !== 1 || scalar(live[0].GUID) !== plan.voucher_type.GUID || !types.active.has(key) || types.family.get(key) !== plan.family) return null;
  return {types, typeName: nameOf(live[0])};
}

/** The approved lines, allocations and date; the voucher type only when given. */
function equal(current, plan, typeName) {
  const lines = plan.lines.map(l => ({ledger: l.ledger, amount_cents: signed(l)})).sort(byLedger);
  const allocations = plan.lines.filter(l => l.allocation)
    .map(l => ({ledger: l.ledger, category: l.allocation.category, centre: l.allocation.centre, amount_cents: signed(l)})).sort(byLedger);
  return current.date === compact(plan.header.date) && hash(current.entries) === hash(lines) && hash(current.allocations) === hash(allocations)
    && (typeName == null || current.voucher_type.toLowerCase() === typeName.toLowerCase());
}

/** A document number as a whole token: "INV-17" never matches "INV-170". */
function containsToken(haystack, needle) {
  const text = norm(haystack), token = norm(needle);
  for (let at = text.indexOf(token); token && at >= 0; at = text.indexOf(token, at + 1))
    if (!/[a-z0-9]/.test(text[at - 1] ?? '') && !/[a-z0-9]/.test(text[at + token.length] ?? '')) return true;
  return false;
}
const FIELD_VALUE = {REFERENCE: v => v.reference, VOUCHERNUMBER: v => v.number};
/** Party plus document number in the client's configured number fields. */
export function documentMatches(voucher, duplicate) {
  return norm(voucher.party_ledger) === norm(duplicate.party_ledger) && duplicate.number_fields.some(field =>
    field === 'NARRATION' ? containsToken(voucher.narration, duplicate.number) : norm(FIELD_VALUE[field](voucher)) === norm(duplicate.number));
}

/** The observed voucher as receipts and attention observations report it. */
export function observedVoucher(v, family) {
  return {guid: v.guid, master_id: v.master_id, date: v.date, voucher_type: v.voucher_type, family,
    reference: v.reference, number: v.number, narration: v.narration, party_ledger: v.party_ledger, tag: v.tag,
    lines: v.entries, allocations: v.allocations, fingerprint: v.fingerprint};
}

const hold = (code, message) => ({outcome: 'attention', hold: code, ...(message ? {message} : {})});
const attention = message => ({outcome: 'attention', message});

/** What already exists decides the outcome: {result} ends the attempt, {current} proceeds. */
function decide(plan, before, live, receipt) {
  const duplicate = plan.duplicate, familyOf = v => live.types.family.get(v.voucher_type.toLowerCase()) ?? null;
  if (duplicate.strategy === 'document') {
    const found = before.filter(v => duplicate.families.includes(familyOf(v)) && documentMatches(v, duplicate));
    const other = found.find(v => familyOf(v) !== plan.family);
    if (other) return {result: attention(`Tally already records this document as a ${other.voucher_type.slice(0, 80)} voucher. Review it in Tally; Minkops will not add another.`)};
    if (found.length > 1) return {result: attention('Multiple vouchers share this document identity. Review Tally before retrying.')};
    const current = found[0];
    if (current && equal(current, plan)) return {result: receipt('duplicate', current)};
    if (current && (plan.operation !== 'update' || plan.expected.fingerprint !== current.fingerprint)) return {result: receipt('correction', current)};
    if (!current && plan.operation === 'update') return {result: attention('The voucher selected for correction no longer exists.')};
    if (current && (!/^\d+$/.test(current.master_id) || !/^[a-f0-9-]{36}(?:-[a-f0-9]{8})?$/.test(current.guid)))
      return {result: attention('Existing voucher has no supported stable identifier.')};
    // Never flatten inventory, bill-wise or foreign lines into an approved correction.
    if (current && (current.unsupported || current.entries.some(e => !plan.lines.some(l => l.ledger === e.ledger))))
      return {result: attention('Existing voucher has allocations this plan cannot preserve. Correct it in Tally, then reconcile.')};
    return {current: current ?? null};
  }
  const own = before.filter(v => v.tag === plan.remote_id);
  if (own.length) return {result: own.length === 1 && equal(own[0], plan, live.typeName) ? receipt('duplicate', own[0]) : hold('destination_changed')};
  // Tagged siblings the server proved to be different real transactions are not candidates.
  const candidates = before.filter(v => !(v.tag && duplicate.distinct.includes(v.tag)));
  if (duplicate.strategy === 'counterpart') {
    const covering = candidates.filter(v => familyOf(v) === 'contra'
      && plan.lines.every(l => v.entries.some(e => e.ledger === l.ledger && e.amount_cents === signed(l))));
    if (covering.length === 1 && covering[0].tag) return {result: {...receipt('duplicate', covering[0]), covered: true}};
    if (covering.length) return {result: hold('possible_existing')};
  }
  const date = compact(plan.header.date), match = duplicate.match;
  if (candidates.some(v => v.date === date && v.entries.some(e => e.ledger === match.ledger && e.amount_cents === signed(match))))
    return {result: hold('possible_existing')};
  return {current: null};
}

function importBody(plan, typeName, current) {
  const guid = current?.guid ?? plan.remote_id, type = current?.voucher_type ?? typeName, header = plan.header;
  const attributes = current
    ? `DATE="${xml(current.date)}" TAGNAME="MASTER ID" TAGVALUE="${xml(current.master_id)}" Action="Alter"`
    : `REMOTEID="${xml(guid)}" Action="Create"`;
  const narration = (header.tag ? `[Minkops ${header.tag}:${plan.remote_id}] ` : '') + (header.narration ?? '');
  const lines = plan.lines.map(line => {
    const amount = signed(line), deemed = amount < 0 ? 'Yes' : 'No', money = (amount / 100).toFixed(2), a = line.allocation;
    const allocation = a ? `<CATEGORYALLOCATIONS.LIST><CATEGORY>${xml(a.category)}</CATEGORY><ISDEEMEDPOSITIVE>${deemed}</ISDEEMEDPOSITIVE><COSTCENTREALLOCATIONS.LIST><NAME>${xml(a.centre)}</NAME><AMOUNT>${money}</AMOUNT></COSTCENTREALLOCATIONS.LIST></CATEGORYALLOCATIONS.LIST>` : '';
    return `<ALLLEDGERENTRIES.LIST><LEDGERNAME>${xml(line.ledger)}</LEDGERNAME><ISDEEMEDPOSITIVE>${deemed}</ISDEEMEDPOSITIVE><AMOUNT>${money}</AMOUNT>${allocation}</ALLLEDGERENTRIES.LIST>`;
  }).join('');
  return `<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME><STATICVARIABLES><SVCURRENTCOMPANY>${xml(plan.company)}</SVCURRENTCOMPANY></STATICVARIABLES></REQUESTDESC><REQUESTDATA><TALLYMESSAGE><VOUCHER ${attributes} VCHTYPE="${xml(type)}" OBJVIEW="Accounting Voucher View"><GUID>${xml(guid)}</GUID><DATE>${compact(header.date)}</DATE><VOUCHERTYPENAME>${xml(type)}</VOUCHERTYPENAME>${header.reference ? `<REFERENCE>${xml(header.reference)}</REFERENCE>` : ''}${header.party_ledger ? `<PARTYLEDGERNAME>${xml(header.party_ledger)}</PARTYLEDGERNAME>` : ''}<PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW><ISINVOICE>No</ISINVOICE><NARRATION>${xml(narration)}</NARRATION>${lines}</VOUCHER></TALLYMESSAGE></REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>`;
}

/** One approved voucher. `fence: "strict"` requires a durable local intent
 * before the import, so no later attempt can resend an uncertain one;
 * `retry_after_read` lets a later explicit retry import again only after a
 * fresh read finds nothing. Within one attempt an import is never repeated. */
export async function saveVoucher(plan, {
  request = fetch, beforeImport, diagnose = () => {},
  // Session checks bypass the diagnosing transport; they classify their own failures.
  sessionRequest = fetch, pc, processes, wait,
  requireCompany = requireOpenCompany, readReferences = readTallyReferences, readVouchers: read = readVouchers,
} = {}) {
  validatePlan(plan);
  if (plan.fence === 'strict' && typeof beforeImport !== 'function') throw new Error('A durable voucher fence is required.');
  const company = {company: plan.company, company_guid: plan.company_guid};
  const session = {port: plan.port, request: sessionRequest, pc, processes, wait};
  const window = () => read({company: plan.company, port: plan.port, window: plan.duplicate.window}, {request});
  try {
    await requireCompany(company, session);
    const live = await recheck(plan, {request, readReferences});
    if (!live) return hold('destination_changed', 'A ledger, voucher type or cost allocation changed in Tally since discovery. Refresh Source Discovery before saving.');
    const familyOf = v => live.types.family.get(v.voucher_type.toLowerCase()) ?? null;
    const receipt = (outcome, v) => ({outcome, company_guid: plan.company_guid, current: observedVoucher(v, familyOf(v))});
    const decision = decide(plan, await window(), live, receipt);
    if (decision.result) return decision.result;
    const current = decision.current;
    await requireCompany(company, session);
    if (plan.fence === 'strict' && await beforeImport(plan) !== true) return hold('uncertain_import');

    let uncertain = null;
    try {
      const response = await tallyExchange(plan.company, plan.port, importBody(plan, live.typeName, current), request);
      const result = response.RESPONSE ?? response.ENVELOPE?.BODY?.DATA;
      const created = Number(scalar(result?.CREATED) || 0), altered = Number(scalar(result?.ALTERED) || 0);
      if (!result || scalar(result.ERRORS) !== '0' || (current ? altered !== 1 || created !== 0 : created !== 1 || altered !== 0))
        uncertain = new Error('Tally did not confirm exactly one write.');
    } catch (error) {
      uncertain = error; // Reconcile below with reads only; never resend.
    }
    const identifies = plan.duplicate.strategy === 'document'
      ? v => familyOf(v) === plan.family && documentMatches(v, plan.duplicate)
      : v => v.tag === plan.remote_id;
    const saved = (await window()).filter(identifies);
    // Tally may assign its own GUID on creation; the observed identity is authoritative.
    if (saved.length === 1 && equal(saved[0], plan, current?.voucher_type ?? live.typeName) && (!current || saved[0].guid === current.guid))
      return receipt('saved', saved[0]);
    if (uncertain?.tallyLineError) return hold('rejected', classifyRejection(uncertain.tallyLineError).message);
    return hold('uncertain_import', plan.fence === 'strict'
      ? 'Tally did not confirm this voucher. Review Tally; Minkops will not import this intent again.'
      : 'Tally did not confirm the write, and the approved version is not present. Review Tally, then use Retry save; it checks Tally again before importing.');
  } catch (error) {
    if (!(error instanceof TallyUnavailable)) throw error;
    diagnose({state: error.tallyState, cause: error.detail?.cause, running: error.detail?.running, error: error.message});
    return hold(error.tallyState, error.message);
  }
}
