import test from 'node:test';
import assert from 'node:assert/strict';
import {saveTallyStatement,readStatementVouchers} from '../src/statement.js';

const plan={format_version:4,operation:'append',company:'Test',company_guid:'company',port:9000,
 remote_id:'12345678-1234-5234-8234-123456789abc',allocation:null,voucher_type:{NAME:'Payment',GUID:'payment'},
 data:{date:'2026-10-01',amount_cents:-10000,bank_ledger:'Bank',counter_ledger:'Expense',reference:'R1',narration:'Synthetic'},
 references:{company_guid:'company',ledgers:{Bank:{GUID:'bank'},Expense:{GUID:'expense'}}}};
const references={collections:[{category:'company',status:'ready',records:[{GUID:'company'}]},
 {category:'ledgers',status:'ready',records:[{NAME:'Bank',GUID:'bank'},{NAME:'Expense',GUID:'expense'}]},
 {category:'voucher_types',status:'ready',records:[{NAME:'Payment',GUID:'payment',PARENT:'Payment'}]}]};
const observed={guid:'native',fingerprint:'digest',date:'20261001',voucher_type:'Payment',tag:plan.remote_id,allocation:null,
 entries:[{ledger:'Bank',amount:10000},{ledger:'Expense',amount:-10000}]};

test('one durable intent, one import, exact native readback and overlap skip',async()=>{
 let imported=0,reads=0,attempted=false;
 const options={requireCompany:async()=>{},readReferences:async()=>references,
  readVouchers:async()=>++reads===1?[]:[observed],beforeImport:async()=>{assert.equal(imported,0);attempted=true;return true;},
  request:async(_url,{body})=>{assert.ok(attempted);assert.ok(body.includes('<VOUCHERTYPENAME>Payment</VOUCHERTYPENAME>'));imported++;
   return new Response('<RESPONSE><CREATED>1</CREATED><ALTERED>0</ALTERED><ERRORS>0</ERRORS></RESPONSE>');}};
 assert.equal((await saveTallyStatement(plan,options)).outcome,'saved');
 assert.equal((await saveTallyStatement(plan,options)).outcome,'duplicate');
 assert.equal(imported,1);
});

test('untagged date/amount matches hold, and an uncertain import is never resent',async()=>{
 let imports=0;
 const options={requireCompany:async()=>{},readReferences:async()=>references,readVouchers:async()=>[{...observed,tag:null}],
  beforeImport:async()=>true,request:async()=>{imports++;throw new Error('timeout');}};
 assert.equal((await saveTallyStatement(plan,options)).hold,'possible_existing');
 assert.equal(imports,0);
 options.readVouchers=async()=>[];
 assert.equal((await saveTallyStatement(plan,options)).hold,'uncertain_import');
 options.beforeImport=async()=>false;
 assert.equal((await saveTallyStatement(plan,options)).hold,'uncertain_import');
 assert.equal(imports,1);
});

test('native date reads use calendar components and reject an out-of-date voucher',async()=>{
 const request=async(_url,{body})=>{
  assert.ok(body.includes('$$YearOfDate:$Date * 10000'));
  assert.ok(body.includes('= 20261001'));
  return new Response('<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><VOUCHER><DATE>20261002</DATE></VOUCHER></COLLECTION></DATA></BODY></ENVELOPE>');
 };
 await assert.rejects(()=>readStatementVouchers(plan,{request}),/outside the approved/);
});

