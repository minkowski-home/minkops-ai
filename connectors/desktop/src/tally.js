/** Bounded Tally attention operations: observe a bill with the voucher
 * writer's reader, and create a verified supplier master on explicit consent.
 * Raw XML/TDL, endpoints and actions never come from the renderer. */
import { XMLBuilder } from "fast-xml-parser";
import { tallyExchange as exchange, readVouchers, voucherFamilies, documentMatches, observedVoucher } from "./voucher.js";
import { readTallyReferences } from "./tally-references.js";
import { requireOpenCompany } from "./tally-session.js";

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
/** A failure with one user action, safe to show verbatim (see worker.js). */
const actionable = (message) => Object.assign(new Error(message), { userSafe: true });

/** Fixed native attention operations. Renderer cannot supply XML or endpoints. */
export async function inspectTallyAttention(plan, {request = fetch, createSupplier = false} = {}) {
  const snapshot = await readTallyReferences({company: plan.company, port: plan.port, categories: ["company", "ledgers", "voucher_types"]}, {request});
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
  let current = null;
  if (plan.document) {
    // The same window, number fields and reader as the voucher writer, so a
    // refresh fingerprint is comparable with the saved one.
    const {window, number_fields, families} = plan.document;
    const live = voucherFamilies(snapshot.collections.find(c => c.category === "voucher_types")?.records ?? []);
    const familyOf = v => live.family.get(v.voucher_type.toLowerCase()) ?? null;
    const found = (await readVouchers({company: plan.company, port: plan.port, window}, {request})).filter(v =>
      families.includes(familyOf(v)) && documentMatches(v, {party_ledger: plan.vendor, number: plan.invoice_number, number_fields}));
    current = found.length === 1 ? observedVoucher(found[0], familyOf(found[0])) : null;
  }
  return {company_guid: plan.company_guid, ledgers, current, ...(supplier ? {supplier} : {})};
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
