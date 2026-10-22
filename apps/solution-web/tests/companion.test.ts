import test from 'node:test';
import assert from 'node:assert/strict';
import { companionNotice } from '../src/starter/desktop/companion.ts';

const pc = {id:'a',name:'PC A',owner_id:'me',revoked_at:null,expires_at:'2027-01-01',last_seen_at:null};

test('a PC is asked to update only when it reports a version older than runs need, or none', () => {
  assert.equal(companionNotice({...pc}), '', 'never polled: work waits for it');
  assert.match(companionNotice({...pc,last_seen_at:'2026-10-12'}), /Update Minkops on PC A to 0.11.0/);
  assert.match(companionNotice({...pc,last_seen_at:'2026-10-12',companion_version:'0.10.0'}), /Update Minkops/);
  assert.equal(companionNotice({...pc,last_seen_at:'2026-10-12',companion_version:'0.11.0'}), '');
  assert.equal(companionNotice({...pc,last_seen_at:'2026-10-12',companion_version:'1.0.0'}), '');
  // On a shared server, the member is told which Tally Minkops reads.
  const shared = {...pc,last_seen_at:'2026-10-12',remote_session:true,tally_port:9101};
  assert.match(companionNotice({...shared,companion_version:'0.10.0'}), /Update Minkops on PC A to 0.11.0/);
  assert.equal(companionNotice({...shared,companion_version:'0.11.0'}),
    'PC A runs in a remote session. Minkops reads only the Tally open in this Windows user\'s session, on port 9101.');
});
