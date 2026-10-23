import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, readdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openPairing, stillPaired, machineInstallationId } from "../src/pairing.js";

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
    machine: null,
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

test("every profile of one Windows user on one PC derives the same installation ID", async () => {
  const reg = (guid) => async () => `\r\nHKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography\r\n    MachineGuid    REG_SZ    ${guid}\r\n`;
  const guid = "6f1d2a4e-0b5c-4c7e-9f00-1234567890ab";
  const pc = { query: reg(guid), host: "GAUSS-PC-Sikar", account: "GAUSS-PC\\karti" };
  const id = await machineInstallationId(pc);
  // Name-based (version 5): the server moves a record to it once, and never between machines.
  assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.equal(await machineInstallationId({ query: reg(guid.toUpperCase()), host: "gauss-pc-sikar", account: "gauss-pc\\KARTI" }), id);
  // Each Windows user on a shared server is a PC of its own, and so is another machine.
  assert.notEqual(await machineInstallationId({ ...pc, account: "GAUSS-PC\\accounts2" }), id);
  assert.notEqual(await machineInstallationId({ ...pc, query: reg("00000000-0b5c-4c7e-9f00-1234567890ab") }), id);
  // A clone that was not generalised keeps the MachineGuid; its network name sets it apart.
  assert.notEqual(await machineInstallationId({ ...pc, host: "TALLY-SERVER-2" }), id);
  // Unreadable (not Windows, or no registry access): the profile's own ID stands.
  assert.equal(await machineInstallationId({ ...pc, query: async () => { throw new Error("reg failed"); } }), null);
  assert.equal(await machineInstallationId({ ...pc, query: async () => "no guid here" }), null);
});

test("an unpaired profile connects with the machine identity; a paired one keeps its record's ID", async (t) => {
  const machine = "44444444-4444-5444-8444-444444444444";
  const fresh = await openPairing({ directory: await profile(t), origin, cipher, machine });
  assert.equal(fresh.state.installation_id, machine);

  const directory = await profile(t);
  const paired = await openPairing({ directory, origin, cipher });
  const own = paired.state.installation_id;
  paired.state.device = device;
  await paired.save();
  // Its server record still has the profile's ID until the companion moves it (POST /api/desktop/worker/installation).
  assert.equal((await openPairing({ directory, origin, cipher, machine })).state.installation_id, own);
  // Reconnecting a lost credential must find that record, so it keeps the profile's ID too.
  await writeFile(join(directory, "companion.bin"), "garbage");
  assert.equal((await openPairing({ directory, origin, cipher, machine })).state.installation_id, own);

  const unpaired = await profile(t);
  const once = await openPairing({ directory: unpaired, origin, cipher });
  await once.save();
  assert.equal((await openPairing({ directory: unpaired, origin, cipher, machine })).state.installation_id, machine);
});

test("a connection saved on another PC is set aside and never used or reconnected here", async (t) => {
  const pcA = "55555555-5555-5555-8555-555555555555";
  const pcB = "66666666-6666-5666-8666-666666666666";
  const directory = await profile(t);
  const onA = await openPairing({ directory, origin, cipher, machine: pcA });
  onA.state.device = device;
  await onA.save();
  // Every save records the machine it was made on, in the credential and in the plain identity.
  assert.equal(JSON.parse(await readFile(join(directory, "installation.json"), "utf8")).machine, pcA);
  assert.equal((await openPairing({ directory, origin, cipher, machine: pcA })).state.device.credential, device.credential);

  // The profile reaches PC B: a profile container, a restored backup or a copied folder.
  const onB = await openPairing({ directory, origin, cipher, machine: pcB, now: () => new Date("2026-10-23T05:00:00Z") });
  assert.match(onB.problem, /another PC/);
  assert.equal(onB.state.device, null, "PC A's credential would claim its jobs and write to another Tally");
  assert.equal(onB.previous, null, "nor is PC A's record reconnected from here");
  assert.equal(onB.state.installation_id, pcB, "connecting registers PC B as itself");
  await onB.save();
  const files = (await readdir(directory)).sort();
  assert.deepEqual(files, ["companion.bin", "companion.bin.other-pc-2026-10-23T05-00-00Z", "installation.json"]);
  assert.equal(JSON.parse(cipher.decrypt(await readFile(join(directory, files[1])))).device.credential, device.credential,
    "set aside, never overwritten");
});

test("another PC's identity is never used to reconnect, even when its credential cannot be read", async (t) => {
  const directory = await profile(t);
  const onA = await openPairing({ directory, origin, cipher, machine: "55555555-5555-5555-8555-555555555555" });
  onA.state.device = device;
  await onA.save();
  await writeFile(join(directory, "companion.bin"), "garbage");
  const onB = await openPairing({ directory, origin, cipher, machine: "66666666-6666-5666-8666-666666666666" });
  assert.equal(onB.previous, null);
  assert.equal(onB.state.installation_id, "66666666-6666-5666-8666-666666666666");
});

test("a connection saved by 0.11.2 on another PC is recognised by its machine installation ID", async (t) => {
  const directory = await profile(t);
  // 0.11.2 recorded no machine, but a version 5 installation ID is the machine it was derived on.
  const legacy = { server_origin: origin, installation_id: "55555555-5555-5555-8555-555555555555", device, bindings: {}, pending: null };
  await writeFile(join(directory, "companion.bin"), cipher.encrypt(JSON.stringify(legacy)));
  await writeFile(join(directory, "installation.json"), JSON.stringify({ server_origin: origin, installation_id: legacy.installation_id, device: null }));
  const elsewhere = await openPairing({ directory, origin, cipher, machine: "66666666-6666-5666-8666-666666666666" });
  assert.equal(elsewhere.state.device, null);
  assert.match(elsewhere.problem, /another PC/);
  const home = await profile(t);
  await writeFile(join(home, "companion.bin"), cipher.encrypt(JSON.stringify(legacy)));
  assert.deepEqual((await openPairing({ directory: home, origin, cipher, machine: legacy.installation_id })).state, legacy);
});

test("a connection whose machine is unknown is kept, and records this PC from its next save", async (t) => {
  const directory = await profile(t);
  // Paired before 0.11.2 under a random ID, not yet moved to the machine identity.
  const legacy = { server_origin: origin, installation_id: "33333333-3333-4333-8333-333333333333", device, bindings: {}, pending: null };
  await writeFile(join(directory, "companion.bin"), cipher.encrypt(JSON.stringify(legacy)));
  const here = await openPairing({ directory, origin, cipher, machine: "55555555-5555-5555-8555-555555555555" });
  assert.deepEqual(here.state, legacy);
  await here.save();
  assert.equal((await openPairing({ directory, origin, cipher, machine: "66666666-6666-5666-8666-666666666666" })).state.device, null);
});

test("a start that cannot read the machine keeps the connection and the machine it recorded", async (t) => {
  const directory = await profile(t);
  const pcA = "55555555-5555-5555-8555-555555555555";
  const first = await openPairing({ directory, origin, cipher, machine: pcA });
  first.state.device = device;
  await first.save();
  const unknown = await openPairing({ directory, origin, cipher, machine: null });
  assert.equal(unknown.state.device.credential, device.credential);
  unknown.state.pending = { job: "j" };
  await unknown.save();
  assert.equal(JSON.parse(await readFile(join(directory, "installation.json"), "utf8")).machine, pcA);
  assert.equal((await openPairing({ directory, origin, cipher, machine: "66666666-6666-5666-8666-666666666666" })).state.device, null);
});

test("a credential that recorded no machine belongs to the machine its identity file names", async (t) => {
  const directory = await profile(t);
  const legacy = { server_origin: origin, installation_id: "33333333-3333-4333-8333-333333333333", device, bindings: {}, pending: null };
  await writeFile(join(directory, "companion.bin"), cipher.encrypt(JSON.stringify(legacy)));
  // Opening on PC A records it in the identity at once, before the credential is next saved.
  await openPairing({ directory, origin, cipher, machine: "55555555-5555-5555-8555-555555555555" });
  const onB = await openPairing({ directory, origin, cipher, machine: "66666666-6666-5666-8666-666666666666" });
  assert.equal(onB.state.device, null);
  assert.equal(onB.previous, null);
});
