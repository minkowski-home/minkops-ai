import test from "node:test";
import assert from "node:assert/strict";
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
  const metadata = await inspectExcel(projection);
  assert.deepEqual(metadata.sheets[0].preview[0], { row: 42, values: [null, "Invoice", "Supplier"] });
  assert.deepEqual(metadata.sheets[0].reference_rows, []);
  assert.deepEqual(metadata.sheets[0].formulas, [{cell:"D43",formula:'"private formula"'}]);
  assert.equal(result.getWorksheet("Bills").getCell("D43").value.result, undefined);
});
