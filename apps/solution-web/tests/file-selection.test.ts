import test from 'node:test';
import assert from 'node:assert/strict';
import { eligibleFiles, restoreSelection, reconcileSelection, selectionKeys } from '../src/starter/accounts/fileSelection.ts';
const source = {id:'s',label:'Bills',writable:false,files:[{id:'a',path:'nested/a.PDF',sha256:''},{id:'b',path:'b.jpg',sha256:''},{id:'x',path:'ledger.xlsx',sha256:''}]};
test('first visit selects supported bills; explicit empty selection stays empty',()=>{
  assert.deepEqual(eligibleFiles([source]).map(f=>f.id),['a','b']);
  assert.deepEqual(restoreSelection([source],null),['a','b']);
  assert.deepEqual(restoreSelection([source],'[]'),[]);
});
test('malformed preferences recover safely; stale and unsupported keys are ignored',()=>{
  for(const raw of ['{','null','{}','[1]']) assert.deepEqual(restoreSelection([source],raw),['a','b']);
  assert.deepEqual(restoreSelection([source],'["s:nested/a.PDF","s:gone.pdf","s:ledger.xlsx"]'),['a']);
  assert.deepEqual(restoreSelection([source],'["s:gone.pdf"]'),[]);
});
test('refresh preserves choices across changing IDs, removes vanished files and leaves new files unchecked',()=>{
  const next={...source,files:[{id:'new-a',path:'nested/a.PDF',sha256:'new'},{id:'c',path:'c.webp',sha256:''}]};
  assert.deepEqual(reconcileSelection([source],[next],['a']),['new-a']);
  assert.deepEqual(reconcileSelection([source],[next],[]),[]);
  assert.deepEqual(selectionKeys([source],['a','x']),['s:nested/a.PDF']);
});
test('same path in different sources remains independently selectable',()=>{
  const other={...source,id:'other',files:[{id:'z',path:'nested/a.PDF',sha256:''}]};
  assert.deepEqual(restoreSelection([source,other],'["other:nested/a.PDF"]'),['z']);
});

test('statement selections retain CSV and XLSX paths across refreshed IDs without adding bills',()=>{
  const pattern=/\.(csv|xlsx)$/i;
  const bank={...source,files:[...source.files,{id:'csv',path:'bank.CSV',sha256:''}]};
  const keys=selectionKeys([bank],['a','csv','x'],pattern);
  assert.deepEqual(keys,['s:ledger.xlsx','s:bank.CSV']);
  const refreshed={...bank,files:[{id:'new-csv',path:'bank.CSV',sha256:'new'},{id:'new-xlsx',path:'ledger.xlsx',sha256:'new'},{id:'new-bill',path:'bill.pdf',sha256:''}]};
  assert.deepEqual(restoreSelection([refreshed],JSON.stringify(keys),pattern),['new-csv','new-xlsx']);
  assert.deepEqual(restoreSelection([refreshed],'[]',pattern),[]);
});
