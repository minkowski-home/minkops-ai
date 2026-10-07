/** Bounded Purchase-voucher adapter. Read-before-write and full readback are
 * mandatory; raw XML/TDL, endpoints and actions never come from the renderer. */
import { createHash } from "node:crypto";
import { XMLParser, XMLValidator } from "fast-xml-parser";
import { boundedText } from "./index.js";
import { discoverTally } from "./discovery.js";

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
const unsupported = Symbol("unsupported allocations");
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

export async function readTallyBills(
  { company, port = 9000 },
  { request = fetch } = {},
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
  return vouchers
    .filter((v) => text(v.VOUCHERTYPENAME) === "Purchase")
    .map((v) => ({
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

function equal(record, data) {
  const expected = [
    { ledger: data.vendor, amount: cents(data.total) },
    { ledger: data.purchase_ledger, amount: -cents(data.subtotal) },
  ];
  if (cents(data.tax))
    expected.push({ ledger: data.tax_ledger, amount: -cents(data.tax) });
  const sort = (v) =>
    v.toSorted(
      (a, b) => a.ledger.localeCompare(b.ledger) || a.amount - b.amount,
    );
  return (
    record.date === data.date.replaceAll("-", "") &&
    digest(sort(record.entries)) === digest(sort(expected))
  );
}

export async function commitTallyBill(plan, { request = fetch } = {}) {
  const { data, company, port = 9000, remote_id, operation, expected } = plan;
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
  if (plan.references) {
    const snapshot = await discoverTally(
      {
        company,
        port,
        categories: ["company", "ledgers"],
        depth: "reference_data",
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
      throw new Error("The Tally company identity changed. Refresh discovery.");
    const ledgers = snapshot.collections.find(
      (c) => c.category === "ledgers",
    ).records;
    for (const name of [
      data.vendor,
      data.purchase_ledger,
      ...(data.tax ? [data.tax_ledger] : []),
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
            pinned[k] != null && digest(actual[0][k]) !== digest(pinned[k]),
        )
      )
        throw new Error(
          "A selected ledger changed since discovery. Refresh and review its mapping before saving.",
        );
    }
  }
  const match = (v) =>
    norm(v.vendor) === norm(data.vendor) &&
    norm(v.invoice_number) === norm(data.invoice_number) &&
    year(v.date) === year(data.date.replaceAll("-", ""));
  const records = (await readTallyBills(plan, { request })).filter(match);
  if (records.length > 1)
    return {
      outcome: "attention",
      message:
        "Multiple vouchers share this bill identity. Review Tally before retrying.",
    };
  const current = records[0];
  if (current && equal(current, data)) return { outcome: "duplicate", current };
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
          ![data.vendor, data.purchase_ledger, data.tax_ledger].includes(
            e.ledger,
          ),
      ))
  )
    return {
      outcome: "attention",
      message:
        "Existing voucher has allocations this bill mapping cannot preserve. Correct it in Tally, then reconcile.",
    };
  const entry = (ledger, amount) =>
    `<ALLLEDGERENTRIES.LIST><LEDGERNAME>${xml(ledger)}</LEDGERNAME><ISDEEMEDPOSITIVE>${amount < 0 ? "Yes" : "No"}</ISDEEMEDPOSITIVE><AMOUNT>${(amount / 100).toFixed(2)}</AMOUNT></ALLLEDGERENTRIES.LIST>`;
  const guid = current?.guid || remote_id;
  const attributes = current
    ? `DATE="${xml(current.date)}" TAGNAME="MASTER ID" TAGVALUE="${xml(current.master_id)}" Action="Alter"`
    : `REMOTEID="${xml(guid)}" Action="Create"`;
  const body = `<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME><STATICVARIABLES><SVCURRENTCOMPANY>${xml(company)}</SVCURRENTCOMPANY></STATICVARIABLES></REQUESTDESC><REQUESTDATA><TALLYMESSAGE><VOUCHER ${attributes} VCHTYPE="Purchase" OBJVIEW="Accounting Voucher View"><GUID>${xml(guid)}</GUID><DATE>${data.date.replaceAll("-", "")}</DATE><VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME><REFERENCE>${xml(data.invoice_number)}</REFERENCE><PARTYLEDGERNAME>${xml(data.vendor)}</PARTYLEDGERNAME><PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW><ISINVOICE>No</ISINVOICE><NARRATION>Minkops reviewed mock bill ${xml(data.invoice_number)}</NARRATION>${entry(data.vendor, cents(data.total))}${entry(data.purchase_ledger, -cents(data.subtotal))}${cents(data.tax) ? entry(data.tax_ledger, -cents(data.tax)) : ""}</VOUCHER></TALLYMESSAGE></REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>`;
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
  const saved = (await readTallyBills(plan, { request })).filter(match);
  // Tally can assign its own company GUID/master suffix on creation. Its
  // business identity and observed ID are authoritative, not the supplied UUID.
  if (
    saved.length !== 1 ||
    !equal(saved[0], data) ||
    (current && saved[0].guid !== current.guid)
  )
    throw new Error(
      "Tally readback differs from the approved bill. Reconcile before retrying.",
    );
  return { outcome: "saved", current: saved[0] };
}
