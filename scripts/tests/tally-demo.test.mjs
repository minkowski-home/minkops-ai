import test from "node:test";
import assert from "node:assert/strict";
import { masterXml, voucherXml, checkImport, verifyVoucher } from "../seed_tally_demo.mjs";

test("fixture XML escapes identities and retains separate tax allocations", () => {
  const xml = voucherXml({guid:"guid", type:"Purchase", date:"2026-10-02", reference:'A&B<1>',
    party:'A&B', entries:[{ledger:'A&B',amount:'118.00'}, {ledger:'Purchases',amount:'-100.00'},
      {ledger:'CGST',amount:'-9.00'}, {ledger:'SGST',amount:'-9.00'}]});
  assert.match(xml, /A&amp;B&lt;1&gt;/);
  assert.equal((xml.match(/<ALLLEDGERENTRIES.LIST>/g) ?? []).length, 4);
});

test("no malformed/unbalanced fixture can reach Tally", () => {
  assert.throws(() => voucherXml({date:'2026-10-03',entries:[]}), /date/i);
  assert.throws(() => voucherXml({date:'2026-02-31',entries:[]}), /date/i);
  assert.throws(() => voucherXml({date:'2026-10-01',entries:[{ledger:'A',amount:'1.00'}]}), /balance/i);
});

test("unit imports require a native template and omit its original identity", () => {
  assert.throws(() => masterXml({type:'UNIT',name:'MKQANos',guid:'u'}), /native unit/i);
  const template = {NAME:'NativeNos',GUID:'native-guid',ALTERID:'12',ISSIMPLEUNIT:'Yes',
    ORIGINALNAME:'Native Pieces',DECIMALPLACES:'3',GSTREPUOM:'NOS-NUMBERS'};
  const unit = masterXml({type:'UNIT',name:'MKQANos',guid:'u'},template);
  assert.match(unit, /^<UNIT ACTION="Create">/);
  assert.equal((unit.match(/<NAME>/g) ?? []).length,1);
  assert.doesNotMatch(unit, /GUID|ALTERID|NAME="MKQANos"/);
  assert.match(unit, /<GSTREPUOM>NOS-NUMBERS<\/GSTREPUOM>/);
  assert.notEqual(unit.match(/<NAME>(.*?)<\/NAME>/)[1],unit.match(/<ORIGINALNAME>(.*?)<\/ORIGINALNAME>/)[1]);
  assert.throws(() => masterXml({type:'UNIT',name:'QA18 Nos',guid:'u'}));
  assert.throws(() => masterXml({type:'UNIT',name:'QA18Nos',guid:'u'},template));
});

test("native empty inventory sections are empty while real allocations remain verified", () => {
  const expected = {date:'2026-06-01',type:'Purchase',inventory:false,stock_item:null,
    entries:[{ledger:'Vendor',amount:'118.00'},{ledger:'Purchases',amount:'-118.00'}]};
  const actual = {DATE:'20260601',VOUCHERTYPENAME:'Purchase',ISINVOICE:'No',
    'ALLINVENTORYENTRIES.LIST':'     ',
    'ALLLEDGERENTRIES.LIST':expected.entries.map(e=>({LEDGERNAME:e.ledger,AMOUNT:e.amount}))};
  assert.doesNotThrow(()=>verifyVoucher(expected,actual));
  assert.throws(()=>verifyVoucher(expected,{...actual,'ALLINVENTORYENTRIES.LIST':{STOCKITEMNAME:'unexpected'}}));
  assert.throws(()=>verifyVoucher(expected,{...actual,'ALLINVENTORYENTRIES.LIST':'malformed'}));
});

test("inventory readback uses entered ledgers without double-counting Tally's derived ledger view", () => {
  const expected = {date:'2026-06-01',type:'Purchase',inventory:true,stock_item:'Stock Kit',
    entries:[{ledger:'Vendor',amount:'118.00'},{ledger:'Purchases',amount:'-118.00'}]};
  const actual = {DATE:'20260601',VOUCHERTYPENAME:'Purchase',ISINVOICE:'Yes',
    'LEDGERENTRIES.LIST':{LEDGERNAME:'Vendor',AMOUNT:'118.00'},
    'ALLLEDGERENTRIES.LIST':expected.entries.map(e=>({LEDGERNAME:e.ledger,AMOUNT:e.amount})),
    'ALLINVENTORYENTRIES.LIST':{STOCKITEMNAME:'Stock Kit',ACTUALQTY:' 1.000 MKQANos',
      'ACCOUNTINGALLOCATIONS.LIST':{LEDGERNAME:'Purchases',AMOUNT:'-118.00'}}};
  assert.doesNotThrow(()=>verifyVoucher(expected,actual));
  actual['ALLINVENTORYENTRIES.LIST'].ACTUALQTY='2 MKQANos';
  assert.throws(()=>verifyVoucher(expected,actual));
});

test("acknowledgement must prove exactly the requested create count", () => {
  assert.doesNotThrow(() => checkImport('<RESPONSE><CREATED>2</CREATED><ALTERED>0</ALTERED><ERRORS>0</ERRORS></RESPONSE>',2));
  for (const result of ['<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>',
    '<RESPONSE><CREATED>2</CREATED><ALTERED>1</ALTERED><ERRORS>0</ERRORS></RESPONSE>',
    '<RESPONSE><CREATED>2</CREATED><ERRORS>1</ERRORS></RESPONSE>'])
    assert.throws(() => checkImport(result, 2), /Reconcile/);
});
