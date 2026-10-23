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
 */
import { randomUUID } from "node:crypto";
import { join } from "node:path";
import { open, readFile, rename } from "node:fs/promises";

async function durableWrite(path, data) {
  const temporary = path + ".tmp";
  const handle = await open(temporary, "w", 0o600);
  try {
    await handle.writeFile(data);
    await handle.sync();
  } finally {
    await handle.close();
  }
  await rename(temporary, path);
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

/**
 * Load this PC's pairing with `origin`. `cipher` is Windows credential storage: {available, encrypt, decrypt}.
 *
 * The result holds the live `state` (change it, then `save()`), `problem` (why the saved connection could not be
 * read, for diagnostics) and `previous`: the PC record whose credential was lost, to reconnect as. Set
 * `previous` to null, and save, once that record is reconnected, disconnected or no longer this PC's.
 */
export async function openPairing({ directory, origin, cipher, now = () => new Date() }) {
  const secretPath = join(directory, "companion.bin");
  const identityPath = join(directory, "installation.json");
  let identity = null;
  try {
    const parsed = JSON.parse((await readOptional(identityPath))?.toString() ?? "null");
    // Credentials and grants belong to one server: another deployment's identity is never reused.
    if (parsed?.server_origin === origin) identity = parsed;
  } catch {
    /* A damaged identity file is rebuilt from the credential, or anew. */
  }

  let restored = null;
  let problem = null;
  const encrypted = await readOptional(secretPath);
  // Storage that is unavailable for now leaves the saved file intact: nothing is lost, so nothing is recovered.
  const locked = Boolean(encrypted) && !cipher.available();
  if (locked) {
    problem = "Windows credential storage is unavailable.";
  } else if (encrypted) {
    try {
      const parsed = JSON.parse(cipher.decrypt(encrypted));
      if (parsed?.server_origin === origin) restored = parsed;
    } catch {
      problem = "This PC's saved connection could not be read.";
      // Kept for support, and out of the way so that no later save overwrites it.
      const stamp = now().toISOString().slice(0, 19).replace(/:/g, "-") + "Z";
      await rename(secretPath, `${secretPath}.unreadable-${stamp}`);
    }
  }

  const pairing = {
    state: restored ?? {
      server_origin: origin,
      installation_id: identity?.installation_id ?? randomUUID(),
      device: null,
      bindings: {},
      pending: null,
    },
    previous: restored || locked ? null : (identity?.device ?? null),
    problem,
    save,
  };
  let written = identity && JSON.stringify(identity);
  async function writeIdentity() {
    const next = JSON.stringify({
      server_origin: origin,
      installation_id: pairing.state.installation_id,
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
        await durableWrite(secretPath, cipher.encrypt(JSON.stringify(pairing.state)));
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
