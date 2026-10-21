import test from 'node:test';
import assert from 'node:assert/strict';
import { companionNotice } from '../src/starter/desktop/companion.ts';

const pc = {id:'a',name:'PC A',owner_id:'me',revoked_at:null,expires_at:'2027-01-01',last_seen_at:null};

test('a PC is asked to update only when it reports a version older than runs need, or none', () => {
  assert.equal(companionNotice({...pc}), '', 'never polled: work waits for it');
  assert.match(companionNotice({...pc,last_seen_at:'2026-10-12'}), /Update Minkops on PC A to 0.10.0/);
  assert.match(companionNotice({...pc,last_seen_at:'2026-10-12',companion_version:'0.9.4'}), /Update Minkops/);
  assert.equal(companionNotice({...pc,last_seen_at:'2026-10-12',companion_version:'0.10.0'}), '');
  assert.equal(companionNotice({...pc,last_seen_at:'2026-10-12',companion_version:'1.0.0'}), '');
  assert.match(companionNotice({...pc,last_seen_at:'2026-10-12',companion_version:'0.10.0',remote_session:true}),
    /Remote Desktop session/);
});
