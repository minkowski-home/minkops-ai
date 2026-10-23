/** Create the party ledger a person approved (plan protocol 8): a bill's new supplier,
 * or the other side of a bank row, in Tally's own terms, read back for the server to verify.
 * Raw XML/TDL, endpoints and actions never come from the renderer. */
import { XMLBuilder } from "fast-xml-parser";
import { tallyExchange as exchange } from "./voucher.js";
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
const scalar = value => String(text(value) ?? "").trim();
const plain = (v, limit) => typeof v === "string" && v.trim() !== "" && v.length <= limit && !/[\x00-\x1f]/.test(v);
const ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";

/** The ledger plan the server approved, checked again here: nothing it does not state is written. */
export function validLedgerPlan(plan) {
  const ledger = plan?.ledger, mailing = ledger?.mailing, gst = ledger?.gst;
  const date = v => typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v);
  if (plan?.kind !== "ledger" || plan.protocol !== 8 || !["dated", "legacy"].includes(plan.shape)
      || !plain(plan.company, 200) || !plain(ledger?.name, 200) || !plain(ledger?.under, 200)
      || typeof ledger.billwise !== "boolean" || !date(ledger.applicable_from)
      || !(ledger.credit_period === null || (Number.isInteger(ledger.credit_period) && ledger.credit_period >= 1
        && ledger.credit_period <= 365 && ledger.billwise)))
    throw new Error("Invalid approved ledger.");
  if (mailing !== null && (!mailing || !Array.isArray(mailing.address) || mailing.address.length > 4
      || mailing.address.some(line => !plain(line, 250)) || !(mailing.state === null || plain(mailing.state, 100))
      || mailing.country !== "India" || !(mailing.pincode === null || /^[1-9][0-9]{5}$/.test(mailing.pincode))))
    throw new Error("Invalid approved mailing details.");
  if (gst !== null) {
    const number = gst?.gstin;
    if (!gst || !["Regular", "Composition"].includes(gst.registration_type) || !plain(gst.state, 100) || !date(gst.applicable_from)
        || typeof number !== "string" || !/^[0-9]{2}[A-Z]{3}[ABCFGHJLPT][A-Z][0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/.test(number))
      throw new Error("Invalid approved GST details.");
    let sum = 0;
    for (let index = 0; index < 14; index++) {
      const product = ALPHABET.indexOf(number[index]) * (index % 2 ? 2 : 1);
      sum += Math.floor(product / 36) + product % 36;
    }
    if (number[14] !== ALPHABET[(36 - sum % 36) % 36]) throw new Error("Invalid GSTIN check character.");
  }
}

/** The ledger is imported only when no ledger has its name, so a retry after a lost
 * acknowledgement reads the one it created instead of creating a second. */
export async function createLedger(plan, {request = fetch} = {}) {
  validLedgerPlan(plan);
  const name = plan.ledger.name;
  const read = async () => {
    const snapshot = await readTallyReferences({company: plan.company, port: plan.port, categories: ["company", "ledgers"]}, {request});
    const companies = snapshot.collections.find(c => c.category === "company")?.records ?? [];
    if (companies.length !== 1 || text(companies[0].GUID) !== plan.company_guid) throw new Error("Tally company changed.");
    return (snapshot.collections.find(c => c.category === "ledgers")?.records ?? [])
      .filter(m => norm(text(m["@_NAME"] ?? m.NAME)) === norm(name));
  };
  let found = await read();
  if (found.length > 1) throw new Error("Ledger identity is ambiguous.");
  if (!found.length) {
    // A closed or replaced company must never fall back to Tally's selected
    // company before this irreversible master import.
    await requireOpenCompany({company: plan.company, company_guid: plan.company_guid}, {port: plan.port, request});
    const body = `<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>All Masters</REPORTNAME><STATICVARIABLES><SVCURRENTCOMPANY>${xml(plan.company)}</SVCURRENTCOMPANY></STATICVARIABLES></REQUESTDESC><REQUESTDATA><TALLYMESSAGE>${buildLedger(plan)}</TALLYMESSAGE></REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>`;
    // Losing an import acknowledgement never permits another import in this
    // attempt. The next explicit action starts with the same exact master read.
    await exchange(plan.company, plan.port, body, request);
    found = await read();
    if (found.length !== 1) throw new Error("Ledger readback is missing or ambiguous.");
  }
  // Read back under the name Tally keeps, which may differ from the approved one in case alone.
  const kept = scalar(found[0]["@_NAME"] ?? found[0].NAME);
  return {company_guid: plan.company_guid, ledger: await readLedger(plan, kept, {request, identity: found[0]})};
}

/** Exactly the approved fields, in the shape this company's Tally keeps them: its dated
 * registration and mailing details, or the older fields. No identity, balance or banking
 * state is ever written. */
export function buildLedger(plan) {
  validLedgerPlan(plan);
  const {name, under, billwise, credit_period: period, mailing, gst, applicable_from: from} = plan.ledger;
  const ledger = {"@_NAME": name, "@_ACTION": "Create", NAME: name, PARENT: under, ISBILLWISEON: billwise ? "Yes" : "No"};
  if (period) ledger.BILLCREDITPERIOD = `${period} Days`;
  const address = mailing && {"@_TYPE": "String", ADDRESS: mailing.address};
  if (plan.shape === "dated") {
    if (gst) ledger["LEDGSTREGDETAILS.LIST"] = {APPLICABLEFROM: gst.applicable_from.replaceAll("-", ""),
      GSTREGISTRATIONTYPE: gst.registration_type, GSTIN: gst.gstin, PLACEOFSUPPLY: gst.state};
    if (mailing) ledger["LEDMAILINGDETAILS.LIST"] = {APPLICABLEFROM: from.replaceAll("-", ""), MAILINGNAME: name,
      ...(mailing.state ? {STATE: mailing.state} : {}), COUNTRY: mailing.country,
      ...(mailing.pincode ? {PINCODE: mailing.pincode} : {}), ...(mailing.address.length ? {"ADDRESS.LIST": address} : {})};
  } else {
    if (gst) Object.assign(ledger, {PARTYGSTIN: gst.gstin, GSTREGISTRATIONTYPE: gst.registration_type, PLACEOFSUPPLY: gst.state});
    if (mailing) Object.assign(ledger, {...(mailing.state ? {LEDSTATENAME: mailing.state} : {}), COUNTRYNAME: mailing.country,
      ...(mailing.pincode ? {PINCODE: mailing.pincode} : {}), "MAILINGNAME.LIST": {"@_TYPE": "String", MAILINGNAME: name},
      ...(mailing.address.length ? {"ADDRESS.LIST": address} : {})});
  }
  return new XMLBuilder({ignoreAttributes: false}).build({LEDGER: ledger});
}

/** Fixed, bounded full-ledger export, retaining nested GST, mailing and credit fields stripped from references. */
export async function readLedger(plan, name, {request = fetch, identity} = {}) {
  if (typeof name !== "string" || !name.trim() || name.length > 200 || /[\x00-\x1f]/.test(name)) throw new Error("Invalid ledger identity.");
  await requireOpenCompany({company: plan.company, company_guid: plan.company_guid}, {port: plan.port, request});
  if (!identity) {
    const snapshot = await readTallyReferences({company: plan.company, port: plan.port, categories: ["company", "ledgers"]}, {request});
    const companies = snapshot.collections.find(c => c.category === "company")?.records ?? [];
    if (companies.length !== 1 || scalar(companies[0].GUID) !== plan.company_guid) throw new Error("Tally company changed.");
    const found = (snapshot.collections.find(c => c.category === "ledgers")?.records ?? [])
      .filter(master => scalar(master["@_NAME"] ?? master.NAME) === name);
    if (found.length !== 1) throw new Error("Ledger readback is missing or ambiguous.");
    identity = found[0];
  }
  const guid = scalar(identity.GUID);
  if (!/^[A-Za-z0-9-]{1,200}$/.test(guid)) throw new Error("Unsupported native ledger identity.");
  // Object exports on the live Prime build ignored SVCURRENTCOMPANY. A fixed
  // collection honors it; filter by a constrained native GUID, never by a
  // user-supplied name interpolated into TDL logic.
  const body = `<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>MinkopsLedger</ID></HEADER><BODY><DESC><STATICVARIABLES><SVCURRENTCOMPANY>${xml(plan.company)}</SVCURRENTCOMPANY><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="MinkopsLedger" ISMODIFY="No"><TYPE>Ledger</TYPE><FETCH>*,LEDGSTREGDETAILS.*,LEDMAILINGDETAILS.*,GSTDETAILS.*</FETCH><FILTERS>MinkopsLedgerIdentity</FILTERS></COLLECTION><SYSTEM TYPE="Formulae" NAME="MinkopsLedgerIdentity">$GUID = "${guid}"</SYSTEM></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>`;
  const response = await exchange(plan.company, plan.port, body, request);
  const found = [];
  const collect = node => { if (node && typeof node === "object") for (const [key, value] of Object.entries(node)) {
    if (key === "LEDGER") found.push(...list(value)); else if (value && typeof value === "object") collect(value);
  }};
  collect(response);
  const matching = found.filter(master => scalar(master["@_NAME"] ?? master.NAME) === name && scalar(master.GUID) === guid);
  if (matching.length !== 1 || !scalar(matching[0].GUID)) throw new Error("Ledger readback is missing or ambiguous.");
  return matching[0];
}
