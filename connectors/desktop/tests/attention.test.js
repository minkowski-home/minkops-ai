import test from "node:test";
import assert from "node:assert/strict";
import {inspectTallyAttention} from "../src/tally.js";

const plan = {company:"Test",company_guid:"company-guid",port:9000,vendor:"New & Co",invoice_number:"NEW-1"};
const envelope = records => `<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>${records}</COLLECTION></DATA></BODY></ENVELOPE>`;
const company = guid => `<COMPANY NAME="Test"><NAME>Test</NAME><GUID>${guid}</GUID></COMPANY>`;
const ledger = '<LEDGER NAME="New &amp; Co"><GUID>ledger-guid</GUID><PARENT>Sundry Creditors</PARENT><ALTERID>1</ALTERID></LEDGER>';
function native({exists=false,wrongBefore=false,wrongAfter=false,loseAck=false}={}) {
  let imported=false; const calls=[];
  return {calls,request:async (_url,options)=>{
    const body=options.body; calls.push(body);
    if(body.includes('<TALLYREQUEST>Import')) {
      imported=true;
      if(loseAck) throw new Error('Lost acknowledgement');
      return new Response('<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>');
    }
    const records=body.includes('<TYPE>Ledger</TYPE>') ? (exists||imported?ledger:'')
      : body.includes('<TYPE>Voucher</TYPE>') ? ''
      : company(wrongBefore||imported&&wrongAfter?'wrong-guid':'company-guid');
    return new Response(envelope(records));
  }};
}

test('refresh observes exact company and performs no import',async()=>{
  const io=native({exists:true});
  const observed=await inspectTallyAttention(plan,io);
  assert.equal(observed.company_guid,plan.company_guid);
  assert.equal(observed.ledgers[0]['@_NAME'],plan.vendor);
  assert.equal(observed.current,null);
  assert.equal(io.calls.some(c=>c.includes('<TALLYREQUEST>Import')),false);
});
test('one-click supplier creation reads before importing and verifies native master',async()=>{
  const io=native();
  const observed=await inspectTallyAttention(plan,{...io,createSupplier:true});
  assert.equal(observed.ledgers[0].GUID,'ledger-guid');
  const imports=io.calls.filter(c=>c.includes('<TALLYREQUEST>Import'));
  assert.equal(imports.length,1);
  assert.match(imports[0],/<NAME>New &amp; Co<\/NAME>/);
  assert.match(imports[0],/<PARENT>Sundry Creditors<\/PARENT>/);
  const existing=native({exists:true});
  await inspectTallyAttention(plan,{...existing,createSupplier:true});
  assert.equal(existing.calls.some(c=>c.includes('<TALLYREQUEST>Import')),false);
});
test('identity changes before creation prevent import and after creation prevent confirmation',async()=>{
  for(const config of [{wrongBefore:true},{wrongAfter:true}]) {
    const io=native(config);
    await assert.rejects(inspectTallyAttention(plan,{...io,createSupplier:true}),/company changed/);
    assert.equal(io.calls.filter(c=>c.includes('<TALLYREQUEST>Import')).length,config.wrongBefore?0:1);
  }
});
test('lost supplier acknowledgement is never replayed automatically',async()=>{
  const io=native({loseAck:true});
  await assert.rejects(inspectTallyAttention(plan,{...io,createSupplier:true}),/Lost acknowledgement/);
  assert.equal(io.calls.filter(c=>c.includes('<TALLYREQUEST>Import')).length,1);
  const observed=await inspectTallyAttention(plan,io);
  assert.equal(observed.ledgers[0].GUID,'ledger-guid');
  assert.equal(io.calls.filter(c=>c.includes('<TALLYREQUEST>Import')).length,1);
});
