/** Read-only local structure collection. Never executes workbook formulas or TDL from callers. */
import ExcelJS from "exceljs";
import yauzl from "yauzl";
import JSZip from "jszip";
import { posix } from "node:path";
import { XMLParser, XMLBuilder, XMLValidator } from "fast-xml-parser";
import { tallyProbe, boundedText } from "./index.js";
import { tallySchema } from "./tally-schema.js";

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
const scalar = (v) => {
  if (v == null) return null;
  if (v instanceof Date) return v.toISOString();
  if (typeof v !== "object") return v;
  if ("formula" in v) return { formula: v.formula, result: scalar(v.result) };
  if ("richText" in v) return v.richText.map((t) => t.text).join("");
  if ("text" in v) return v.text;
  if ("error" in v) return { error: v.error };
  return null;
};

function tallyReferenceScalar(value) {
  if (typeof value === "string") return value;
  // Tally annotates scalar XML elements with TYPE attributes. Keep their text
  // exact (including identifier leading zeroes), and reject nested records.
  if (value && typeof value === "object" && !Array.isArray(value) &&
      Object.keys(value).every((key) => key === "#text" || key.startsWith("@_")) &&
      (!Object.hasOwn(value, "#text") || typeof value["#text"] === "string"))
    return value["#text"] ?? "";
  throw new Error("Tally reference field is not a scalar.");
}

async function excelReaderBytes(bytes) {
  // OPC permits package-absolute relationship targets. ExcelJS 4.4 only resolves
  // relative table targets (upstream #1468). Normalize the reader's in-memory
  // copy; hashes, uploads and approved writes keep the original bytes.
  const zip = await JSZip.loadAsync(bytes);
  const parser = new XMLParser({
    ignoreAttributes: false,
    parseAttributeValue: false,
  });
  const builder = new XMLBuilder({ ignoreAttributes: false });
  let changed = false;
  for (const [name, entry] of Object.entries(zip.files)) {
    if (entry.dir || !name.endsWith(".rels") || !name.includes("/_rels/"))
      continue;
    const xml = await entry.async("string");
    if (/<!DOCTYPE|<!ENTITY/i.test(xml) || XMLValidator.validate(xml) !== true)
      throw new Error("Workbook contains invalid relationships.");
    const doc = parser.parse(xml);
    const value = doc.Relationships?.Relationship;
    const relationships = value ? (Array.isArray(value) ? value : [value]) : [];
    let modified = false;
    for (const rel of relationships) {
      const target = rel["@_Target"];
      if (
        rel["@_TargetMode"] === "External" ||
        !rel["@_Type"]?.endsWith("/table") ||
        typeof target !== "string" ||
        !target.startsWith("/")
      )
        continue;
      const sourceDirectory = posix.dirname(
        name.replace("/_rels/", "/").slice(0, -5),
      );
      rel["@_Target"] = posix.relative(sourceDirectory, target.slice(1));
      modified = true;
    }
    if (modified) {
      zip.file(name, builder.build(doc));
      changed = true;
    }
  }
  return changed ? zip.generateAsync({ type: "nodebuffer" }) : bytes;
}

export async function inspectExcel(bytes, depth = "business_mappings") {
  if (!Buffer.isBuffer(bytes) || !bytes.length || bytes.length > 5_000_000)
    throw new Error("Workbook exceeds the 5 MB limit.");
  await new Promise((resolve, reject) =>
    yauzl.fromBuffer(bytes, { lazyEntries: true }, (error, zip) => {
      if (error) return reject(error);
      let count = 0,
        size = 0;
      zip.on("error", reject);
      zip.on("end", resolve);
      zip.on("entry", (entry) => {
        if (++count > 2000 || (size += entry.uncompressedSize) > 50_000_000) {
          zip.close();
          reject(new Error("Workbook expands beyond the supported size."));
        } else zip.readEntry();
      });
      zip.readEntry();
    }),
  );
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(await excelReaderBytes(bytes));
  if (workbook.worksheets.length > 100)
    throw new Error("Workbook has too many worksheets.");
  const sheets = workbook.worksheets.map((s) => {
    if (
      s.rowCount > 10000 ||
      s.columnCount > 500 ||
      s.rowCount * s.columnCount > 250000
    )
      throw new Error("Worksheet exceeds the supported dimensions.");
    const preview = [];
    const formulas = [];
    const reference_rows = [];
    // Header candidates remain observations. The hosted skill and review decide business meaning.
    s.eachRow({ includeEmpty: false }, (row, index) => {
      if (depth !== "structure") {
        const values = [];
        row.eachCell({ includeEmpty: true }, (cell, col) => {
          values[col - 1] = scalar(cell.value);
        });
        reference_rows.push({ row: index, values });
      }
      if (preview.length < 30 && (depth !== "structure" || index <= 10)) {
        const values = [];
        row.eachCell({ includeEmpty: true }, (cell, col) => {
          values[col - 1] = scalar(cell.value);
        });
        preview.push({ row: index, values });
      }
      row.eachCell((cell) => {
        if (cell.formula && formulas.length < 100)
          formulas.push({ cell: cell.address, formula: cell.formula });
      });
    });
    const tables = Object.values(s.tables).map((t) => {
      const table = t.table;
      const header = Number(
        (table.tableRef || table.ref).split(":")[0].match(/\d+$/)?.[0],
      );
      return {
        name: table.name,
        range: table.tableRef,
        header_row: header,
        columns: table.columns.map((c) => c.name),
      };
    });
    const headerRows = tables.length ? tables.map((t) => t.header_row) :
      preview.filter((r) => r.values.filter((v) => typeof v === "string" && v.trim()).length >= 2).slice(0, 1).map((r) => r.row);
    const headers = headerRows.map((index) => {
      const values = [];
      s.getRow(index).eachCell({ includeEmpty: true }, (cell, col) => {
        values[col - 1] = typeof scalar(cell.value) === "string" ? scalar(cell.value) : null;
      });
      return { row: index, values };
    });
    return {
      sheet: s.name,
      state: s.state,
      rows: s.rowCount,
      columns: s.columnCount,
      tables,
      merged_ranges: s.model.merges,
      preview: depth === "structure" ? headers : preview,
      formulas: depth === "structure" ? [] : formulas,
      reference_rows: depth === "structure" ? [] : reference_rows,
    };
  });
  return { format: "xlsx", sheets, defined_names: depth === "structure" ? [] : workbook.definedNames.model };
}

/** Keep only candidate/table headers in bytes sent for business mapping. Local
 * source bytes stay on the PC until a workflow explicitly refreshes its inputs.
 * Untabled header candidates require the operator's normal mapping confirmation.
 */
export async function excelSchemaBytes(bytes) {
  const observed = await inspectExcel(bytes, "structure");
  const workbook = new ExcelJS.Workbook();
  // Build a fresh package: clearing values in the original can retain comments,
  // hyperlinks, images, cached formulas and document properties with client data.
  for (const layout of observed.sheets) {
    const sheet = workbook.addWorksheet(layout.sheet, { state: layout.state });
    for (const header of layout.preview) {
      header.values.forEach((value, index) => {
        if (typeof value === "string") sheet.getCell(header.row, index + 1).value = value;
      });
    }
    for (const table of layout.tables) {
      const endRow = Number(table.range.split(":").at(-1).match(/\d+$/)[0]);
      sheet.addTable({ name: table.name, ref: table.range.split(":")[0], headerRow: true,
        columns: table.columns.map((name) => ({ name })),
        rows: Array.from({ length: Math.max(0, endRow - table.header_row) }, () => table.columns.map(() => null)),
      });
    }
    for (const range of layout.merged_ranges) sheet.mergeCells(range);
  }
  return Buffer.from(await workbook.xlsx.writeBuffer());
}

export async function discoverTally(
  config,
  { request = fetch, onProgress = async () => {}, metadata = tallySchema } = {},
) {
  const { company, port = 9000, categories, depth } = config;
  if (
    typeof company !== "string" ||
    !company.trim() ||
    company.length > 200 ||
    /[\x00-\x1f]/.test(company) ||
    !Array.isArray(categories) ||
    !categories.length ||
    categories.some((c) => !Object.hasOwn(TALLY_COLLECTIONS, c)) ||
    new Set(categories).size !== categories.length ||
    !["structure", "reference_data", "business_mappings"].includes(depth)
  )
    throw new Error("Invalid Tally discovery configuration.");
  const probe = await tallyProbe({ port, request });
  if (!probe.companies.includes(company))
    throw new Error(
      "The selected company is not open in Tally. Open it and refresh discovery.",
    );
  if (depth === "structure") {
    let tables;
    try {
      tables = await metadata({ port });
      if (!Array.isArray(tables) || tables.length > 500 || tables.some((t) =>
        typeof t.table !== "string" || !t.table || t.table.length > 200 ||
        !Array.isArray(t.columns) || t.columns.length > 2000 || t.columns.some((c) =>
          typeof c.name !== "string" || !c.name || c.name.length > 300 ||
          typeof c.type !== "string" || c.type.length > 100 || typeof c.nullable !== "boolean" ||
          !Number.isInteger(c.ordinal) || c.ordinal < 0))) throw new Error("Invalid metadata.");
    } catch {
      tables = null;
    }
    const aliases = { groups: "Groups", cost_centres: "CostCentre", units: "Unit", currencies: "Currency" };
    const collections = [];
    for (const category of categories) {
      await onProgress(category, "reading");
      const table = aliases[category] || TALLY_COLLECTIONS[category][0];
      const columns = tables?.find((t) => t.table.toLowerCase() === table.toLowerCase())?.columns || [];
      collections.push(tables ? {
        category, status: "ready", count: 0, records: [], fields: columns.map((c) => c.name),
        schema: { source: "odbc_metadata", coverage: columns.length ? "exposed_top_level_methods" : "not_exposed", table, columns },
      } : { category, status: "unavailable", error: "Enable Tally ODBC and its 64-bit driver on this PC, then retry structure discovery." });
      await onProgress(category, tables ? "ready" : "unavailable");
    }
    return { company, port, collections, schema_tables: tables || [] };
  }
  const collections = [];
  for (const category of categories) {
    await onProgress(category, "reading");
    const [type, tag] = TALLY_COLLECTIONS[category];
    try {
      const xml = `<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>MinkopsDiscovery</ID></HEADER><BODY><DESC><STATICVARIABLES><SVCURRENTCOMPANY>${escapeXml(company)}</SVCURRENTCOMPANY><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="MinkopsDiscovery" ISMODIFY="No"><TYPE>${type}</TYPE><FETCH>Name,GUID,Parent,AlterID</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>`;
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
      records = records.map((r) => Object.fromEntries(
        Object.entries(r)
          .filter(([key]) => ["@_NAME", "NAME", "GUID", "PARENT", "ALTERID"].includes(key))
          .map(([key, value]) => [key, tallyReferenceScalar(value)]),
      ));
      if (category === "company")
        records = records.filter(
          (r) =>
            r["@_NAME"] === company ||
            r.NAME === company,
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
        records: depth === "structure" ? [] : records,
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
