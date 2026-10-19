/** Bounded purchase-voucher adapter. Read-before-write and full readback are
 * mandatory; raw XML/TDL, endpoints and actions never come from the renderer.
 * Voucher types come from the live company, never a hard-coded name. */
import { createHash } from "node:crypto";
import { XMLParser, XMLBuilder, XMLValidator } from "fast-xml-parser";
import { boundedText } from "./index.js";
import { readTallyReferences } from "./tally-references.js";
import { requireOpenCompany, TallyUnavailable } from "./tally-session.js";

const xml = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&apos;",
      })[c],
  );
const list = (v) => (v == null ? [] : Array.isArray(v) ? v : [v]);
const text = (v) => (typeof v === "object" && v !== null ? v["#text"] : v);
const norm = (v) => String(v).trim().toLowerCase();
const year = (s) => Number(s.slice(0, 4)) - (Number(s.slice(4, 6)) < 4 ? 1 : 0);
const digest = (v) =>
  createHash("sha256").update(JSON.stringify(v)).digest("hex");
// Detailed XML pads numeric AlterID text; reference collections trim it. Only
// normalize that numeric field, retaining exact ledger GUIDs and parent names.
const referenceDigest = (field, value) => digest(
  field === "ALTERID" && typeof value === "string" && /^\s*\d+\s*$/.test(value)
    ? value.trim() : value,
);
const unsupported = Symbol("unsupported allocations");
const kind = Symbol("purchase or journal record");
/** A failure with one user action, safe to show verbatim (see worker.js). */
const actionable = (message) => Object.assign(new Error(message), { userSafe: true });
const typeName = (r) => String(text(r?.["@_NAME"] ?? r?.NAME) ?? "").trim();

/** Classify voucher types by their predefined base: RESERVEDNAME for a
 * predefined type, otherwise the base of its PARENT, followed by name. The
 * server applies the same rule when a run chooses its type
 * (platform/.../accounts/voucher_types.py). Inactive types stay in the family:
 * vouchers recorded under them are still possible duplicates. */
export function purchaseVoucherTypes(records) {
  const byName = new Map();
  for (const record of records) if (typeName(record)) byName.set(typeName(record).toLowerCase(), record);
  const resolve = (name, depth) => {
    const record = byName.get(name.toLowerCase());
    if (!record) return name;
    const reserved = String(text(record["@_RESERVEDNAME"]) ?? "").trim();
    if (reserved) return reserved;
    const parent = String(text(record.PARENT) ?? "").trim();
    if (!parent || parent.toLowerCase() === name.toLowerCase()) return typeName(record);
    return depth >= 10 ? null : resolve(parent, depth + 1);
  };
  const types = { purchase: new Set(), journal: new Set(), active: new Set() };
  for (const [key, record] of byName) {
    const base = resolve(typeName(record), 0)?.toLowerCase();
    if (base === "purchase") types.purchase.add(key);
    if (base === "journal") types.journal.add(key);
    if (String(text(record.ISACTIVE) ?? "").trim().toLowerCase() !== "no") types.active.add(key);
  }
  return types;
}
// Plans without live references predate voucher-type discovery.
const LEGACY_TYPES = { purchase: new Set(["purchase"]), journal: new Set(), active: new Set(["purchase"]) };

/** Fixed native attention operations. Renderer cannot supply XML or endpoints. */
export async function inspectTallyAttention(plan, {request = fetch, createSupplier = false} = {}) {
  const snapshot = await readTallyReferences({company: plan.company, port: plan.port, categories: ["company", "ledgers", "voucher_types"]}, {request});
  const types = purchaseVoucherTypes(snapshot.collections.find(c => c.category === "voucher_types")?.records ?? []);
  const companies = snapshot.collections.find(c => c.category === "company")?.records ?? [];
  if (companies.length !== 1 || text(companies[0].GUID) !== plan.company_guid)
    throw new Error("Tally company changed.");
  let ledgers = snapshot.collections.find(c => c.category === "ledgers")?.records ?? [];
  const matches = ledgers.filter(m => norm(text(m["@_NAME"] ?? m.NAME)) === norm(plan.vendor));
  if (matches.length > 1) throw new Error("Supplier ledger identity is ambiguous.");
  if (createSupplier && !matches.length) {
    if (typeof plan.vendor !== "string" || !plan.vendor.trim() || plan.vendor.length > 200 || /[\x00-\x1f]/.test(plan.vendor))
      throw new Error("Invalid supplier name.");
    let ledger = `<LEDGER NAME="${xml(plan.vendor)}" ACTION="Create"><NAME>${xml(plan.vendor)}</NAME><PARENT>Sundry Creditors</PARENT><ISBILLWISEON>No</ISBILLWISEON></LEDGER>`;
    if (plan.gst_supplier) {
      const template = await readGSTSupplier(plan, plan.gst_supplier.template.name,
        {request, identity: {GUID: plan.gst_supplier.template.guid}});
      ledger = buildGSTSupplier(plan, template);
      // A closed or replaced company must never fall back to Tally's selected
      // company between template export and this irreversible master import.
      await requireOpenCompany({company: plan.company, company_guid: plan.company_guid}, {port: plan.port, request});
    }
    const body = `<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>All Masters</REPORTNAME><STATICVARIABLES><SVCURRENTCOMPANY>${xml(plan.company)}</SVCURRENTCOMPANY></STATICVARIABLES></REQUESTDESC><REQUESTDATA><TALLYMESSAGE>${ledger}</TALLYMESSAGE></REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>`;
    // Losing an import acknowledgement never permits another import in this
    // attempt. The next explicit action starts with the same exact master read.
    await exchange(plan.company, plan.port, body, request);
    const after = await readTallyReferences({company: plan.company, port: plan.port, categories: ["company", "ledgers"]}, {request});
    const observed = after.collections.find(c => c.category === "company")?.records ?? [];
    if (observed.length !== 1 || text(observed[0].GUID) !== plan.company_guid)
      throw new Error("Tally company changed.");
    ledgers = after.collections.find(c => c.category === "ledgers")?.records ?? [];
  }
  const supplier = plan.gst_supplier ? await readGSTSupplier(plan, plan.vendor,
    {request, identity: ledgers.find(master => text(master["@_NAME"] ?? master.NAME) === plan.vendor)}) : null;
  if (plan.gst_supplier && !verifyGSTSupplier(supplier, plan.gst_supplier))
    throw actionable("Supplier GST details need review in Tally. The bill has not been queued for saving.");
  const bills = (await readTallyBills(plan, {request, types})).filter(v =>
    v[kind] === "purchase" && v.vendor === plan.vendor && v.invoice_number === plan.invoice_number);
  return {company_guid: plan.company_guid, ledgers, current: bills.length === 1 ? bills[0] : null,
    ...(supplier ? {supplier} : {})};
}

const gstScalar = value => String(text(value) ?? "").trim();
function gstValues(value, names) {
  const result = new Set();
  if (Array.isArray(value)) for (const item of value) for (const entry of gstValues(item, names)) result.add(entry);
  else if (value && typeof value === "object") for (const [key, child] of Object.entries(value)) {
    if (names.includes(key)) for (const item of list(child)) if (gstScalar(item)) result.add(gstScalar(item));
    if (child && typeof child === "object") for (const entry of gstValues(child, names)) result.add(entry);
  }
  return result;
}
function validGSTPlan(gst) {
  const number = gst?.gstin, alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  if (!gst || gst.version !== 1 || typeof number !== "string" ||
      !/^[0-9]{2}[A-Z]{3}[ABCFGHJLPT][A-Z][0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/.test(number) ||
      Number(number.slice(0, 2)) < 1 || Number(number.slice(0, 2)) > 38 || ["25", "28"].includes(number.slice(0, 2)) ||
      gst.state_code !== number.slice(0, 2) || !["Regular", "Composition"].includes(gst.registration_type) ||
      !/^[1-9][0-9]{5}$/.test(gst.pincode) || !/^\d{4}-\d{2}-\d{2}$/.test(gst.applicable_from) ||
      !Array.isArray(gst.address) || gst.address.length < 1 || gst.address.length > 4 ||
      [gst.state, gst.place_of_supply, ...gst.address].some(v => typeof v !== "string" || !v.trim() || v.length > 250 || /[\x00-\x1f]/.test(v)))
    throw new Error("Invalid approved GST supplier details.");
  let sum = 0;
  for (let index = 0; index < 14; index++) {
    const product = alphabet.indexOf(number[index]) * (index % 2 ? 2 : 1);
    sum += Math.floor(product / 36) + product % 36;
  }
  if (number[14] !== alphabet[(36 - sum % 36) % 36]) throw new Error("Invalid GSTIN check character.");
}

/** Construct only a new party master; no identity, balances or banking state is copied. */
export function buildGSTSupplier(plan, template) {
  const gst = plan.gst_supplier;
  validGSTPlan(gst);
  if (!template || gstScalar(template.GUID) !== gst.template.guid || gstScalar(template.ALTERID) !== gst.template.alter_id ||
      gstScalar(template["@_NAME"] ?? template.NAME) !== gst.template.name ||
      typeof plan.vendor !== "string" || !plan.vendor.trim() || plan.vendor.length > 200 || /[\x00-\x1f]/.test(plan.vendor))
    throw new Error("GST supplier template changed; refresh Source Discovery.");
  const ledger = {"@_NAME": plan.vendor, "@_ACTION": "Create", NAME: plan.vendor, PARENT: "Sundry Creditors", ISBILLWISEON: "No"};
  const registration = list(template["LEDGSTREGDETAILS.LIST"]).filter(v => v && typeof v === "object")
    .sort((a, b) => gstScalar(b.APPLICABLEFROM).localeCompare(gstScalar(a.APPLICABLEFROM)))[0];
  if (registration) {
    const keys = ["APPLICABLEFROM", "GSTREGISTRATIONTYPE", "GSTIN", "PLACEOFSUPPLY"];
    if (keys.some(key => !(key in registration)) || gstScalar(registration.GSTREGISTRATIONTYPE) !== gst.registration_type ||
        Object.entries(registration).some(([key, value]) => key !== "#text" && !keys.includes(key) &&
          gstScalar(value) && gstScalar(value) !== "No"))
      throw new Error("Unsupported GST supplier template; create the ledger manually.");
    ledger["LEDGSTREGDETAILS.LIST"] = {APPLICABLEFROM: gst.applicable_from.replaceAll("-", ""),
      GSTREGISTRATIONTYPE: gst.registration_type, GSTIN: gst.gstin, PLACEOFSUPPLY: gst.place_of_supply};
    const mailing = list(template["LEDMAILINGDETAILS.LIST"]).find(v => v && typeof v === "object");
    if (!mailing || !mailing["ADDRESS.LIST"] || !("STATE" in mailing) || !("COUNTRY" in mailing) || !("PINCODE" in mailing))
      throw new Error("Unsupported supplier address template; create the ledger manually.");
    ledger["LEDMAILINGDETAILS.LIST"] = {APPLICABLEFROM: gst.applicable_from.replaceAll("-", ""), MAILINGNAME: plan.vendor,
      STATE: gst.state, COUNTRY: "India", PINCODE: gst.pincode, "ADDRESS.LIST": {"@_TYPE": "String", ADDRESS: gst.address}};
  } else {
    if (!gstScalar(template.PARTYGSTIN) || gstScalar(template.GSTREGISTRATIONTYPE) !== gst.registration_type ||
        !("PLACEOFSUPPLY" in template) || !("LEDSTATENAME" in template) || !("ADDRESS.LIST" in template))
      throw new Error("Unsupported GST supplier template; create the ledger manually.");
    Object.assign(ledger, {PARTYGSTIN: gst.gstin, GSTREGISTRATIONTYPE: gst.registration_type, LEDSTATENAME: gst.state,
      PLACEOFSUPPLY: gst.place_of_supply, COUNTRYNAME: "India", PINCODE: gst.pincode,
      "MAILINGNAME.LIST": {"@_TYPE": "String", MAILINGNAME: plan.vendor},
      "ADDRESS.LIST": {"@_TYPE": "String", ADDRESS: gst.address}});
  }
  return new XMLBuilder({ignoreAttributes: false}).build({LEDGER: ledger});
}

export function verifyGSTSupplier(master, expected) {
  if (!master || !gstScalar(master.GUID) || gstScalar(master.PARENT) !== "Sundry Creditors") return false;
  return [
    [["GSTIN", "PARTYGSTIN", "LEDGSTIN"], [expected.gstin]],
    [["GSTREGISTRATIONTYPE", "LEDGSTREGISTRATIONTYPE"], [expected.registration_type]],
    [["STATENAME", "LEDSTATENAME", "STATE", "LEDSTATE"], [expected.state]],
    [["PLACEOFSUPPLY", "LEDPLACEOFSUPPLY"], [expected.place_of_supply]],
    [["PINCODE", "LEDPINCODE"], [expected.pincode]], [["ADDRESS"], expected.address],
  ].every(([keys, values]) => {
    const actual = gstValues(master, keys), wanted = new Set(values);
    return actual.size === wanted.size && [...wanted].every(value => actual.has(value));
  });
}

/** Fixed, bounded full-ledger export, retaining nested GST fields stripped from references. */
export async function readGSTSupplier(plan, name, {request = fetch, identity} = {}) {
  if (typeof name !== "string" || !name.trim() || name.length > 200 || /[\x00-\x1f]/.test(name)) throw new Error("Invalid supplier identity.");
  await requireOpenCompany({company: plan.company, company_guid: plan.company_guid}, {port: plan.port, request});
  if (!identity) {
    const snapshot = await readTallyReferences({company: plan.company, port: plan.port, categories: ["company", "ledgers"]}, {request});
    const companies = snapshot.collections.find(c => c.category === "company")?.records ?? [];
    if (companies.length !== 1 || gstScalar(companies[0].GUID) !== plan.company_guid) throw new Error("Tally company changed.");
    const found = (snapshot.collections.find(c => c.category === "ledgers")?.records ?? [])
      .filter(master => gstScalar(master["@_NAME"] ?? master.NAME) === name);
    if (found.length !== 1) throw new Error("Supplier readback is missing or ambiguous.");
    identity = found[0];
  }
  const guid = gstScalar(identity.GUID);
  if (!/^[A-Za-z0-9-]{1,200}$/.test(guid)) throw new Error("Unsupported native supplier identity.");
  // Object exports on the live Prime build ignored SVCURRENTCOMPANY. A fixed
  // collection honors it; filter by a constrained native GUID, never by a
  // user-supplied name interpolated into TDL logic.
  const body = `<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>MinkopsGSTSupplier</ID></HEADER><BODY><DESC><STATICVARIABLES><SVCURRENTCOMPANY>${xml(plan.company)}</SVCURRENTCOMPANY><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="MinkopsGSTSupplier" ISMODIFY="No"><TYPE>Ledger</TYPE><FETCH>*,LEDGSTREGDETAILS.*,LEDMAILINGDETAILS.*,GSTDETAILS.*</FETCH><FILTERS>MinkopsGSTSupplierIdentity</FILTERS></COLLECTION><SYSTEM TYPE="Formulae" NAME="MinkopsGSTSupplierIdentity">$GUID = "${guid}"</SYSTEM></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>`;
  const response = await exchange(plan.company, plan.port, body, request);
  const found = [];
  const collect = node => { if (node && typeof node === "object") for (const [key, value] of Object.entries(node)) {
    if (key === "LEDGER") found.push(...list(value)); else if (value && typeof value === "object") collect(value);
  }};
  collect(response);
  const matching = found.filter(master => gstScalar(master["@_NAME"] ?? master.NAME) === name && gstScalar(master.GUID) === guid);
  if (matching.length !== 1 || !gstScalar(matching[0].GUID)) throw new Error("Supplier readback is missing or ambiguous.");
  return matching[0];
}
const populated = (v) =>
  typeof v === "object" && v !== null
    ? Object.values(v).some(populated)
    : v != null && String(v).trim() !== "";
function complexAllocations(v) {
  if (typeof v !== "object" || v === null) return false;
  return Object.entries(v).some(([key, value]) =>
    /^(?:ALLINVENTORYENTRIES|INVENTORYENTRIES|BILLALLOCATIONS|BANKALLOCATIONS|CATEGORYALLOCATIONS|COSTCATEGORYALLOCATIONS|COSTCENTREALLOCATIONS|INVENTORYALLOCATIONS)\.LIST$/.test(
      key,
    )
      ? populated(value)
      : complexAllocations(value),
  );
}
const cents = (v) => {
  const n = Number(v);
  if (
    !Number.isFinite(n) ||
    !Number.isSafeInteger(Math.round(n * 100)) ||
    Math.abs(n * 100 - Math.round(n * 100)) > 0.00001
  )
    throw new Error("Invalid money value.");
  return Math.round(n * 100);
};

async function exchange(company, port, body, request) {
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

export { exchange as tallyExchange };

/** Vouchers that may record a bill: every purchase-family type, plus Journal
 * types (a bill booked as a Journal must never be entered again). */
export async function readTallyBills(
  { company, port = 9000 },
  { request = fetch, types = LEGACY_TYPES } = {},
) {
  const body = `<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>MinkopsBills</ID></HEADER><BODY><DESC><STATICVARIABLES><SVCURRENTCOMPANY>${xml(company)}</SVCURRENTCOMPANY><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="MinkopsBills"><TYPE>Voucher</TYPE><FETCH>MasterID,GUID,AlterID,Date,Reference,PartyLedgerName,VoucherTypeName,IsInvoice,AllLedgerEntries.*,LedgerEntries.*,AllInventoryEntries.*,InventoryEntries.*</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>`;
  const reply = (await exchange(company, port, body, request)).ENVELOPE;
  if (
    text(reply?.HEADER?.STATUS) !== "1" ||
    !Object.hasOwn(reply?.BODY?.DATA || {}, "COLLECTION")
  )
    throw new Error("Tally did not confirm the voucher collection.");
  const vouchers = list(reply.BODY.DATA.COLLECTION?.VOUCHER);
  if (vouchers.length > 10000)
    throw new Error("Tally voucher scope exceeds 10,000 records.");
  const classify = (v) => {
    const name = String(text(v.VOUCHERTYPENAME) ?? "").trim().toLowerCase();
    return types.purchase.has(name) ? "purchase" : types.journal.has(name) ? "journal" : null;
  };
  return vouchers
    .filter(classify)
    .map((v) => ({
      voucher_type: String(text(v.VOUCHERTYPENAME)).trim(),
      [kind]: classify(v),
      master_id: String(text(v.MASTERID)),
      guid: String(text(v.GUID)),
      date: String(text(v.DATE)),
      invoice_number: String(text(v.REFERENCE)),
      vendor: String(text(v.PARTYLEDGERNAME)),
      entries: list(v["ALLLEDGERENTRIES.LIST"] || v["LEDGERENTRIES.LIST"]).map(
        (e) => ({
          ledger: String(text(e.LEDGERNAME)),
          amount: cents(text(e.AMOUNT)),
        }),
      ),
      fingerprint: digest(v),
      [unsupported]: complexAllocations(v) || text(v.ISINVOICE) === "Yes",
    }));
}

function taxLines(plan) {
  const {data} = plan;
  if (plan.tax_allocations === undefined)
    return cents(data.tax) ? [{ledger:data.tax_ledger,amount:cents(data.tax)}] : [];
  if (![2, 3].includes(plan.format_version) || !plan.references?.company_guid || data.tax_ledger != null
      || !Array.isArray(plan.tax_allocations) || !plan.tax_allocations.length || plan.tax_allocations.length > 8)
    throw new Error("Unsupported split tax plan; refresh the approved mapping.");
  const lines = plan.tax_allocations.map(line => {
    if (!line || Object.keys(line).sort().join(',') !== 'amount,ledger'
        || typeof line.ledger !== 'string' || !line.ledger.trim() || line.ledger.length > 200
        || /[\x00-\x1f]/.test(line.ledger) || typeof line.amount !== 'number' || cents(line.amount) <= 0)
      throw new Error("Invalid tax allocation.");
    return {ledger:line.ledger,amount:cents(line.amount)};
  });
  const sum = lines.reduce((n,line)=>n+line.amount,0);
  if (!Number.isSafeInteger(sum) || sum !== cents(data.tax)
      || new Set(lines.map(line=>line.ledger)).size !== lines.length
      || lines.some(line=>[data.vendor,data.purchase_ledger].includes(line.ledger)))
    throw new Error("Tax allocations must balance exactly and use distinct ledgers.");
  return lines;
}

function equal(record, data, taxes) {
  const expected = [
    { ledger: data.vendor, amount: cents(data.total) },
    { ledger: data.purchase_ledger, amount: -cents(data.subtotal) },
  ];
  expected.push(...taxes.map(line=>({ledger:line.ledger,amount:-line.amount})));
  const sort = (v) =>
    v.toSorted(
      (a, b) => a.ledger.localeCompare(b.ledger) || a.amount - b.amount,
    );
  return (
    record.date === data.date.replaceAll("-", "") &&
    digest(sort(record.entries)) === digest(sort(expected))
  );
}

export async function commitTallyBill(plan, { request = fetch, reconciliationOnly = false } = {}) {
  const { data, company, port = 9000, remote_id, operation, expected } = plan;
  const taxes = taxLines(plan);
  if (
    !/^[a-f0-9-]{36}$/.test(remote_id) ||
    !["append", "update"].includes(operation) ||
    !/^\d{4}-\d{2}-\d{2}$/.test(data.date) ||
    !data.invoice_number?.trim() ||
    !data.vendor?.trim() ||
    data.cost_code
  )
    throw new Error("Unsupported bill plan.");
  if (
    cents(data.subtotal) < 0 ||
    cents(data.tax) < 0 ||
    cents(data.total) <= 0 ||
    cents(data.subtotal) + cents(data.tax) !== cents(data.total)
  )
    throw new Error("Unbalanced bill.");
  let types = LEGACY_TYPES,
    writeType = "Purchase";
  if (plan.references) {
    const snapshot = await readTallyReferences(
      {
        company,
        port,
        categories: ["company", "ledgers", "voucher_types"],
      },
      { request },
    );
    if (snapshot.collections.some((c) => c.status !== "ready"))
      throw new Error("Required Tally references could not be rechecked.");
    const companyRecord = snapshot.collections.find(
      (c) => c.category === "company",
    ).records[0];
    if (
      plan.references.company_guid &&
      companyRecord.GUID !== plan.references.company_guid
    )
      throw actionable("The Tally company identity changed. Refresh Source Discovery, then start a new run.");
    const ledgers = snapshot.collections.find(
      (c) => c.category === "ledgers",
    ).records;
    for (const name of [
      data.vendor,
      data.purchase_ledger,
      ...taxes.map(line=>line.ledger),
    ]) {
      const actual = ledgers.filter(
        (r) => text(r["@_NAME"] ?? r.NAME) === name,
      );
      const pinned = plan.references.ledgers[name];
      if (
        actual.length !== 1 ||
        !pinned ||
        ["GUID", "PARENT", "ALTERID"].some(
          (k) =>
            pinned[k] != null && referenceDigest(k, actual[0][k]) !== referenceDigest(k, pinned[k]),
        )
      )
        throw actionable(
          "A selected ledger changed since discovery. Refresh and review its mapping before saving.",
        );
    }
    // The run's pinned type must still be exactly one active purchase type
    // with the same GUID. Plans pinned before voucher types used "Purchase".
    const records = snapshot.collections.find((c) => c.category === "voucher_types").records;
    types = purchaseVoucherTypes(records);
    const pinned = plan.references.voucher_type ?? { NAME: "Purchase" };
    const key = String(pinned.NAME ?? "").trim().toLowerCase();
    const live = records.filter((r) => typeName(r).toLowerCase() === key);
    if (
      live.length !== 1 ||
      (pinned.GUID != null && text(live[0].GUID) !== pinned.GUID) ||
      !types.purchase.has(key) ||
      !types.active.has(key)
    )
      throw actionable(
        `The purchase voucher type ${String(pinned.NAME).slice(0, 80)} changed in Tally since discovery. Refresh Source Discovery, then start a new run.`,
      );
    writeType = typeName(live[0]);
  }
  const match = (v) =>
    norm(v.vendor) === norm(data.vendor) &&
    norm(v.invoice_number) === norm(data.invoice_number) &&
    year(v.date) === year(data.date.replaceAll("-", ""));
  const matches = (await readTallyBills(plan, { request, types })).filter(match);
  const journal = matches.find((v) => v[kind] === "journal");
  if (journal)
    return {
      outcome: "attention",
      message: `Tally already records this bill as a ${journal.voucher_type.slice(0, 80)} voucher. Review it in Tally; Minkops will not add another.`,
    };
  const records = matches.filter((v) => v[kind] === "purchase");
  if (records.length > 1)
    return {
      outcome: "attention",
      message:
        "Multiple vouchers share this bill identity. Review Tally before retrying.",
    };
  const current = records[0];
  if (current && equal(current, data, taxes)) return { outcome: "duplicate", current };
  if (
    current &&
    (operation !== "update" || expected?.fingerprint !== current.fingerprint)
  )
    return { outcome: "correction", current };
  if (!current && operation === "update")
    return {
      outcome: "attention",
      message: "The voucher selected for correction no longer exists.",
    };
  if (
    current &&
    (!/^\d+$/.test(current.master_id) ||
      !/^[a-f0-9-]{36}(?:-[a-f0-9]{8})?$/.test(current.guid))
  )
    return {
      outcome: "attention",
      message: "Existing voucher has no supported stable identifier.",
    };
  // The fixed accounting plan cannot preserve inventory, payment or cost/bill
  // allocations. Leave those corrections untouched rather than flatten them.
  if (
    current &&
    (current[unsupported] ||
      current.entries.some(
        (e) =>
          ![data.vendor, data.purchase_ledger, ...taxes.map(line=>line.ledger)].includes(
            e.ledger,
          ),
      ))
  )
    return {
      outcome: "attention",
      message:
        "Existing voucher has allocations this bill mapping cannot preserve. Correct it in Tally, then reconcile.",
    };
  if (reconciliationOnly) return {outcome:"attention",message:"Tally did not confirm the write, and the approved version is not present. Review Tally, then use Retry save; it checks Tally again before importing."};
  const entry = (ledger, amount) =>
    `<ALLLEDGERENTRIES.LIST><LEDGERNAME>${xml(ledger)}</LEDGERNAME><ISDEEMEDPOSITIVE>${amount < 0 ? "Yes" : "No"}</ISDEEMEDPOSITIVE><AMOUNT>${(amount / 100).toFixed(2)}</AMOUNT></ALLLEDGERENTRIES.LIST>`;
  const guid = current?.guid || remote_id;
  // A correction keeps the existing voucher's own type; a new voucher uses the run's.
  const vchType = current?.voucher_type ?? writeType;
  const attributes = current
    ? `DATE="${xml(current.date)}" TAGNAME="MASTER ID" TAGVALUE="${xml(current.master_id)}" Action="Alter"`
    : `REMOTEID="${xml(guid)}" Action="Create"`;
  const body = `<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME><STATICVARIABLES><SVCURRENTCOMPANY>${xml(company)}</SVCURRENTCOMPANY></STATICVARIABLES></REQUESTDESC><REQUESTDATA><TALLYMESSAGE><VOUCHER ${attributes} VCHTYPE="${xml(vchType)}" OBJVIEW="Accounting Voucher View"><GUID>${xml(guid)}</GUID><DATE>${data.date.replaceAll("-", "")}</DATE><VOUCHERTYPENAME>${xml(vchType)}</VOUCHERTYPENAME><REFERENCE>${xml(data.invoice_number)}</REFERENCE><PARTYLEDGERNAME>${xml(data.vendor)}</PARTYLEDGERNAME><PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW><ISINVOICE>No</ISINVOICE><NARRATION>Minkops reviewed bill ${xml(data.invoice_number)}</NARRATION>${entry(data.vendor, cents(data.total))}${entry(data.purchase_ledger, -cents(data.subtotal))}${taxes.map(line=>entry(line.ledger,-line.amount)).join('')}</VOUCHER></TALLYMESSAGE></REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>`;
  const reply = await exchange(company, port, body, request);
  const result = reply.RESPONSE || reply.ENVELOPE?.BODY?.DATA;
  if (
    !result ||
    text(result.ERRORS) !== "0" ||
    Number(text(result.CREATED) || 0) + Number(text(result.ALTERED) || 0) !== 1
  )
    throw new Error(
      "Tally did not confirm exactly one write. Reconcile before retrying.",
    );
  if (current && Number(text(result.CREATED) || 0) !== 0)
    throw new Error(
      "Tally created a voucher instead of applying the approved correction. Review the company before retrying.",
    );
  const saved = (await readTallyBills(plan, { request, types })).filter(
    (v) => v[kind] === "purchase" && match(v),
  );
  // Tally can assign its own company GUID/master suffix on creation. Its
  // business identity and observed ID are authoritative, not the supplied UUID.
  if (
    saved.length !== 1 ||
    !equal(saved[0], data, taxes) ||
    saved[0].voucher_type.toLowerCase() !== vchType.toLowerCase() ||
    (current && saved[0].guid !== current.guid)
  )
    throw new Error(
      "Tally readback differs from the approved bill. Reconcile before retrying.",
    );
  return { outcome: "saved", current: saved[0] };
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

/** One approved bill, as the companion saves it: the company must be open
 * (and be the discovered one), then commit; an unacknowledged write is
 * reconciled once and never resent. Session problems become holds that a
 * Retry save clears once Tally is ready. */
export async function saveTallyBill(plan, { request = fetch, sessionRequest = fetch, processes, pc, wait, diagnose = () => {} } = {}) {
  const hold = (error) => {
    // Session checks bypass the transport, so record their evidence here.
    diagnose({ state: error.tallyState, cause: error.detail?.cause, running: error.detail?.running, error: error.message });
    return { outcome: "attention", hold: error.tallyState, message: error.message };
  };
  try {
    await requireOpenCompany(
      { company: plan.company, company_guid: plan.references?.company_guid },
      { port: plan.port ?? 9000, request: sessionRequest, processes, pc, wait },
    );
    return await commitTallyBill(plan, { request });
  } catch (error) {
    if (error instanceof TallyUnavailable) return hold(error);
    if (!error.tallyAmbiguous) throw error;
    let reconciled;
    try {
      reconciled = await commitTallyBill(plan, { request, reconciliationOnly: true });
    } catch (second) {
      if (second instanceof TallyUnavailable) return hold(second);
      throw second;
    }
    if (reconciled.outcome === "attention" && error.tallyLineError)
      return { ...reconciled, hold: "rejected", message: classifyRejection(error.tallyLineError).message };
    return reconciled;
  }
}
