/** Native adapters only. Business approvals and task authority remain server-side. */
import { constants } from "node:fs";
import { lstat, readdir, readFile, realpath } from "node:fs/promises";
import { join, sep } from "node:path";
// The Windows companion's native surface. Tests import implementation modules
// directly; only what the companion and its operator scripts call is exported.
export { readTallyReferences } from './tally-references.js';
export { checkTally, requireOpenCompany, readOpenCompanies, tallyTransport, tallyProcesses, tallyCrashEvents, readTallyIni } from './tally-session.js';

const SUPPORTED = /\.(xlsx|csv|pdf|png|jpe?g|webp)$/i;
const EXCLUDED = new Set([
  "ground_truth",
  "ground-truth",
  "pr-infra-sample-bills",
]);

function relativeParts(path) {
  if (
    typeof path !== "string" ||
    !path ||
    path.length > 1000 ||
    path.includes("\\") ||
    path.includes(":")
  )
    throw new Error("Invalid source path.");
  const parts = path.split("/");
  if (
    parts.some(
      (p) =>
        !p ||
        p === "." ||
        p === ".." ||
        p.startsWith(".") ||
        /[\x00-\x1f]/.test(p) ||
        /[. ]$/.test(p),
    )
  )
    throw new Error("Invalid source path.");
  return parts;
}

async function containedPath(root, path) {
  const canonical = await realpath(root);
  if ((await lstat(root)).isSymbolicLink())
    throw new Error("Source folder links are not allowed.");
  let target = canonical;
  for (const part of relativeParts(path)) {
    target = join(target, part);
    if ((await lstat(target)).isSymbolicLink())
      throw new Error("Source file links are not allowed.");
  }
  const actual = await realpath(target);
  if (!actual.startsWith(canonical + sep))
    throw new Error("File is outside the granted folder.");
  return actual;
}

/** Stable, limited file snapshots from an explicitly granted directory. */
export async function inventory(root) {
  const canonical = await realpath(root);
  if ((await lstat(root)).isSymbolicLink())
    throw new Error("Source folder links are not allowed.");
  const files = [];
  let total = 0;
  async function walk(directory, prefix = "", depth = 0) {
    if (depth > 12)
      throw new Error("Choose a folder with fewer nested directories.");
    const entries = (await readdir(directory, { withFileTypes: true })).sort(
      (a, b) => a.name.localeCompare(b.name),
    );
    for (const entry of entries) {
      if (entry.name.startsWith(".") || EXCLUDED.has(entry.name)) continue;
      const path = prefix ? `${prefix}/${entry.name}` : entry.name;
      relativeParts(path);
      if (entry.isSymbolicLink())
        throw new Error(
          "Folder links are not allowed. Choose a direct folder.",
        );
      if (entry.isDirectory())
        await walk(await containedPath(canonical, path), path, depth + 1);
      else if (entry.isFile() && SUPPORTED.test(entry.name)) {
        const full = await containedPath(canonical, path);
        const stat = await lstat(full);
        if (
          !stat.size ||
          stat.size > 5_000_000 ||
          (total += stat.size) > 30_000_000 ||
          files.length >= 100
        )
          throw new Error(
            "Choose a smaller folder: 100 files, 5 MB per file, and 30 MB total.",
          );
        const content = await readFile(full, {
          flag: constants.O_RDONLY | (constants.O_NOFOLLOW || 0),
        });
        if (content.length !== stat.size)
          throw new Error("A file changed during reading. Refresh the folder.");
        files.push({ path, content: content.toString("base64") });
      }
    }
  }
  await walk(canonical);
  if (!files.length)
    throw new Error("No Excel, PDF or image files were found.");
  return files;
}

export { createSupplier } from "./tally.js";
export { saveVoucher } from "./voucher.js";
export { runSync } from "./sync.js";
