import test from "node:test";
import assert from "node:assert/strict";
import { chmod, mkdir, mkdtemp, readFile, readdir, rm, stat, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { machineStateDirectory } from "../src/machine-state.js";

// A Windows user's two app-data roots: Roaming (Electron's userData lives here) and Local.
async function windowsProfile(t, name = "Minkops") {
  const home = await mkdtemp(join(tmpdir(), "minkops-profile-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const roaming = join(home, "AppData", "Roaming");
  const local = join(home, "AppData", "Local");
  const userData = join(roaming, name);
  await mkdir(userData, { recursive: true });
  await mkdir(local, { recursive: true });
  return { home, userData, local, env: { LOCALAPPDATA: local }, platform: "win32" };
}

const at = () => new Date("2026-10-23T06:00:00Z");
const tree = async (directory) => (await readdir(directory, { recursive: true })).sort();

test("machine-bound state lives under Local app data, beside a separate Minkops Dev", async (t) => {
  const production = await windowsProfile(t);
  assert.equal(await machineStateDirectory({ ...production, now: at }), join(production.local, "Minkops"));
  // The dev channel keeps its own profile name, so it never shares the production companion's state.
  const dev = await windowsProfile(t, "Minkops Dev");
  assert.equal(await machineStateDirectory({ ...dev, now: at }), join(dev.local, "Minkops Dev"));
});

test("without LOCALAPPDATA, Windows' default Local folder under the profile is used", async (t) => {
  const profile = await windowsProfile(t);
  assert.equal(await machineStateDirectory({ ...profile, env: {}, now: at }), join(profile.local, "Minkops"));
});

test("outside Windows there is no roaming profile, and userData is used as it is", async (t) => {
  const profile = await windowsProfile(t);
  await writeFile(join(profile.userData, "companion.bin"), "state");
  assert.equal(await machineStateDirectory({ ...profile, platform: "linux", now: at }), profile.userData);
  assert.deepEqual(await readdir(profile.userData), ["companion.bin"]);
});

test("an earlier release's state moves out of the roaming profile, byte for byte", async (t) => {
  const profile = await windowsProfile(t);
  const roaming = profile.userData;
  await writeFile(join(roaming, "companion.bin"), "encrypted-state");
  await writeFile(join(roaming, "installation.json"), '{"installation_id":"x"}');
  await writeFile(join(roaming, "companion.bin.unreadable-2026-10-01T00-00-00Z"), "kept-for-support");
  // Half-written saves hold a credential but were never a saved state.
  await writeFile(join(roaming, "companion.bin.tmp"), "partial");
  await mkdir(join(roaming, "statement-manifests"));
  await writeFile(join(roaming, "statement-manifests", "remote-1.bin"), "intent-1");
  await mkdir(join(roaming, "tally-diagnostics"));
  await writeFile(join(roaming, "tally-diagnostics", "job-1.json"), "{}");
  const recorded = new Date("2026-09-01T10:00:00Z");
  await utimes(join(roaming, "tally-diagnostics", "job-1.json"), recorded, recorded);
  // Chromium's session and cache are not machine-bound state and stay where they are.
  await mkdir(join(roaming, "Local Storage", "leveldb"), { recursive: true });
  await writeFile(join(roaming, "Local Storage", "leveldb", "000003.log"), "session");
  await writeFile(join(roaming, "Preferences"), "{}");

  const directory = await machineStateDirectory({ ...profile, now: at });
  assert.deepEqual(await tree(directory), [
    "companion.bin",
    "companion.bin.unreadable-2026-10-01T00-00-00Z",
    "installation.json",
    "migrated.json",
    "statement-manifests",
    join("statement-manifests", "remote-1.bin"),
    "tally-diagnostics",
    join("tally-diagnostics", "job-1.json"),
  ]);
  assert.equal(await readFile(join(directory, "companion.bin"), "utf8"), "encrypted-state");
  assert.equal(await readFile(join(directory, "statement-manifests", "remote-1.bin"), "utf8"), "intent-1");
  // Send diagnostics picks the most recent records by modification time.
  assert.equal((await stat(join(directory, "tally-diagnostics", "job-1.json"))).mtimeMs, recorded.getTime());
  assert.deepEqual(JSON.parse(await readFile(join(directory, "migrated.json"), "utf8")), {
    from: roaming,
    at: "2026-10-23T06:00:00.000Z",
  });
  // Nothing machine-bound is left for the roaming profile to carry to another PC.
  assert.deepEqual(await tree(roaming), ["Local Storage", join("Local Storage", "leveldb"), join("Local Storage", "leveldb", "000003.log"), "Preferences"]);
});

test("the move happens once: state an older companion later roams in is never adopted", async (t) => {
  const profile = await windowsProfile(t);
  const directory = await machineStateDirectory({ ...profile, now: at });
  assert.deepEqual(await readdir(directory), ["migrated.json"], "a new installation records that it has nothing to move");
  // Another PC still running 0.11.2 saves its credential in the shared roaming profile.
  await writeFile(join(profile.userData, "companion.bin"), "another-pcs-state");
  assert.equal(await machineStateDirectory({ ...profile, now: at }), directory);
  assert.deepEqual(await readdir(directory), ["migrated.json"]);
  assert.equal(await readFile(join(profile.userData, "companion.bin"), "utf8"), "another-pcs-state", "nor is it touched");
});

test("an interrupted move resumes without losing or duplicating anything", async (t) => {
  const profile = await windowsProfile(t);
  const local = join(profile.local, "Minkops");
  // A power cut after the credential was copied and flushed, before its roaming copy was removed.
  await mkdir(local, { recursive: true });
  await writeFile(join(local, "companion.bin"), "encrypted-state");
  await writeFile(join(local, "companion.bin.tmp"), "partial");
  await writeFile(join(profile.userData, "companion.bin"), "encrypted-state");
  await writeFile(join(profile.userData, "installation.json"), "{}");

  await machineStateDirectory({ ...profile, now: at });
  assert.deepEqual(await readdir(profile.userData), []);
  assert.equal(await readFile(join(local, "companion.bin"), "utf8"), "encrypted-state");
  assert.equal(await readFile(join(local, "installation.json"), "utf8"), "{}");
});

test("a file already on this PC is never overwritten, and its roaming counterpart is left alone", async (t) => {
  const profile = await windowsProfile(t);
  const local = join(profile.local, "Minkops");
  await mkdir(join(local, "statement-manifests"), { recursive: true });
  await writeFile(join(local, "statement-manifests", "remote-1.bin"), "local-intent");
  await mkdir(join(profile.userData, "statement-manifests"));
  await writeFile(join(profile.userData, "statement-manifests", "remote-1.bin"), "roaming-intent");
  await writeFile(join(profile.userData, "statement-manifests", "remote-2.bin"), "intent-2");

  await machineStateDirectory({ ...profile, now: at });
  assert.equal(await readFile(join(local, "statement-manifests", "remote-1.bin"), "utf8"), "local-intent");
  assert.equal(await readFile(join(local, "statement-manifests", "remote-2.bin"), "utf8"), "intent-2");
  assert.deepEqual(await tree(profile.userData), ["statement-manifests", join("statement-manifests", "remote-1.bin")]);
});

test("a roaming file that cannot be read stops the start, and nothing is lost or marked moved", {
  skip: process.platform === "win32" || process.getuid?.() === 0 ? "needs POSIX permissions as a non-root user" : false,
}, async (t) => {
  const profile = await windowsProfile(t);
  await writeFile(join(profile.userData, "installation.json"), "{}");
  await mkdir(join(profile.userData, "statement-manifests"));
  const blocked = join(profile.userData, "statement-manifests", "remote-1.bin");
  await writeFile(blocked, "intent-1");
  await chmod(blocked, 0o000);

  // A save fence that did not arrive could let a voucher be imported twice, so the companion does not start without it.
  await assert.rejects(machineStateDirectory({ ...profile, now: at }), { code: "EACCES" });
  const local = join(profile.local, "Minkops");
  assert.equal((await readdir(local)).includes("migrated.json"), false);
  await chmod(blocked, 0o600);
  assert.equal(await readFile(blocked, "utf8"), "intent-1");

  // Once it can be read, the next start completes the move.
  await machineStateDirectory({ ...profile, now: at });
  assert.equal(await readFile(join(local, "statement-manifests", "remote-1.bin"), "utf8"), "intent-1");
  assert.deepEqual(await readdir(profile.userData), []);
});
