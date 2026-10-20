/** Fixed, bounded identity reads for destination verification and legacy pinned writes. */
import { XMLParser, XMLValidator } from "fast-xml-parser";
import { boundedText, readOpenCompanies, TallyUnavailable } from "./tally-session.js";

export const TALLY_COLLECTIONS = Object.freeze({
  company: ["Company", "COMPANY"],
  groups: ["Group", "GROUP"],
  ledgers: ["Ledger", "LEDGER"],
  voucher_types: ["VoucherType", "VOUCHERTYPE"],
  stock_items: ["StockItem", "STOCKITEM"],
  stock_groups: ["StockGroup", "STOCKGROUP"],
  units: ["Unit", "UNIT"],
  godowns: ["Godown", "GODOWN"],
  cost_centres: ["CostCentre", "COSTCENTRE"],
  cost_categories: ["CostCategory", "COSTCATEGORY"],
  currencies: ["Currency", "CURRENCY"],
});
const EXTRA_FIELDS = {
  company: ',IsCostCentresOn', ledgers: ',IsCostCentresOn',
  voucher_types: ',IsActive', cost_centres: ',Category',
};
const escapeXml = (s) =>
  s.replace(
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
function tallyReferenceScalar(value) {
  if (typeof value === "string") return value;
  // Tally annotates scalar XML elements with TYPE attributes. Keep their text
  // exact (including identifier leading zeroes), and reject nested records.
  if (
    value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.keys(value).every(
      (key) => key === "#text" || key.startsWith("@_"),
    ) &&
    (!Object.hasOwn(value, "#text") || typeof value["#text"] === "string")
  )
    return value["#text"] ?? "";
  throw new Error("Tally reference field is not a scalar.");
}

export async function readTallyReferences(
  config,
  { request = fetch, onProgress = async () => {} } = {},
) {
  const { company, port = 9000, categories } = config;
  if (
    typeof company !== "string" ||
    !company.trim() ||
    company.length > 200 ||
    /[\x00-\x1f]/.test(company) ||
    !Array.isArray(categories) ||
    !categories.length ||
    categories.some((c) => !Object.hasOwn(TALLY_COLLECTIONS, c)) ||
    new Set(categories).size !== categories.length
  )
    throw new Error("Invalid Tally discovery configuration.");
  const open = await readOpenCompanies({ port, request });
  if (!open.some((c) => c.company === company))
    throw new TallyUnavailable(
      "company_not_open",
      `${company} is not open in Tally. Open it in Tally, then try again.`,
    );
  const collections = [];
  for (const category of categories) {
    await onProgress(category, "reading");
    const [type, tag] = TALLY_COLLECTIONS[category];
    try {
      const xml = `<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>MinkopsDiscovery</ID></HEADER><BODY><DESC><STATICVARIABLES><SVCURRENTCOMPANY>${escapeXml(company)}</SVCURRENTCOMPANY><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="MinkopsDiscovery" ISMODIFY="No"><TYPE>${type}</TYPE><FETCH>Name,GUID,Parent,AlterID${EXTRA_FIELDS[category] ?? ''}</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>`;
      const response = await request(`http://127.0.0.1:${port}`, {
        method: "POST",
        body: xml,
        headers: { "Content-Type": "text/xml; charset=utf-8" },
        redirect: "error",
        signal: AbortSignal.timeout(15000),
      });
      const text = await boundedText(response, 3_000_000);
      if (
        /<!DOCTYPE|<!ENTITY|<LINEERROR\b/i.test(text) ||
        XMLValidator.validate(text) !== true
      )
        throw new Error("Tally returned an invalid or unsupported collection.");
      const envelope = new XMLParser({
        ignoreAttributes: false,
        parseTagValue: false,
        parseAttributeValue: false,
        trimValues: true,
      }).parse(text).ENVELOPE;
      if (
        String(envelope?.HEADER?.STATUS) !== "1" ||
        !envelope.BODY?.DATA ||
        !Object.hasOwn(envelope.BODY.DATA, "COLLECTION")
      )
        throw new Error("Tally did not confirm this collection.");
      const node = envelope.BODY.DATA.COLLECTION?.[tag];
      let records = node ? (Array.isArray(node) ? node : [node]) : [];
      if (records.length > 10000)
        throw new Error(
          "Collection exceeds 10,000 records; narrow your selected categories.",
        );
      records = records.map((r) =>
        Object.fromEntries(
          Object.entries(r)
            .filter(([key]) =>
              // RESERVEDNAME and ISACTIVE classify voucher types (see tally.js).
              ["@_NAME", "NAME", "GUID", "PARENT", "ALTERID", "@_RESERVEDNAME", "ISACTIVE", "ISCOSTCENTRESON", "CATEGORY"].includes(key),
            )
            .map(([key, value]) => [key, tallyReferenceScalar(value)]),
        ),
      );
      if (category === "company")
        records = records.filter(
          (r) => r["@_NAME"] === company || r.NAME === company,
        );
      if (category === "company" && !records.length)
        throw new Error("Selected company details were not returned.");
      const fields = new Set();
      const walk = (v, p = "") => {
        if (v && typeof v === "object")
          for (const [k, value] of Object.entries(v)) {
            const key = p ? `${p}.${k}` : k;
            fields.add(key);
            walk(value, key);
          }
      };
      records.forEach((r) => walk(r));
      collections.push({
        category,
        status: "ready",
        count: records.length,
        fields: [...fields].sort(),
        records,
      });
      await onProgress(category, "ready");
    } catch {
      collections.push({
        category,
        status: "unavailable",
        error:
          "Could not read this Tally collection. Check company access and selected scope, then refresh.",
      });
      await onProgress(category, "unavailable");
    }
  }
  return { company, port, collections };
}
