/** Read-only local structure collection. Never executes workbook formulas or TDL from callers. */
import ExcelJS from "exceljs";
import yauzl from "yauzl";
import JSZip from "jszip";
import { posix } from "node:path";
import { XMLParser, XMLBuilder, XMLValidator } from "fast-xml-parser";

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
    if (
      !entry.dir &&
      (/^xl\/tables\/.*\.xml$/.test(name) ||
        /^xl\/worksheets\/.*\.xml$/.test(name))
    ) {
      const xml = await entry.async("string");
      if (
        /<(?:calculatedColumnFormula|totalsRowFormula)\b/.test(xml) ||
        /<f\b[^>]*\bt=["'](?:array|dataTable)["']/.test(xml)
      )
        throw new Error(
          "Unsupported table or array formula; discovery needs attention.",
        );
    }
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

export async function inspectExcel(bytes) {
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
    // Header candidates remain observations. The hosted skill and review decide business meaning.
    s.eachRow({ includeEmpty: false }, (row, index) => {
      if (preview.length < 30 && index <= 10) {
        const values = [];
        row.eachCell({ includeEmpty: true }, (cell, col) => {
          values[col - 1] = scalar(cell.value);
        });
        preview.push({ row: index, values });
      }
      row.eachCell((cell) => {
        if (cell.formula)
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
    const headerRows = tables.length
      ? tables.map((t) => t.header_row)
      : preview
          .filter(
            (r) =>
              r.values.filter((v) => typeof v === "string" && v.trim())
                .length >= 2,
          )
          .slice(0, 1)
          .map((r) => r.row);
    const headers = headerRows.map((index) => {
      const values = [];
      s.getRow(index).eachCell({ includeEmpty: true }, (cell, col) => {
        values[col - 1] =
          typeof scalar(cell.value) === "string" ? scalar(cell.value) : null;
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
      preview: headers,
      formulas,
      reference_rows: [],
    };
  });
  return {
    format: "xlsx",
    sheets,
    defined_names: [],
  };
}

/** Keep only candidate/table headers in bytes sent for business mapping. Local
 * source bytes stay on the PC until a workflow explicitly refreshes its inputs.
 * Untabled header candidates require the operator's normal mapping confirmation.
 */
export async function excelSchemaBytes(bytes) {
  const observed = await inspectExcel(bytes);
  const workbook = new ExcelJS.Workbook();
  // Build a fresh package: clearing values in the original can retain comments,
  // hyperlinks, images, cached formulas and document properties with client data.
  for (const layout of observed.sheets) {
    const sheet = workbook.addWorksheet(layout.sheet, { state: layout.state });
    for (const header of layout.preview) {
      header.values.forEach((value, index) => {
        if (typeof value === "string")
          sheet.getCell(header.row, index + 1).value = value;
      });
    }
    for (const table of layout.tables) {
      const endRow = Number(table.range.split(":").at(-1).match(/\d+$/)[0]);
      sheet.addTable({
        name: table.name,
        ref: table.range.split(":")[0],
        headerRow: true,
        columns: table.columns.map((name) => ({ name })),
        rows: Array.from(
          { length: Math.max(0, endRow - table.header_row) },
          () => table.columns.map(() => null),
        ),
      });
    }
    for (const formula of layout.formulas)
      sheet.getCell(formula.cell).value = { formula: formula.formula };
    for (const range of layout.merged_ranges) sheet.mergeCells(range);
  }
  return Buffer.from(await workbook.xlsx.writeBuffer());
}
