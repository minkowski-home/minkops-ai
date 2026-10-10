import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  discoverClientContext,
  saveDiscoveryPackage,
} from "../src/client-context.js";

const reply = (record) =>
  new Response(
    `<ENVELOPE><BODY><EXPORTDATA><REQUESTDATA><TALLYMESSAGE>${record}</TALLYMESSAGE></REQUESTDATA></EXPORTDATA></BODY></ENVELOPE>`,
  );
const company = (name) =>
  `<COMPANY NAME="${name}"><GUID>${name}-guid</GUID><GSTIN>00123</GSTIN></COMPANY>`;
function transport(sent, fail = false) {
  return async (_url, { body }) => {
    sent.push(body);
    if (body.includes("<ID>MinkopsCompanies</ID>"))
      return new Response(
        `<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>${company("A")}${company("B")}</COLLECTION></DATA></BODY></ENVELOPE>`,
      );
    const name = body.includes("<SVCURRENTCOMPANY>A</SVCURRENTCOMPANY>")
      ? "A"
      : "B";
    if (body.includes("<TYPE>Company</TYPE>"))
      return new Response(
        `<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>${company(name)}</COLLECTION></DATA></BODY></ENVELOPE>`,
      );
    if (body.includes("<ID>List of Accounts</ID>"))
      return reply(
        '<LEDGER NAME="Supplier"><GUID>001</GUID><PARENT>Sundry Creditors</PARENT><GSTDETAILS.LIST><PARTYGSTIN>001234</PARTYGSTIN></GSTDETAILS.LIST></LEDGER><VOUCHERTYPE NAME="Purchase"/><CUSTOMMASTER NAME="Custom"><FIELD>value</FIELD></CUSTOMMASTER>',
      );
    if (fail && name === "B") throw new Error("unavailable");
    return reply(
      "<VOUCHER><GUID>v1</GUID><DATE>20261001</DATE><ALLINVENTORYENTRIES.LIST><STOCKITEMNAME>Item</STOCKITEMNAME><BATCHALLOCATIONS.LIST><GODOWNNAME>Site</GODOWNNAME></BATCHALLOCATIONS.LIST></ALLINVENTORYENTRIES.LIST></VOUCHER>",
    );
  };
}
test("discovery collects every loaded company, undated full masters and dated nested vouchers", async () => {
  const sent = [];
  const snapshot = await discoverClientContext(
    { port: 9000, period: { from: "2026-10-01", to: "2026-10-02" } },
    { request: transport(sent) },
  );
  assert.equal(snapshot.companies.length, 2);
  assert.equal(snapshot.companies[0].company_guid, "A-guid");
  assert.equal(
    snapshot.companies[0].masters.records[0].data["GSTDETAILS.LIST"].PARTYGSTIN,
    "001234",
  );
  assert.equal(snapshot.companies[0].masters.records[2].type, "CUSTOMMASTER");
  assert.equal(
    snapshot.companies[0].vouchers.records[0].data["ALLINVENTORYENTRIES.LIST"][
      "BATCHALLOCATIONS.LIST"
    ].GODOWNNAME,
    "Site",
  );
  assert.ok(
    sent
      .filter((b) => b.includes("<ID>List of Accounts</ID>"))
      .every((b) => !b.includes("SVFROMDATE")),
  );
  assert.ok(
    sent
      .filter((b) => b.includes("<ID>DayBook</ID>"))
      .every((b) =>
        b.includes('<SVFROMDATE TYPE="Date">20261001</SVFROMDATE>'),
      ),
  );
});
test("failed company remains partial without losing successful company", async () => {
  const result = await discoverClientContext(
    { port: 9000, period: { from: "2026-10-01", to: "2026-10-02" } },
    { request: transport([], true) },
  );
  assert.equal(result.companies[0].status, "ready");
  assert.equal(result.companies[1].status, "unavailable");
  assert.equal(result.partial, true);
});
test("invalid period and caller-supplied transport options never reach Tally", async () => {
  for (const config of [
    { port: 9000, period: { from: "2026-02-30", to: "2026-03-01" } },
    { port: 9000, period: { from: "2026-10-03", to: "2026-10-01" } },
    {
      port: 9000,
      period: { from: "2026-10-01", to: "2026-10-02" },
      company: "A",
    },
  ]) {
    await assert.rejects(
      discoverClientContext(config, {
        request: () => {
          throw new Error("should not call");
        },
      }),
      /Invalid/,
    );
  }
});
test("local package is immutable, hashed and repeatable after receipt replay", async () => {
  const root = await mkdtemp(join(tmpdir(), "minkops-context-"));
  try {
    const catalog = {
      format_version: "2",
      run_id: "11111111-1111-4111-8111-111111111111",
      sources: [],
      context_notes: [],
      partial: false,
    };
    const path = await saveDiscoveryPackage(root, catalog);
    const manifest = JSON.parse(
      await readFile(join(path, "manifest.json"), "utf8"),
    );
    assert.ok(manifest.files.every((f) => /^[a-f0-9]{64}$/.test(f.sha256)));
    assert.equal(await saveDiscoveryPackage(root, catalog), path);
    await assert.rejects(
      saveDiscoveryPackage(root, { ...catalog, partial: true }),
      /changed/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("Excel structure includes every formula but no cached result or business row", async () => {
  const { inspectExcel, excelSchemaBytes } =
    await import("../src/discovery.js");
  const { default: ExcelJS } = await import("exceljs");
  const book = new ExcelJS.Workbook(),
    sheet = book.addWorksheet("Bills");
  sheet.addRow(["Invoice", "Total", "Calculated"]);
  sheet.getCell("A2").value = "SECRET-BILL";
  for (let i = 2; i < 110; i++)
    sheet.getCell(`C${i}`).value = { formula: `B${i}*2`, result: 999 };
  const bytes = Buffer.from(await book.xlsx.writeBuffer());
  const projected = await excelSchemaBytes(bytes);
  const structure = await inspectExcel(projected, "structure");
  assert.equal(structure.sheets[0].formulas.length, 108);
  assert.equal(structure.sheets[0].reference_rows.length, 0);
  const clean = new ExcelJS.Workbook();
  await clean.xlsx.load(projected);
  assert.equal(clean.getWorksheet("Bills").getCell("A2").value, null);
  assert.equal(
    clean.getWorksheet("Bills").getCell("C2").value.result,
    undefined,
  );
});

test("unsupported array formulas require attention instead of losing range semantics", async () => {
  const { excelSchemaBytes } = await import("../src/discovery.js");
  const { default: ExcelJS } = await import("exceljs");
  const book = new ExcelJS.Workbook(),
    sheet = book.addWorksheet("Array");
  sheet.addRow(["Input", "Computed"]);
  sheet.getCell("B2").value = {
    formula: "A2:A3*2",
    shareType: "array",
    ref: "B2:B3",
    result: 10,
  };
  await assert.rejects(
    excelSchemaBytes(Buffer.from(await book.xlsx.writeBuffer())),
    /Unsupported.*formula/,
  );
});

test("native export files with TALLYMESSAGE directly under ENVELOPE retain full data", async () => {
  const base = transport([]);
  const result = await discoverClientContext(
    { port: 9000, period: { from: "2026-10-01", to: "2026-10-02" } },
    {
      request: async (url, options) => {
        const response = await base(url, options);
        const text = await response.text();
        return new Response(
          text
            .replace("<BODY><EXPORTDATA><REQUESTDATA>", "")
            .replace("</REQUESTDATA></EXPORTDATA></BODY>", ""),
        );
      },
    },
  );
  assert.equal(result.partial, false);
  assert.equal(result.companies[0].masters.count, 3);
  assert.equal(result.companies[0].vouchers.count, 1);
});

test("an empty native voucher export is a complete empty period, never empty masters", async () => {
  const base = transport([]);
  const result = await discoverClientContext(
    { port: 9000, period: { from: "2026-10-01", to: "2026-10-02" } },
    {
      request: (url, options) =>
        options.body.includes("<ID>DayBook</ID>")
          ? Promise.resolve(new Response("<ENVELOPE/>"))
          : base(url, options),
    },
  );
  assert.equal(result.partial, false);
  assert.equal(result.companies[0].vouchers.count, 0);
  assert.equal(result.companies[0].masters.count, 3);
});

test("indented native exports ignore formatting text but never discard unexpected content", async () => {
  for (const content of ["\r\n    ", "unexpected export content"]) {
    const base = transport([]);
    const result = await discoverClientContext(
      { port: 9000, period: { from: "2026-10-01", to: "2026-10-02" } },
      {
        request: async (url, options) => {
          const response = await base(url, options);
          return new Response((await response.text()).replaceAll(
            "<TALLYMESSAGE>", `<TALLYMESSAGE>${content}`,
          ));
        },
      },
    );
    assert.equal(result.partial, content.trim() !== "");
    if (!result.partial) assert.equal(result.companies[0].masters.count, 3);
  }
});

test("DayBook company trailers are checked against the discovered identity", async () => {
  for (const guid of ["A-guid", "different-guid"]) {
    const base = transport([]);
    const snapshot = await discoverClientContext(
      { port: 9000, period: { from: "2026-10-01", to: "2026-10-02" } },
      {
        request: async (url, options) => {
          const response = await base(url, options);
          let text = await response.text();
          if (options.body.includes("<ID>DayBook</ID>") && options.body.includes("<SVCURRENTCOMPANY>A</SVCURRENTCOMPANY>"))
            text = text.replace("</REQUESTDATA>", `<TALLYMESSAGE><COMPANY><REMOTECMPINFO.LIST MERGE="Yes"><NAME>${guid}</NAME><REMOTECMPNAME>A</REMOTECMPNAME><REMOTECMPSTATE>Rajasthan</REMOTECMPSTATE></REMOTECMPINFO.LIST></COMPANY></TALLYMESSAGE></REQUESTDATA>`);
          return new Response(text);
        },
      },
    );
    assert.equal(snapshot.partial, guid !== "A-guid");
    if (!snapshot.partial) assert.equal(snapshot.companies[0].vouchers.count, 1);
  }
});
