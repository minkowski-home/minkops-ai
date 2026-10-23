/** This PC's pairing with one Minkops server, kept across restarts and power cuts.
 *
 * Two files in the app profile:
 * - companion.bin: the encrypted state (credential, folder grants, an unsent receipt);
 * - installation.json: the plain, non-secret identity (installation ID and the PC record it is paired as).
 *
 * The identity outlives the credential. When companion.bin cannot be read, it is set aside rather than
 * overwritten, and reconnecting reuses the same installation ID, so the server reissues a credential for the
 * same PC record instead of adding a second, "offline" one. Every write is flushed to disk before it replaces
 * the previous file, so an unexpected shutdown leaves the old or the new version, never a damaged one.
 *
 * From 0.11.2 the installation ID is derived from the machine and the Windows user (machineInstallationId), so every
 * profile of that user on that PC, from a reinstall, a wiped profile or a launch inside another app's container, is
 * the same PC record: its companies stay authorised, and no continuation is needed. A record paired under a
 * profile's random ID moves to the machine identity once it is connected (POST /api/desktop/worker/installation).
 *
 * From 0.11.3 both files record the machine they were saved on, and a state saved on another PC is never used: its
 * credential would claim that PC's Tally jobs and write to this PC's Tally. The files live outside the roaming
 * profile (machine-state.js), but a profile container, a restored backup or a copied folder can still carry them.
 */
import { createHash, randomUUID } from "node:crypto";
import { execFile } from "node:child_process";
import { hostname, userInfo } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { readFile, rename } from "node:fs/promises";
import { durableWrite } from "./machine-state.js";

const machineGuid = async () =>
  (await promisify(execFile)("reg", ["query", "HKLM\\SOFTWARE\\Microsoft\\Cryptography", "/v", "MachineGuid"],
    { windowsHide: true, timeout: 5000 })).stdout;

/**
 * This PC's installation ID for this Windows user, or null where the machine cannot be identified.
 *
 * A name-based (version 5) UUID of Windows' MachineGuid, the computer name and the account. The account separates
 * users on a shared server; the computer name separates clones of one image that kept the MachineGuid, which must
 * never share a record, since a record's jobs would then reach another Tally copy. A renamed PC is a new PC.
 */
export async function machineInstallationId({ query = machineGuid, host, account } = {}) {
  try {
    const guid = /MachineGuid\s+REG_SZ\s+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i.exec(await query())?.[1];
    if (!guid) return null;
    const name = [
      "minkops-installation",
      guid,
      host ?? hostname(),
      account ?? `${process.env.USERDOMAIN ?? ""}\\${userInfo().username}`,
    ];
    const bytes = createHash("sha1").update(name.join("\0").toLowerCase()).digest().subarray(0, 16);
    bytes[6] = (bytes[6] & 0x0f) | 0x50;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = bytes.toString("hex");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  } catch {
    return null;
  }
}

async function readOptional(path) {
  try {
    return await readFile(path);
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

/** The PC record a credential belongs to, without the credential. */
const recordOf = (device) => (device ? { id: device.id, tenant: device.tenant, owner_id: device.owner_id } : null);

/** The machine a saved file was made on, or null: recorded from 0.11.3, and implied before it by an installation ID
 * derived from the machine (version 5; a profile's own IDs are random, version 4). */
const savedOn = (saved) =>
  saved?.machine ?? (/^[0-9a-f]{8}-[0-9a-f]{4}-5/i.test(saved?.installation_id ?? "") ? saved.installation_id : null);

/**
 * Load this PC's pairing with `origin`. `cipher` is Windows credential storage: {available, encrypt, decrypt};
 * `machine` is machineInstallationId(), or null.
 *
 * The result holds the live `state` (change it, then `save()`), `problem` (why the saved connection could not be
 * read, for diagnostics) and `previous`: the PC record whose credential was lost, to reconnect as. Set
 * `previous` to null, and save, once that record is reconnected, disconnected or no longer this PC's.
 */
export async function openPairing({ directory, origin, cipher, machine = null, now = () => new Date() }) {
  const secretPath = join(directory, "companion.bin");
  const identityPath = join(directory, "installation.json");
  // Where this PC cannot be identified, nothing can be told apart, and a saved file is taken as this PC's.
  const elsewhere = (saved) => Boolean(machine && savedOn(saved) && savedOn(saved) !== machine);
  let found = null;
  try {
    const parsed = JSON.parse((await readOptional(identityPath))?.toString() ?? "null");
    // Credentials and grants belong to one server: another deployment's identity is never reused.
    if (parsed?.server_origin === origin) found = parsed;
  } catch {
    /* A damaged identity file is rebuilt from the credential, or anew. */
  }
  // A record belongs to one PC: another PC's identity is never reconnected from here.
  let identity = elsewhere(found) ? null : found;

  let restored = null;
  let problem = null;
  /** Kept for support, and out of the way so that no later save overwrites it. */
  const setAside = (reason) =>
    rename(secretPath, `${secretPath}.${reason}-${now().toISOString().slice(0, 19).replace(/:/g, "-")}Z`);
  const encrypted = await readOptional(secretPath);
  // Storage that is unavailable for now leaves the saved file intact: nothing is lost, so nothing is recovered.
  const locked = Boolean(encrypted) && !cipher.available();
  if (locked) {
    problem = "Windows credential storage is unavailable.";
  } else if (encrypted) {
    let parsed;
    try {
      parsed = JSON.parse(cipher.decrypt(encrypted));
    } catch {
      problem = "This PC's saved connection could not be read.";
      await setAside("unreadable");
    }
    // A credential saved before 0.11.3 recorded no machine; the identity beside it records one from the first start.
    if (parsed?.server_origin === origin && elsewhere({ machine: savedOn(parsed) ?? savedOn(found) })) {
      problem = "This PC's saved connection was made on another PC.";
      await setAside("other-pc");
      // The identity beside it came with it: reconnecting its record from here would take that PC's record over.
      identity = null;
    } else if (parsed?.server_origin === origin) {
      restored = parsed;
    }
  }
  // Saves record the machine they are made on, or, where this start cannot read it, the one recorded before.
  const savedMachine = machine ?? savedOn(restored) ?? savedOn(identity);
  if (restored) delete restored.machine;

  const previous = restored || locked ? null : (identity?.device ?? null);
  const state = restored ?? {
    server_origin: origin,
    installation_id: identity?.installation_id ?? randomUUID(),
    device: null,
    bindings: {},
    pending: null,
  };
  // A record this profile is connected as, or reconnects as, keeps the ID the server knows it by until it moves to
  // the machine identity; an unpaired profile connects as the machine.
  if (machine && !locked && !state.device && !previous) state.installation_id = machine;
  const pairing = { state, previous, problem, machine, save };
  let written = identity && JSON.stringify(identity);
  async function writeIdentity() {
    const next = JSON.stringify({
      server_origin: origin,
      installation_id: pairing.state.installation_id,
      machine: savedMachine,
      device: recordOf(pairing.state.device) ?? pairing.previous,
    });
    if (next === written) return;
    await durableWrite(identityPath, next);
    written = next;
  }
  let persistence = Promise.resolve();
  /** Save the state. Saves run in order, and a failed one does not block the next. */
  function save() {
    persistence = persistence
      .catch(() => {})
      .then(async () => {
        if (!cipher.available()) throw new Error("Windows credential storage is unavailable.");
        await durableWrite(secretPath, cipher.encrypt(JSON.stringify({ ...pairing.state, machine: savedMachine })));
        await writeIdentity();
      });
    return persistence;
  }
  // A new installation, or one connected by a release before 0.11.1, records its identity at once.
  if (!locked) await writeIdentity();
  return pairing;
}

/** Whether a credential this PC lost may be reissued: the same owner's PC record, still connected on the server.
 * A PC disconnected from the web (revoked) or removed stays disconnected until someone connects it again. */
export function stillPaired({ previous, user, installationId, devices }) {
  if (!previous || previous.owner_id !== user?.id) return false;
  return devices.some(
    (record) =>
      record.id === previous.id &&
      record.owner_id === user.id &&
      record.installation_id === installationId &&
      !record.revoked_at,
  );
}
