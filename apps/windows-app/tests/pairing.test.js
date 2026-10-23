import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, readdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openPairing, stillPaired } from "../src/pairing.js";

const origin = "http://127.0.0.1:3000";
const device = {
  id: "11111111-1111-4111-8111-111111111111",
  tenant: "mock-tenant",
  owner_id: "22222222-2222-4222-8222-222222222222",
  credential: "secret-token",
};
// A stand-in for Windows credential storage: readable only through decrypt.
const cipher = {
  available: () => true,
  encrypt: (text) => Buffer.from("enc:" + Buffer.from(text).toString("base64")),
  decrypt: (data) => {
    const text = data.toString();
    if (!text.startsWith("enc:")) throw new Error("Unable to decrypt.");
    return Buffer.from(text.slice(4), "base64").toString();
  },
};

async function profile(t) {
  const directory = await mkdtemp(join(tmpdir(), "minkops-pairing-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  return directory;
}

test("a connected PC is restored as it was saved", async (t) => {
  const directory = await profile(t);
  const first = await openPairing({ directory, origin, cipher });
  assert.equal(first.problem, null);
  first.state.device = device;
  first.state.bindings["mock-tenant:x"] = { root: "C:\\Books" };
  await first.save();

  const again = await openPairing({ directory, origin, cipher });
  assert.equal(again.problem, null);
  assert.deepEqual(again.state, first.state);
  assert.equal(again.previous, null, "nothing to recover when the credential was read");
  assert.deepEqual((await readdir(directory)).sort(), ["companion.bin", "installation.json"]);
});

test("an unreadable credential keeps this PC's identity and is never overwritten", async (t) => {
  const directory = await profile(t);
  const first = await openPairing({ directory, origin, cipher });
  first.state.device = device;
  await first.save();
  // The encrypted file can no longer be read: damaged by a power cut, or its key is gone.
  await writeFile(join(directory, "companion.bin"), Buffer.alloc(64));

  const after = await openPairing({ directory, origin, cipher, now: () => new Date("2026-10-23T04:24:25Z") });
  assert.match(after.problem, /could not be read/);
  assert.equal(after.state.device, null);
  assert.equal(after.state.installation_id, first.state.installation_id, "reconnecting reuses the same PC record");
  assert.deepEqual(after.previous, { id: device.id, tenant: device.tenant, owner_id: device.owner_id });

  await after.save();
  const files = (await readdir(directory)).sort();
  assert.deepEqual(files, ["companion.bin", "companion.bin.unreadable-2026-10-23T04-24-25Z", "installation.json"]);
  assert.equal((await readFile(join(directory, files[1]))).every((byte) => byte === 0), true, "the old file is kept for support");
});

test("the plain identity file never holds the credential", async (t) => {
  const directory = await profile(t);
  const pairing = await openPairing({ directory, origin, cipher });
  pairing.state.device = device;
  await pairing.save();
  const plain = await readFile(join(directory, "installation.json"), "utf8");
  assert.doesNotMatch(plain, /secret-token/);
  assert.deepEqual(JSON.parse(plain), {
    server_origin: origin,
    installation_id: pairing.state.installation_id,
    device: { id: device.id, tenant: device.tenant, owner_id: device.owner_id },
  });
});

test("a PC connected by an earlier release keeps its identity", async (t) => {
  const directory = await profile(t);
  const legacy = { server_origin: origin, installation_id: "33333333-3333-4333-8333-333333333333", device, bindings: {}, pending: null };
  await writeFile(join(directory, "companion.bin"), cipher.encrypt(JSON.stringify(legacy)));

  const pairing = await openPairing({ directory, origin, cipher });
  assert.equal(pairing.problem, null);
  assert.deepEqual(pairing.state, legacy);
  // Written at once, so a later unreadable credential still finds this PC's record.
  assert.equal(JSON.parse(await readFile(join(directory, "installation.json"), "utf8")).installation_id, legacy.installation_id);
});

test("a disconnected PC has nothing to recover", async (t) => {
  const directory = await profile(t);
  const pairing = await openPairing({ directory, origin, cipher });
  pairing.state.device = device;
  await pairing.save();
  pairing.state.device = null;
  await pairing.save();
  await writeFile(join(directory, "companion.bin"), "garbage");
  assert.equal((await openPairing({ directory, origin, cipher })).previous, null);
});

test("another server's identity and credentials are never reused", async (t) => {
  const directory = await profile(t);
  const first = await openPairing({ directory, origin: "https://app.minkops.com", cipher });
  first.state.device = device;
  await first.save();
  const other = await openPairing({ directory, origin, cipher });
  assert.equal(other.state.device, null);
  assert.equal(other.previous, null);
  assert.notEqual(other.state.installation_id, first.state.installation_id);
});

test("unavailable credential storage leaves the saved file untouched", async (t) => {
  const directory = await profile(t);
  const first = await openPairing({ directory, origin, cipher });
  first.state.device = device;
  await first.save();
  const saved = await readFile(join(directory, "companion.bin"));
  const identity = await readFile(join(directory, "installation.json"), "utf8");

  const locked = await openPairing({ directory, origin, cipher: { ...cipher, available: () => false } });
  assert.match(locked.problem, /unavailable/);
  assert.equal(locked.state.installation_id, first.state.installation_id);
  assert.equal(locked.previous, null, "a credential that is still saved is never rotated away");
  await assert.rejects(locked.save(), /unavailable/);
  assert.deepEqual(await readFile(join(directory, "companion.bin")), saved);
  assert.equal(await readFile(join(directory, "installation.json"), "utf8"), identity);
});

test("a lost credential is reissued only for the same owner's live PC record", () => {
  const previous = { id: device.id, tenant: device.tenant, owner_id: device.owner_id };
  const installationId = "33333333-3333-4333-8333-333333333333";
  const record = { id: device.id, owner_id: device.owner_id, installation_id: installationId, revoked_at: null };
  const user = { id: device.owner_id };
  assert.equal(stillPaired({ previous, user, installationId, devices: [record] }), true);
  assert.equal(stillPaired({ previous, user: { id: "someone-else" }, installationId, devices: [record] }), false);
  assert.equal(stillPaired({ previous, user, installationId, devices: [{ ...record, revoked_at: "2026-10-23T00:00:00Z" }] }), false,
    "a PC disconnected from the web stays disconnected");
  assert.equal(stillPaired({ previous, user, installationId, devices: [{ ...record, installation_id: "other" }] }), false);
  assert.equal(stillPaired({ previous, user, installationId, devices: [] }), false);
});
