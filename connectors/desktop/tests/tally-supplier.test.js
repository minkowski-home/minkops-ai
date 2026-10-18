import test from 'node:test';
import assert from 'node:assert/strict';
import { XMLParser } from 'fast-xml-parser';
import { buildGSTSupplier, verifyGSTSupplier, readGSTSupplier } from '../src/tally.js';

const gst = {version: 1, gstin: '08AABCM1256F1ZR', registration_type: 'Regular', state_code: '08',
  state: 'Rajasthan', place_of_supply: 'Rajasthan', address: ['Synthetic Industrial Road', 'Sikar'],
  pincode: '332001', applicable_from: '2026-10-01', template: {name: 'Existing supplier', guid: 'template-guid', alter_id: '3'}};
const plan = {company: 'Test', company_guid: 'company', port: 9000, vendor: 'New & Sons <Synthetic>', gst_supplier: gst};
const template = {'@_NAME': 'Existing supplier', GUID: 'template-guid', ALTERID: '3', PARENT: 'Sundry Creditors',
  OPENINGBALANCE: '999999', 'BANKDETAILS.LIST': {ACCOUNTNUMBER: 'NEVER COPY'},
  'LEDGSTREGDETAILS.LIST': {APPLICABLEFROM: '20260401', GSTREGISTRATIONTYPE: 'Regular', GSTIN: '27AAPFU0939F1ZV', PLACEOFSUPPLY: 'Maharashtra'},
  'LEDMAILINGDETAILS.LIST': {APPLICABLEFROM: '20260401', MAILINGNAME: 'Existing supplier', STATE: 'Maharashtra', COUNTRY: 'India', PINCODE: '411001', 'ADDRESS.LIST': {ADDRESS: ['Other address']}}};

test('GST supplier uses the same-company template shape and copies no unrelated master state', () => {
  const source = buildGSTSupplier(plan, template);
  assert.ok(!source.includes('999999') && !source.includes('NEVER COPY') && !source.includes('27AAPFU0939F1ZV'));
  const ledger = new XMLParser({ignoreAttributes: false, parseTagValue: false}).parse(source).LEDGER;
  assert.equal(ledger['@_NAME'], plan.vendor);
  assert.equal(ledger['@_ACTION'], 'Create');
  assert.equal(ledger.PARENT, 'Sundry Creditors');
  assert.equal(ledger['LEDGSTREGDETAILS.LIST'].GSTIN, gst.gstin);
  assert.equal(ledger['LEDGSTREGDETAILS.LIST'].PLACEOFSUPPLY, 'Rajasthan');
  assert.equal(ledger['LEDMAILINGDETAILS.LIST'].PINCODE, '332001');
  assert.equal(ledger.GUID, undefined);
  assert.ok(verifyGSTSupplier({...ledger, GUID: 'created'}, gst));
  ledger['LEDGSTREGDETAILS.LIST'].GSTIN = '27AAPFU0939F1ZV';
  assert.equal(verifyGSTSupplier({...ledger, GUID: 'created'}, gst), false);
});

test('stale templates, invalid GSTIN and unsupported GST shapes refuse before import', () => {
  for (const altered of [{...template, ALTERID: '4'}, {...template, GUID: 'foreign'},
    {...template, 'LEDGSTREGDETAILS.LIST': ''}, {...template, 'LEDGSTREGDETAILS.LIST': {...template['LEDGSTREGDETAILS.LIST'], ISECOMMOPERATOR: 'Yes'}}])
    assert.throws(() => buildGSTSupplier(plan, altered));
  assert.throws(() => buildGSTSupplier({...plan, gst_supplier: {...gst, gstin: '08AABCM1256F1ZA'}}, template));
});

test('legacy GST templates retain their known layout without copying identity or balances', () => {
  const legacy = {'@_NAME': 'Existing supplier', GUID: 'template-guid', ALTERID: '3', PARENT: 'Sundry Creditors',
    GSTREGISTRATIONTYPE: 'Regular', PARTYGSTIN: '27AAPFU0939F1ZV', LEDSTATENAME: 'Maharashtra',
    PLACEOFSUPPLY: 'Maharashtra', COUNTRYNAME: 'India', PINCODE: '411001', 'ADDRESS.LIST': {ADDRESS: ['Old address']}};
  const source = buildGSTSupplier(plan, legacy);
  const ledger = new XMLParser({ignoreAttributes: false, parseTagValue: false}).parse(source).LEDGER;
  assert.equal(ledger.PARTYGSTIN, gst.gstin);
  assert.equal(ledger.LEDSTATENAME, 'Rajasthan');
  assert.ok(verifyGSTSupplier({...ledger, GUID: 'created'}, gst));
});

test('GST reads use a company-scoped GUID-filtered collection and reject another company ledger', async () => {
  const requests = [];
  const request = async (_url, options) => {
    requests.push(options.body);
    if (options.body.includes('MinkopsOpenCompanies')) return new Response('<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><COMPANY NAME="Test"><NAME>Test</NAME><GUID>company</GUID><COMPANYNUMBER>100000</COMPANYNUMBER></COMPANY></COLLECTION></DATA></BODY></ENVELOPE>');
    assert.ok(options.body.includes('<TYPE>Collection</TYPE>'));
    assert.ok(options.body.includes('<SVCURRENTCOMPANY>Test</SVCURRENTCOMPANY>'));
    assert.ok(options.body.includes('$GUID = "expected-guid"'));
    return new Response('<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><LEDGER NAME="Existing supplier"><GUID>wrong-company-guid</GUID></LEDGER></COLLECTION></DATA></BODY></ENVELOPE>');
  };
  await assert.rejects(() => readGSTSupplier(plan, 'Existing supplier', {request, identity: {GUID: 'expected-guid'}}), /missing or ambiguous/);
  assert.equal(requests.length, 2);
});
