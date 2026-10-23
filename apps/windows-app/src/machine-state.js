/** Where this PC's machine-bound companion state lives (0.11.3+), and its one move there from the roaming profile.
 *
 * The device credential, folder grants and unsent receipt (companion.bin), the identity (installation.json), the
 * save fences (statement-manifests) and Tally diagnostics belong to one PC. Electron's userData is %APPDATA%
 * (Roaming), which roaming profiles and AppData folder redirection carry to every PC the user signs in to, where a
 * roamed credential would claim this PC's Tally jobs and write to another Tally copy. So the state lives under
 * %LOCALAPPDATA%, which stays on the PC. Chromium's session and cache, which are the user's, stay in userData.
 *
 * Profile containers (FSLogix, user profile disks) carry Local too; pairing.js refuses a state saved on another PC.
 */
import { homedir } from "node:os";
import { basename, join } from "node:path";
import { lstat, mkdir, open, readFile, readdir, rename, rmdir, unlink } from "node:fs/promises";

/** Write `data` to `path` so that a power cut leaves the previous version or this one: flushed before it replaces. */
export async function durableWrite(path, data, { modified } = {}) {
  const temporary = path + ".tmp";
  const handle = await open(temporary, "w", 0o600);
  try {
    await handle.writeFile(data);
    if (modified) await handle.utimes(modified, modified);
    await handle.sync();
  } finally {
    await handle.close();
  }
  await rename(temporary, path);
}

// What earlier releases kept in userData that belongs to the PC. Half-written saves (*.tmp) were never a saved
// state, but may hold a credential, so they are removed from the roaming profile rather than moved.
const MACHINE_BOUND = /^(companion\.bin|installation\.json|statement-manifests|tally-diagnostics|companion\.bin\.unreadable-.+)$/;
const HALF_WRITTEN = /^(companion\.bin|installation\.json)\.tmp$/;
const MARKER = "migrated.json";

/** For a file that is already gone, true; any other failure is rethrown. */
const gone = (error) => {
  if (error.code === "ENOENT") return true;
  throw error;
};

/** Move one file or folder, never overwriting what is already here. Returns whether the source is gone.
 *
 * With folder redirection, userData is a share another PC may be moving from at the same time: a source that
 * disappears was moved there, and is gone as far as this PC is concerned. */
async function move(source, target) {
  const kind = await lstat(source).catch(gone);
  if (kind === true) return true;
  if (kind.isDirectory()) {
    await mkdir(target, { recursive: true });
    let complete = true;
    for (const name of await readdir(source).catch((error) => gone(error) && []))
      complete = (await move(join(source, name), join(target, name))) && complete;
    // Something saved into it meanwhile keeps it, as anything not moved does.
    return complete && rmdir(source).then(() => true, (error) => (error.code === "ENOTEMPTY" ? false : gone(error)));
  }
  // Nothing but files and folders is written here; anything else is not ours to move.
  if (!kind.isFile()) return false;
  const data = await readFile(source).catch(gone);
  if (data === true) return true;
  const present = await readFile(target).catch((error) => gone(error) && null);
  // An identical copy is the same move interrupted after the copy; a different one is this PC's own and wins.
  if (present && !present.equals(data)) return false;
  if (!present) await durableWrite(target, data, { modified: kind.mtime });
  await unlink(source).catch(gone);
  return true;
}

/**
 * The folder for this PC's machine-bound state, given Electron's userData. On Windows, `%LOCALAPPDATA%\<the
 * profile's name>`, so the dev channel's "Minkops Dev" keeps its own; elsewhere there is no roaming, and userData
 * serves as it is.
 *
 * The first start moves an earlier release's state there, once: a record (migrated.json), written after everything
 * moved, keeps a state an older companion later roams into userData from ever being adopted. Each file is flushed
 * here before its roaming copy is removed, so an interruption is resumed on the next start. A file that cannot be
 * read fails the start: the move must not leave a save fence behind, or a voucher could be imported twice.
 */
export async function machineStateDirectory({ userData, platform = process.platform, env = process.env,
  home = homedir(), now = () => new Date() }) {
  if (platform !== "win32") return userData;
  const local = env.LOCALAPPDATA || join(home, "AppData", "Local");
  const directory = join(local, basename(userData));
  await mkdir(directory, { recursive: true });
  if (await lstat(join(directory, MARKER)).then(() => true, (error) => !gone(error))) return directory;
  for (const name of await readdir(userData).catch((error) => gone(error) && [])) {
    if (HALF_WRITTEN.test(name)) await unlink(join(userData, name)).catch(gone);
    else if (MACHINE_BOUND.test(name)) await move(join(userData, name), join(directory, name));
  }
  await durableWrite(join(directory, MARKER), JSON.stringify({ from: userData, at: now().toISOString() }));
  return directory;
}
