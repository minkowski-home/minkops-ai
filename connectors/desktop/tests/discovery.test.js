import test from "node:test";
import assert from "node:assert/strict";
import ExcelJS from "exceljs";
import JSZip from "jszip";
import { inspectExcel, discoverTally } from "../src/discovery.js";

test("Excel inspection accepts absolute package table relationships produced by openpyxl", async () => {
  const w = new ExcelJS.Workbook();
  w.addWorksheet("Bills").addTable({
    name: "Purchases",
    ref: "B5",
    columns: [{ name: "Invoice" }, { name: "Amount" }],
    rows: [["00018", 1180]],
  });
  const original = Buffer.from(await w.xlsx.writeBuffer());
  const zip = await JSZip.loadAsync(original);
  const path = "xl/worksheets/_rels/sheet1.xml.rels";
  const rels = await zip.file(path).async("string");
  assert.ok(rels.includes('Target="../tables/table1.xml"'));
  zip.file(
    path,
    rels.replace(
      'Target="../tables/table1.xml"',
      'Target="/xl/tables/table1.xml"',
    ),
  );
  const absolute = await zip.generateAsync({ type: "nodebuffer" });
  const unchanged = Buffer.from(absolute);
  assert.deepEqual(await inspectExcel(absolute), await inspectExcel(original));
  assert.deepEqual(
    absolute,
    unchanged,
    "inspection must not change uploaded workbook bytes",
  );
});

test("local Excel inspection preserves off-row headers, named tables, formulas and identifiers", async () => {
  const w = new ExcelJS.Workbook();
  const s = w.addWorksheet("Purchases");
  s.getCell("A1").value = "Purchase register";
  s.addTable({
    name: "Bills",
    ref: "A5",
    headerRow: true,
    columns: [{ name: "Invoice" }, { name: "Vendor" }, { name: "Total" }],
    rows: [["00017", "Minkops supplier", 118]],
  });
  s.getCell("D6").value = { formula: "C6*2", result: 236 };
  const result = await inspectExcel(
    Buffer.from(await w.xlsx.writeBuffer()),
    "business_mappings",
  );
  assert.equal(result.sheets[0].tables[0].name, "Bills");
  assert.equal(result.sheets[0].tables[0].header_row, 5);
  assert.deepEqual(result.sheets[0].tables[0].columns, [
    "Invoice",
    "Vendor",
    "Total",
  ]);
  assert.equal(
    result.sheets[0].preview.find((r) => r.row === 6).values[0],
    "00017",
  );
  assert.deepEqual(result.sheets[0].formulas, [
    { cell: "D6", formula: "C6*2" },
  ]);
  assert.ok(
    (
      await inspectExcel(Buffer.from(await w.xlsx.writeBuffer()), "structure")
    ).sheets[0].preview.every((r) => r.row <= 10),
  );
});

test("Tally discovery scopes company, preserves nested tax records, isolates failed categories", async () => {
  const sent = [];
  const result = await discoverTally(
    {
      company: "Test & Co",
      port: 9001,
      categories: ["ledgers", "stock_items"],
      depth: "reference_data",
    },
    {
      request: async (url, options) => {
        sent.push({ url, body: options.body });
        if (options.body.includes("<TYPE>Company</TYPE>"))
          return new Response(
            '<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><COMPANY NAME="Test &amp; Co"/></COLLECTION></DATA></BODY></ENVELOPE>',
          );
        if (options.body.includes("<TYPE>StockItem</TYPE>"))
          throw new Error("offline");
        return new Response(
          '<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><LEDGER NAME="001"><GUID>abc</GUID><PARENT>Sundry Creditors</PARENT><GSTDETAILS.LIST><GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE><PARTYGSTIN>001234</PARTYGSTIN></GSTDETAILS.LIST></LEDGER></COLLECTION></DATA></BODY></ENVELOPE>',
        );
      },
    },
  );
  assert.equal(result.collections[0].records[0]["@_NAME"], "001");
  assert.equal(
    result.collections[0].records[0]["GSTDETAILS.LIST"].PARTYGSTIN,
    "001234",
  );
  assert.equal(result.collections[1].status, "unavailable");
  assert.match(
    sent[1].body,
    /<SVCURRENTCOMPANY>Test &amp; Co<\/SVCURRENTCOMPANY>/,
  );
  assert.ok(
    sent.every(
      (s) =>
        s.url === "http://127.0.0.1:9001" &&
        !s.body.includes("<TALLYREQUEST>Import"),
    ),
  );
  await assert.rejects(
    discoverTally({
      company: "Test",
      port: 9000,
      categories: ["arbitrary"],
      depth: "structure",
    }),
  );
});

test("Tally discovery refuses unopened companies and never falls back to the active company", async () => {
  let calls = 0;
  await assert.rejects(
    discoverTally(
      {
        company: "Missing",
        port: 9000,
        categories: ["ledgers"],
        depth: "reference_data",
      },
      {
        request: async () => {
          calls++;
          return new Response(
            '<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><COMPANY NAME="Other"/></COLLECTION></DATA></BODY></ENVELOPE>',
          );
        },
      },
    ),
    /not open/,
  );
  assert.equal(calls, 1);
});
