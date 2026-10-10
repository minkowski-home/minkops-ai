import test from "node:test";
import assert from "node:assert/strict";
import { discoverTally } from "../src/discovery.js";
import { excelSchemaBytes, inspectExcel } from "../src/discovery.js";
import ExcelJS from "exceljs";

test("Excel projection retains off-row table headers without data or package attachments", async () => {
  const original = new ExcelJS.Workbook();
  original.creator = "private client";
  const sheet = original.addWorksheet("Bills");
  sheet.addTable({ name: "Bills", ref: "B42", headerRow: true,
    columns: [{ name: "Invoice" }, { name: "Supplier" }],
    rows: [["secret invoice", "secret supplier"]],
  });
  sheet.getCell("B42").note = "private comment";
  sheet.getCell("D43").value = { formula: '"private formula"', result: "private cached result" };
  sheet.getCell("E43").value = { text: "private link", hyperlink: "https://private.example" };
  const projection = await excelSchemaBytes(Buffer.from(await original.xlsx.writeBuffer()));
  const result = new ExcelJS.Workbook();
  await result.xlsx.load(projection);
  assert.equal(result.getWorksheet("Bills").getCell("B42").value, "Invoice");
  assert.equal(result.getWorksheet("Bills").getCell("B43").value, null);
  assert.equal(result.getWorksheet("Bills").getCell("B42").note, undefined);
  assert.notEqual(result.creator, "private client");
  const metadata = await inspectExcel(projection, "structure");
  assert.deepEqual(metadata.sheets[0].preview[0], { row: 42, values: [null, "Invoice", "Supplier"] });
  assert.deepEqual(metadata.sheets[0].reference_rows, []);
  assert.deepEqual(metadata.sheets[0].formulas, [{cell:"D43",formula:'"private formula"'}]);
  assert.equal(result.getWorksheet("Bills").getCell("D43").value.result, undefined);
});

test("structure discovery uses metadata without exporting business objects", async () => {
  const requests = [];
  const result = await discoverTally(
    { company: "Test Company", port: 9000, categories: ["ledgers"], depth: "structure" },
    {
      request: async (_, options) => {
        requests.push(options.body);
        return new Response('<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><COMPANY NAME="Test Company"/></COLLECTION></DATA></BODY></ENVELOPE>');
      },
      metadata: async ({ port }) => {
        assert.equal(port, 9000);
        return [{ table: "Ledger", columns: [{ name: "$Name", type: "VarChar", nullable: true, ordinal: 1 }] }];
      },
    },
  );
  assert.equal(requests.length, 1, "only the loaded-company probe may use XML");
  assert.deepEqual(result.collections[0].records, []);
  assert.deepEqual(result.collections[0].fields, ["$Name"]);
  assert.equal(result.collections[0].schema.source, "odbc_metadata");
  assert.equal(result.collections[0].schema.coverage, "exposed_top_level_methods");
  assert.equal(result.collections[0].count, 0);
});

test("unavailable metadata never falls back to exporting records", async () => {
  let calls = 0;
  const result = await discoverTally(
    { company: "Test", port: 9000, categories: ["ledgers"], depth: "structure" },
    {
      request: async () => {
        calls++;
        return new Response('<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><COMPANY NAME="Test"/></COLLECTION></DATA></BODY></ENVELOPE>');
      },
      metadata: async () => { throw new Error("missing driver"); },
    },
  );
  assert.equal(calls, 1);
  assert.equal(result.collections[0].status, "unavailable");
});
