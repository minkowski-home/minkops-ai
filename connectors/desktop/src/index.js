/** Native adapters only. Business approvals and task authority remain server-side. */
import { createHash, randomUUID } from "node:crypto";
import { constants } from "node:fs";
import {
  lstat,
  readdir,
  readFile,
  realpath,
  open,
  rename,
  unlink,
} from "node:fs/promises";
import { join, dirname, sep, extname } from "node:path";
import { XMLParser, XMLValidator } from "fast-xml-parser";

const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const SUPPORTED = /\.(xlsx|pdf|png|jpe?g|webp)$/i;
const EXCLUDED = new Set([
  "ground_truth",
  "ground-truth",
  "pr-infra-sample-bills",
]);
const runningWrites = new Map();

async function workbookBytes(path) {
  if ((await lstat(path)).size > 5_000_000)
    throw new Error("The local workbook is too large.");
  const bytes = await readFile(path, {
    flag: constants.O_RDONLY | (constants.O_NOFOLLOW || 0),
  });
  if (!bytes.length || bytes.length > 5_000_000)
    throw new Error("The local workbook is invalid or too large.");
  return bytes;
}

async function boundedText(response, limit = 1_000_000) {
  if (!response.ok || !response.body)
    throw new Error("Tally did not accept the connection check.");
  const reader = response.body.getReader();
  const parts = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit)
        throw new Error("Tally returned too much data for a connection check.");
      parts.push(Buffer.from(value));
    }
    return Buffer.concat(parts).toString("utf8");
  } finally {
    await reader.cancel().catch(() => {});
  }
}

/** A read-only company export, never a caller-supplied XML request or hostname. */
export async function tallyProbe({ port = 9000, request = fetch } = {}) {
  if (!Number.isInteger(port) || port < 1 || port > 65535)
    throw new Error("Invalid Tally port.");
  const body =
    '<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>MinkopsCompanies</ID></HEADER><BODY><DESC><TDL><TDLMESSAGE><COLLECTION NAME="MinkopsCompanies"><TYPE>Company</TYPE><FETCH>Name</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>';
  const response = await request(`http://127.0.0.1:${port}`, {
    method: "POST",
    body,
    headers: { "Content-Type": "text/xml; charset=utf-8" },
    redirect: "error",
    signal: AbortSignal.timeout(8000),
  });
  const text = await boundedText(response);
  if (/<!DOCTYPE|<!ENTITY/i.test(text) || XMLValidator.validate(text) !== true)
    throw new Error("Tally returned an invalid response.");
  const parsed = new XMLParser({
    ignoreAttributes: false,
    parseTagValue: false,
    trimValues: true,
  }).parse(text);
  const envelope = parsed.ENVELOPE;
  if (
    !envelope ||
    String(envelope.HEADER?.STATUS) !== "1" ||
    /<LINEERROR\b/i.test(text)
  )
    throw new Error("Tally could not list the open companies.");
  const nodes = envelope.BODY?.DATA?.COLLECTION?.COMPANY;
  const list = nodes ? (Array.isArray(nodes) ? nodes : [nodes]) : [];
  const companies = list.map((company) => {
    // With attributes enabled, <NAME TYPE="String"> is an object containing
    // #text. Accept scalar text or this typed-text shape, never object coercion.
    const node = company.NAME;
    let name;
    if (typeof node === "string") name = node;
    else if (node !== undefined) {
      if (
        !node ||
        Array.isArray(node) ||
        typeof node !== "object" ||
        Object.keys(node).some(
          (key) => key !== "#text" && !key.startsWith("@_"),
        ) ||
        (node["#text"] !== undefined && typeof node["#text"] !== "string")
      ) {
        throw new Error("Tally returned an invalid company name.");
      }
      name = node["#text"];
    }
    name = name || company["@_NAME"];
    if (typeof name !== "string" || !name.trim())
      throw new Error("Tally returned an invalid company name.");
    return name.trim();
  });
  if (companies.length > 100 || companies.some((c) => c.length > 200))
    throw new Error("Tally returned an invalid company list.");
  return { available: true, companies };
}

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

/** Save only server-approved bytes. A repeated receipt never repeats an append. */
export async function replaceApproved(root, spec, approved, backup) {
  if (extname(spec.path).toLowerCase() !== ".xlsx")
    throw new Error("Only approved Excel workbooks can be saved.");
  const target = await containedPath(root, spec.path);
  const previous = runningWrites.get(target) || Promise.resolve();
  const operation = previous
    .catch(() => {})
    .then(async () => {
      if (approved.length > 5_000_000 || hash(approved) !== spec.after_sha256)
        throw new Error("Approved workbook failed its integrity check.");
      const current = await workbookBytes(target);
      const currentHash = hash(current);
      if (currentHash === spec.after_sha256) return current;
      if (currentHash !== spec.before_sha256)
        throw new Error(
          "The local workbook changed. Refresh discovery before saving.",
        );
      await backup(current);
      const temporary = join(dirname(target), `.minkops-${randomUUID()}.tmp`);
      try {
        const handle = await open(temporary, "wx", 0o600);
        try {
          await handle.writeFile(approved);
          await handle.sync();
        } finally {
          await handle.close();
        }
        await containedPath(root, spec.path);
        if (hash(await workbookBytes(target)) !== spec.before_sha256)
          throw new Error("The local workbook changed before saving.");
        await rename(temporary, target);
        const saved = await workbookBytes(target);
        if (hash(saved) !== spec.after_sha256)
          throw new Error("The saved workbook could not be verified.");
        return saved;
      } finally {
        await unlink(temporary).catch(() => {});
      }
    });
  runningWrites.set(target, operation);
  try {
    return await operation;
  } finally {
    if (runningWrites.get(target) === operation) runningWrites.delete(target);
  }
}
