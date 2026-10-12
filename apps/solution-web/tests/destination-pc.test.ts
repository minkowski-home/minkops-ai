import test from 'node:test';
import assert from 'node:assert/strict';
import { destinationDevices, initialDestination, destinationAvailable } from '../src/starter/desktop/destinationPCs.ts';
const now = Date.parse('2026-10-12');
const pc = {id:'a',name:'PC A',owner_id:'me',revoked_at:null,expires_at:'2027-01-01',last_seen_at:null};
test('destination choices preserve account boundaries and expose expired PCs for reconnection', () => {
  const devices=[pc,{...pc,id:'b'},{...pc,id:'other',owner_id:'other'},{...pc,id:'revoked',revoked_at:'2026-01-01'},{...pc,id:'expired',expires_at:'2025-01-01'}];
  assert.deepEqual(destinationDevices(devices,'me').map(d=>d.id),['a','b','expired']);
  assert.equal(destinationAvailable(pc,now),true); // Offline work can queue.
  assert.equal(destinationAvailable(devices[4],now),false);
});
test('multiple PCs require a choice; saved unavailable choices never switch silently', () => {
  assert.equal(initialDestination([pc],null,now),'a');
  assert.equal(initialDestination([pc,{...pc,id:'b'}],null,now),'');
  assert.equal(initialDestination([pc],'"b"',now),'b');
  assert.equal(initialDestination([pc],'""',now),'');
  assert.equal(initialDestination([pc],'{}',now),'a');
  assert.equal(initialDestination([{...pc,expires_at:'2025-01-01'}],null,now),'');
});
