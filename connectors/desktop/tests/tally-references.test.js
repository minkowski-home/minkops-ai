import test from "node:test";
import assert from "node:assert/strict";
import { readTallyReferences } from "../src/tally-references.js";

test('allocation verification fetches and retains the native enablement and category fields', async () => {
  const result = await readTallyReferences({company:'Test',port:9000,categories:['company','ledgers','cost_centres']}, {
    request: async (_url, {body}) => {
      if (body.includes('MinkopsOpenCompanies')) return new Response('<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><COMPANY NAME="Test"><NAME>Test</NAME><GUID>company</GUID></COMPANY></COLLECTION></DATA></BODY></ENVELOPE>');
      const centre = body.includes('<TYPE>CostCentre</TYPE>');
      const ledger = body.includes('<TYPE>Ledger</TYPE>');
      assert.ok(body.includes(centre ? ',Category' : ',IsCostCentresOn'));
      const tag = centre ? 'COSTCENTRE' : ledger ? 'LEDGER' : 'COMPANY';
      const fields = centre ? '<CATEGORY TYPE="String">Projects</CATEGORY>' : '<ISCOSTCENTRESON TYPE="Logical">Yes</ISCOSTCENTRESON>';
      return new Response(`<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><${tag} NAME="Test"><NAME>Test</NAME><GUID>identity</GUID>${fields}</${tag}></COLLECTION></DATA></BODY></ENVELOPE>`);
    },
  });
  assert.ok(result.collections.every(c => c.status === 'ready'));
  assert.equal(result.collections[0].records[0].ISCOSTCENTRESON, 'Yes');
  assert.equal(result.collections[1].records[0].ISCOSTCENTRESON, 'Yes');
  assert.equal(result.collections[2].records[0].CATEGORY, 'Projects');
});

test("typed Tally reference identities become exact strings and malformed wrappers fail closed", async () => {
  for (const malformed of [false, true]) {
    const result = await readTallyReferences({ company: "Test", port: 9000, categories: ["company", "ledgers"], }, {
      request: async (_url, options) => {
        const record = options.body.includes("<TYPE>Ledger</TYPE>")
          ? `<LEDGER NAME="Supplier"><GUID TYPE="String">${malformed ? '<VALUE>bad</VALUE>' : 'ledger-guid'}</GUID><PARENT TYPE="String">Sundry Creditors</PARENT><ALTERID TYPE="Number">0017</ALTERID></LEDGER>`
          : '<COMPANY NAME="Test"><NAME TYPE="String">Test</NAME><GUID TYPE="String">company-guid</GUID><ALTERID TYPE="Number">0012</ALTERID><PARENT TYPE="String"></PARENT></COMPANY>';
        return new Response(`<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>${record}</COLLECTION></DATA></BODY></ENVELOPE>`);
      },
    });
    assert.equal(result.collections[0].records[0].GUID, "company-guid");
    assert.equal(result.collections[0].records[0].ALTERID, "0012");
    assert.equal(result.collections[0].records[0].PARENT, "");
    if (malformed) assert.equal(result.collections[1].status, "unavailable");
    else assert.deepEqual(result.collections[1].records[0], { "@_NAME": "Supplier", GUID: "ledger-guid", PARENT: "Sundry Creditors", ALTERID: "0017" });
  }
});

test("Tally references scope the company, exclude unrelated values, and isolate failed categories", async () => {
  const sent = [];
  const result = await readTallyReferences(
    {
      company: "Test & Co",
      port: 9001,
      categories: ["ledgers", "stock_items"],
    },
    {
      request: async (url, options) => {
        sent.push({ url, body: options.body });
        if (options.body.includes("<TYPE>Company</TYPE>"))
          return new Response(
            '<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><COMPANY NAME="Test &amp; Co"><GUID>co-guid</GUID></COMPANY></COLLECTION></DATA></BODY></ENVELOPE>',
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
  assert.equal(result.collections[0].records[0]["GSTDETAILS.LIST"], undefined);
  assert.ok(sent.every((s) => !s.body.includes("<FETCH>*</FETCH>")));
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
    readTallyReferences({
      company: "Test",
      port: 9000,
      categories: ["arbitrary"],
    }),
  );
});

test("Tally references refuse unopened companies and never fall back to the active company", async () => {
  let calls = 0;
  await assert.rejects(
    readTallyReferences(
      {
        company: "Missing",
        port: 9000,
        categories: ["ledgers"],
      },
      {
        request: async () => {
          calls++;
          return new Response(
            '<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><COMPANY NAME="Other"><GUID>other-guid</GUID></COMPANY></COLLECTION></DATA></BODY></ENVELOPE>',
          );
        },
      },
    ),
    /not open/,
  );
  assert.equal(calls, 1);
});
