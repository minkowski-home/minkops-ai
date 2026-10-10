/** Native, read-only Tally exports and immutable local discovery packages.
 * Report names/variables are fixed here; callers cannot supply XML, TDL or URLs.
 * Keep native nested data intact. This is evidence, never an accounting engine.
 */
import { createHash, randomUUID } from "node:crypto";
import {
  mkdir,
  writeFile,
  readFile,
  rename,
  rm,
  lstat,
} from "node:fs/promises";
import { join } from "node:path";
import { XMLParser, XMLValidator } from "fast-xml-parser";
import { tallyProbe, boundedText } from "./index.js";
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const escape = (s) =>
  s.replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&apos;",
      })[c],
  );
const scalar = (v) => (typeof v === "string" ? v : v?.["#text"]);
const array = (v) => (v == null ? [] : Array.isArray(v) ? v : [v]);
const parser = new XMLParser({
  ignoreAttributes: false,
  parseTagValue: false,
  parseAttributeValue: false,
  trimValues: false,
});
function date(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value))
    throw new Error("Invalid period.");
  const parsed = new Date(value + "T00:00:00Z");
  if (!Number.isFinite(+parsed) || parsed.toISOString().slice(0, 10) !== value)
    throw new Error("Invalid period.");
  return parsed;
}
export async function discoverClientContext(
  config,
  { request = fetch, onProgress = async () => {} } = {},
) {
  if (
    !config ||
    Object.keys(config).some((k) => !["port", "period"].includes(k)) ||
    !Number.isInteger(config.port) ||
    config.port < 1 ||
    config.port > 65535 ||
    !config.period ||
    Object.keys(config.period).sort().join(",") !== "from,to"
  )
    throw new Error("Invalid discovery configuration.");
  const from = date(config.period.from),
    to = date(config.period.to);
  if (from > to || (to - from) / 86400000 > 3660)
    throw new Error("Invalid period.");
  const probe = await tallyProbe({ port: config.port, request });
  if (!probe.companies.length || probe.companies.length > 50)
    throw new Error("Load between one and 50 authorised companies in Tally.");
  const companies = [];
  let totalBytes = 0;
  async function exportData(company, id, period = null, identity = false) {
    const variables =
      `<SVCURRENTCOMPANY>${escape(company)}</SVCURRENTCOMPANY><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>` +
      (period
        ? `<SVFROMDATE TYPE="Date">${period.from.replaceAll("-", "")}</SVFROMDATE><SVTODATE TYPE="Date">${period.to.replaceAll("-", "")}</SVTODATE><EXPLODEFLAG>Yes</EXPLODEFLAG><SVEXPORTWITHCANCELLED>Yes</SVEXPORTWITHCANCELLED><SVEXPORTWITHOPTIONAL>Yes</SVEXPORTWITHOPTIONAL>`
        : id === "List of Accounts"
          ? "<ACCOUNTTYPE>All Masters</ACCOUNTTYPE>"
          : "");
    const body = `<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>${identity ? "Collection" : "Data"}</TYPE><ID>${id}</ID></HEADER><BODY><DESC><STATICVARIABLES>${variables}</STATICVARIABLES>${identity ? '<TDL><TDLMESSAGE><COLLECTION NAME="MinkopsIdentity"><TYPE>Company</TYPE><FETCH>*</FETCH></COLLECTION></TDLMESSAGE></TDL>' : ""}</DESC></BODY></ENVELOPE>`;
    const response = await request(`http://127.0.0.1:${config.port}`, {
      method: "POST",
      body,
      headers: { "Content-Type": "text/xml; charset=utf-8" },
      redirect: "error",
      signal: AbortSignal.timeout(60000),
    });
    const text = await boundedText(response, 32_000_000);
    totalBytes += Buffer.byteLength(text);
    if (totalBytes > 64_000_000)
      throw new Error("Discovery exceeds the 64 MB collection limit.");
    if (
      /<!DOCTYPE|<!ENTITY|<LINEERROR\b/i.test(text) ||
      XMLValidator.validate(text) !== true
    )
      throw new Error("Invalid Tally export.");
    const envelope = parser.parse(text).ENVELOPE;
    // The native XML data format emits an empty envelope when a period has no vouchers.
    if (period && envelope === "") return [];
    if (
      !envelope ||
      scalar(envelope.HEADER?.STATUS) === "0" ||
      envelope.HEADER?.STATUS === "0"
    )
      throw new Error("Tally rejected the export.");
    if (identity)
      return array(envelope.BODY?.DATA?.COLLECTION?.COMPANY).find(
        (r) => (r["@_NAME"] ?? scalar(r.NAME)) === company,
      );
    const data =
      envelope.BODY?.EXPORTDATA?.REQUESTDATA ?? envelope.BODY?.DATA ?? envelope;
    if (period && data === "") return [];
    if (!data || !Object.hasOwn(data, "TALLYMESSAGE"))
      throw new Error("Native detailed data export is unavailable.");
    const records = [];
    for (const message of array(data.TALLYMESSAGE)) {
      for (const [type, values] of Object.entries(message ?? {})) {
        if (type.startsWith("@_")) continue;
        for (const record of array(values)) {
          if (!record || typeof record !== "object")
            throw new Error("Incomplete export record.");
          records.push({ type, data: record });
        }
      }
    }
    return records;
  }
  for (const company of probe.companies) {
    const item = { company, port: config.port, status: "ready" };
    try {
      await onProgress(company, "reading");
      item.identity = await exportData(company, "MinkopsIdentity", null, true);
      item.company_guid = scalar(item.identity?.GUID);
      if (!item.company_guid?.trim())
        throw new Error("Company GUID is unavailable.");
      // All Masters is an import report; the native master export is List of Accounts.
      const masters = await exportData(company, "List of Accounts");
      item.masters = {
        status: "ready",
        count: masters.length,
        records: masters,
      };
      const vouchers = [];
      // Date chunks bound individual responses; no record slicing or sampling.
      for (let start = new Date(from); start <= to;) {
        const end = new Date(Math.min(+to, +start + 30 * 86400000));
        const period = {
          from: start.toISOString().slice(0, 10),
          to: end.toISOString().slice(0, 10),
        };
        await onProgress(company, "reading");
        const records = await exportData(company, "DayBook", period);
        for (const record of records) {
          const value = scalar(record.data.DATE);
          if (
            record.type !== "VOUCHER" ||
            !/^\d{8}$/.test(value ?? "") ||
            value < period.from.replaceAll("-", "") ||
            value > period.to.replaceAll("-", "")
          )
            throw new Error("Voucher export does not match its period.");
        }
        vouchers.push(...records);
        start = new Date(+end + 86400000);
      }
      item.vouchers = {
        status: "ready",
        count: vouchers.length,
        records: vouchers,
      };
    } catch {
      item.status = "unavailable";
      item.error =
        "Could not collect complete company data. Check access, detailed export support and collection size, then refresh.";
    }
    companies.push(item);
    await onProgress(company, item.status);
  }
  return {
    format_version: "2",
    period: config.period,
    companies,
    partial: companies.some((c) => c.status !== "ready"),
  };
}

export async function saveDiscoveryPackage(root, catalog) {
  if (!/^[a-f0-9-]{36}$/i.test(catalog.run_id ?? ""))
    throw new Error("Invalid discovery identity.");
  await mkdir(root, { recursive: true, mode: 0o700 });
  if ((await lstat(root)).isSymbolicLink())
    throw new Error("Invalid discovery folder.");
  const files = [
    { path: "catalog.json", value: catalog },
    { path: "context.json", value: catalog.context_notes ?? [] },
  ];
  for (const source of catalog.sources ?? [])
    for (const [index, company] of (
      source.snapshot?.companies ?? []
    ).entries()) {
      files.push(
        {
          path: `company-${index}-masters.json`,
          value: company.masters ?? null,
        },
        {
          path: `company-${index}-vouchers.json`,
          value: company.vouchers ?? null,
        },
      );
    }
  const contents = files.map((f) => ({
    ...f,
    bytes: Buffer.from(JSON.stringify(f.value)),
  }));
  const manifest = {
    format_version: "2",
    run_id: catalog.run_id,
    partial: catalog.partial,
    files: contents.map((f) => ({
      path: f.path,
      sha256: hash(f.bytes),
      bytes: f.bytes.length,
    })),
  };
  const manifestBytes = JSON.stringify(manifest, null, 2),
    target = join(root, catalog.run_id);
  try {
    if ((await lstat(target)).isSymbolicLink())
      throw new Error("Invalid package directory.");
    const existing = await readFile(join(target, "manifest.json"), "utf8");
    if (existing !== manifestBytes)
      throw new Error("Existing discovery package changed.");
    for (const file of manifest.files)
      if (hash(await readFile(join(target, file.path))) !== file.sha256)
        throw new Error("Existing discovery package changed.");
    return target;
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  const temporary = join(root, `.${randomUUID()}.tmp`);
  await mkdir(temporary, { mode: 0o700 });
  try {
    for (const file of contents)
      await writeFile(join(temporary, file.path), file.bytes, {
        flag: "wx",
        mode: 0o600,
      });
    await writeFile(join(temporary, "manifest.json"), manifestBytes, {
      flag: "wx",
      mode: 0o600,
    });
    await rename(temporary, target);
    return target;
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}
