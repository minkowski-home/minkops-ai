import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
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
  `<COMPANY NAME="${name}"><GUID>${name}-guid</GUID><COMPANYNUMBER> ${name === "A" ? "100000" : "100001"}</COMPANYNUMBER><GSTIN>00123</GSTIN></COMPANY>`;
function transport(sent, fail = false) {
  return async (_url, { body }) => {
    sent.push(body);
    if (body.includes("<ID>MinkopsAvailableCompanies</ID>"))
      return new Response(
        `<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>${company("A")}${company("B")}</COLLECTION></DATA></BODY></ENVELOPE>`
          .replaceAll("<COMPANY ", "<COMPANYONDISK ")
          .replaceAll("</COMPANY>", "</COMPANYONDISK>"),
      );
    if (
      body.includes("<ID>MinkopsCompanies</ID>") ||
      body.includes("<ID>MinkopsCompanyScope</ID>")
    )
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
  assert.deepEqual(
    snapshot.company_scope.map((c) => c.company),
    ["A", "B"],
  );
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
      .filter((b) => b.includes("<ID>Voucher Register</ID>"))
      .every((b) =>
        b.includes('<SVFROMDATE TYPE="Date">20261001</SVFROMDATE>'),
      ),
  );
});

test("a lost, added or replaced company during collection makes the package partial", async () => {
  for (const finalScope of [
    company("A"),
    company("A") + company("B") + company("C"),
    company("A") + company("B").replace("B-guid", "replacement-guid"),
  ]) {
    let probes = 0;
    const base = transport([]);
    const result = await discoverClientContext(
      { port: 9000, period: { from: "2026-10-01", to: "2026-10-02" } },
      {
        request: (url, options) =>
          options.body.includes("<ID>MinkopsCompanyScope</ID>") && ++probes > 1
            ? Promise.resolve(
                new Response(
                  `<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>${finalScope}</COLLECTION></DATA></BODY></ENVELOPE>`,
                ),
              )
            : base(url, options),
      },
    );
    assert.equal(result.partial, true);
    assert.match(result.scope_error, /company scope/i);
    assert.equal(result.companies.length, 2, "successful evidence is retained");
  }
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

test("an unopened on-disk company remains an identified unavailable company, never omitted", async () => {
  const base = transport([]);
  const result = await discoverClientContext(
    { port: 9000, period: { from: "2026-10-01", to: "2026-10-02" } },
    {
      request: (url, options) =>
        options.body.includes("<ID>MinkopsCompanyScope</ID>")
          ? Promise.resolve(
              new Response(
                `<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>${company("A")}</COLLECTION></DATA></BODY></ENVELOPE>`,
              ),
            )
          : base(url, options),
    },
  );
  assert.equal(result.partial, true);
  assert.equal(result.companies.length, 2);
  assert.equal(result.companies[1].company, "B");
  assert.equal(result.companies[1].status, "unavailable");
  assert.equal(result.company_scope[1].company_guid, null);
});
test("period discovery uses the range-aware register rather than the current-day report", async () => {
  const base = transport([]);
  const snapshot = await discoverClientContext(
    { port: 9000, period: { from: "2026-11-01", to: "2026-11-01" } },
    {
      request: (url, options) =>
        options.body.includes("<ID>Voucher Register</ID>")
          ? Promise.resolve(new Response("<ENVELOPE/>"))
          : base(url, options),
    },
  );
  assert.equal(snapshot.partial, false);
  assert.ok(snapshot.companies.every((c) => c.vouchers.count === 0));
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

test("local package rejects an occupied file without replacing it", async () => {
  const root = await mkdtemp(join(tmpdir(), "minkops-context-"));
  const catalog = {
    run_id: "11111111-1111-4111-8111-111111111111",
    sources: [],
  };
  const target = join(root, catalog.run_id);
  try {
    await writeFile(target, "Existing local file");
    await assert.rejects(
      saveDiscoveryPackage(root, catalog),
      /Invalid package directory/,
    );
    assert.equal(await readFile(target, "utf8"), "Existing local file");
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
  const structure = await inspectExcel(projected);
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
        options.body.includes("<ID>Voucher Register</ID>")
          ? Promise.resolve(new Response("<ENVELOPE/>"))
          : base(url, options),
    },
  );
  assert.equal(result.partial, false);
  assert.equal(result.companies[0].vouchers.count, 0);
  assert.equal(result.companies[0].masters.count, 3);
});

test("empty voucher DATA accepts whitespace but rejects nonempty text and failed exports", async () => {
  for (const [content, status, partial] of [
    ["  \r\n", "1", false],
    ["unexpected", "1", true],
    ["  ", "0", true],
  ]) {
    const base = transport([]);
    const result = await discoverClientContext(
      { port: 9000, period: { from: "2026-10-01", to: "2026-10-02" } },
      {
        request: (url, options) =>
          options.body.includes("<ID>Voucher Register</ID>")
            ? Promise.resolve(
                new Response(
                  `<ENVELOPE><HEADER><STATUS>${status}</STATUS></HEADER><BODY><DATA>${content}</DATA></BODY></ENVELOPE>`,
                ),
              )
            : base(url, options),
      },
    );
    assert.equal(result.partial, partial);
    if (!partial) assert.equal(result.companies[0].vouchers.count, 0);
  }
});

test("indented native exports ignore formatting text but never discard unexpected content", async () => {
  for (const content of ["\r\n    ", "unexpected export content"]) {
    const base = transport([]);
    const result = await discoverClientContext(
      { port: 9000, period: { from: "2026-10-01", to: "2026-10-02" } },
      {
        request: async (url, options) => {
          const response = await base(url, options);
          return new Response(
            (await response.text()).replaceAll(
              "<TALLYMESSAGE>",
              `<TALLYMESSAGE>${content}`,
            ),
          );
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
          if (
            options.body.includes("<ID>Voucher Register</ID>") &&
            options.body.includes("<SVCURRENTCOMPANY>A</SVCURRENTCOMPANY>")
          )
            text = text.replace(
              "</REQUESTDATA>",
              `<TALLYMESSAGE><COMPANY><REMOTECMPINFO.LIST MERGE="Yes"><NAME>${guid}</NAME><REMOTECMPNAME>A</REMOTECMPNAME><REMOTECMPSTATE>Rajasthan</REMOTECMPSTATE></REMOTECMPINFO.LIST></COMPANY></TALLYMESSAGE></REQUESTDATA>`,
            );
          return new Response(text);
        },
      },
    );
    assert.equal(snapshot.partial, guid !== "A-guid");
    if (!snapshot.partial)
      assert.equal(snapshot.companies[0].vouchers.count, 1);
  }
});
