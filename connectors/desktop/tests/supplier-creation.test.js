import test from "node:test";
import assert from "node:assert/strict";
import {createSupplier} from "../src/tally.js";

const plan = {kind:"supplier",company:"Test",company_guid:"company-guid",port:9000,vendor:"New & Co",gst_supplier:null};
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

test('an approved supplier is read before it is imported, and verified from Tally afterwards',async()=>{
  const io=native();
  const observed=await createSupplier(plan,io);
  assert.equal(observed.ledgers[0].GUID,'ledger-guid');
  const imports=io.calls.filter(c=>c.includes('<TALLYREQUEST>Import'));
  assert.equal(imports.length,1);
  assert.match(imports[0],/<NAME>New &amp; Co<\/NAME>/);
  assert.match(imports[0],/<PARENT>Sundry Creditors<\/PARENT>/);
  // A ledger that already has the name is read back as it is, never created twice.
  const existing=native({exists:true});
  assert.equal((await createSupplier(plan,existing)).ledgers[0].GUID,'ledger-guid');
  assert.equal(existing.calls.some(c=>c.includes('<TALLYREQUEST>Import')),false);
});
test('identity changes before creation prevent import and after creation prevent confirmation',async()=>{
  for(const config of [{wrongBefore:true},{wrongAfter:true}]) {
    const io=native(config);
    await assert.rejects(createSupplier(plan,io),/company changed/);
    assert.equal(io.calls.filter(c=>c.includes('<TALLYREQUEST>Import')).length,config.wrongBefore?0:1);
  }
});
test('lost supplier acknowledgement is never replayed automatically',async()=>{
  const io=native({loseAck:true});
  await assert.rejects(createSupplier(plan,io),/Lost acknowledgement/);
  assert.equal(io.calls.filter(c=>c.includes('<TALLYREQUEST>Import')).length,1);
  // The person's next Create this ledger finds the one the lost acknowledgement created.
  const observed=await createSupplier(plan,io);
  assert.equal(observed.ledgers[0].GUID,'ledger-guid');
  assert.equal(io.calls.filter(c=>c.includes('<TALLYREQUEST>Import')).length,1);
});
