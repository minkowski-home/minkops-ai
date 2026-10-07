import assert from 'node:assert/strict';
import test from 'node:test';
import { commitLocalWrite, sha256 } from '../src/starter/accounts/localWrites.ts';

function handle(initial: string) {
  let bytes = new TextEncoder().encode(initial);
  let writes = 0;
  return { getFile: async () => new Blob([bytes]),
    createWritable: async () => ({ write: async (blob: Blob) => { bytes = new Uint8Array(await blob.arrayBuffer()); writes++; }, close: async () => {}, abort: async () => {} }),
    get writes() { return writes; } };
}

test('changed local files are rejected before any write', async () => {
  const file = handle('external change');
  await assert.rejects(commitLocalWrite(file, new Blob(['after']), await sha256(new Blob(['before'])), await sha256(new Blob(['after'])), async () => {}), /changed/);
  assert.equal(file.writes, 0);
});

test('reconnecting after a saved write verifies without appending again', async () => {
  const file = handle('after');
  const output = await commitLocalWrite(file, new Blob(['after']), await sha256(new Blob(['before'])), await sha256(new Blob(['after'])), async () => {});
  assert.equal(await output.text(), 'after');
  assert.equal(file.writes, 0);
});

test('backup precedes a write and saved bytes are verified', async () => {
  const file = handle('before'); let backup = '';
  const output = await commitLocalWrite(file, new Blob(['after']), await sha256(new Blob(['before'])), await sha256(new Blob(['after'])), async (blob) => { backup = await blob.text(); assert.equal(file.writes, 0); });
  assert.equal(backup, 'before'); assert.equal(await output.text(), 'after'); assert.equal(file.writes, 1);
});
