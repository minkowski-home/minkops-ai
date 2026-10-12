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
import { boundedText } from "./index.js";
import {
  readTallyCompanyScope,
  readTallyAvailableCompanies,
  sameCompanyScope,
  tallyCompanyNumber,
} from "./tally-recovery.js";
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
  async function companyScope() {
    const available = await readTallyAvailableCompanies({
      port: config.port,
      request,
    });
    const loaded = await readTallyCompanyScope({ port: config.port, request });
    const scope = available.map((c) => ({
      ...c,
      company_guid:
        loaded.find(
          (l) =>
            l.company === c.company && l.company_number === c.company_number,
        )?.company_guid ?? null,
    }));
    // Preserve companies opened from another configured location as well.
    for (const company of loaded) {
      if (
        scope.some(
          (c) =>
            c.company_number === company.company_number &&
            c.company !== company.company,
        ) ||
        scope.some(
          (c) =>
            c.company === company.company &&
            c.company_number !== company.company_number,
        )
      )
        throw Object.assign(
          new Error(
            "Tally company scope has conflicting identities. Check company data paths and retry discovery.",
          ),
          { tallyScope: true },
        );
      if (!scope.some((c) => c.company_number === company.company_number))
        scope.push(company);
    }
    if (scope.length > 50)
      throw Object.assign(
        new Error("Tally company scope exceeds 50 companies."),
        { tallyScope: true },
      );
    return scope.sort((a, b) => a.company.localeCompare(b.company));
  }
  const scope = await companyScope();
  const companies = [];
  // Count verified native reads, not individual records in a bulk export.
  const total = scope.length * (2 + Math.ceil(((to - from) / 86400000 + 1) / 31)) + 1;
  let completed = 0;
  const report = (company, status, activity) => onProgress(company, status, {
    completed, total, activity, ...(company ? { item: company } : {})
  });
  let totalBytes = 0;
  async function exportData(
    company,
    id,
    period = null,
    identity = false,
    companyGuid = null,
  ) {
    const variables =
      `<SVCURRENTCOMPANY>${escape(company)}</SVCURRENTCOMPANY><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>` +
      (period
        ? `<SVFROMDATE TYPE="Date">${period.from.replaceAll("-", "")}</SVFROMDATE><SVTODATE TYPE="Date">${period.to.replaceAll("-", "")}</SVTODATE><EXPLODEFLAG>Yes</EXPLODEFLAG><SVEXPORTWITHCANCELLED>Yes</SVEXPORTWITHCANCELLED><SVEXPORTWITHOPTIONAL>Yes</SVEXPORTWITHOPTIONAL>`
        : id === "List of Accounts"
          ? "<ACCOUNTTYPE>All Masters</ACCOUNTTYPE>"
          : "");
    // Report-level date settings may override the supplied period. A fixed
    // native collection filters stored vouchers directly and fetches every
    // method/subcollection, including inventory and statutory allocations.
    // The root wildcard omits ledger/inventory allocations in native XML;
    // request their alternate native collection names explicitly as well.
    const definition = identity
      ? '<TDL><TDLMESSAGE><COLLECTION NAME="MinkopsIdentity"><TYPE>Company</TYPE><FETCH>*</FETCH></COLLECTION></TDLMESSAGE></TDL>'
      : period
        // Compare calendar components to validated numeric bounds: some native
        // modes coerce a requested Date variable to an empty/default date.
        ? `<TDL><TDLMESSAGE><COLLECTION NAME="MinkopsPeriodVouchers"><TYPE>Voucher</TYPE><FETCH>*,AllLedgerEntries.*,LedgerEntries.*,AllInventoryEntries.*,InventoryEntries.*</FETCH><FILTER>MinkopsPeriod</FILTER></COLLECTION><SYSTEM TYPE="Formulae" NAME="MinkopsPeriod">($$YearOfDate:$Date * 10000 + $$MonthOfDate:$Date * 100 + $$DayOfDate:$Date) Between ${period.from.replaceAll("-", "")} And ${period.to.replaceAll("-", "")}</SYSTEM></TDLMESSAGE></TDL>`
        : "";
    const body = `<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>${identity || period ? "Collection" : "Data"}</TYPE><ID>${id}</ID></HEADER><BODY><DESC><STATICVARIABLES>${variables}</STATICVARIABLES>${definition}</DESC></BODY></ENVELOPE>`;
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
    const collection = period ? envelope.BODY?.DATA?.COLLECTION : undefined;
    const data = collection ??
      envelope.BODY?.EXPORTDATA?.REQUESTDATA ?? envelope.BODY?.DATA ?? envelope;
    if (period && typeof data === "string" && !data.trim()) return [];
    if (!data || (collection === undefined && !Object.hasOwn(data, "TALLYMESSAGE")))
      throw new Error("Native detailed data export is unavailable.");
    const records = [];
    for (const message of collection === undefined ? array(data.TALLYMESSAGE) : [data]) {
      for (const [type, values] of Object.entries(message ?? {})) {
        if (type.startsWith("@_")) continue;
        // Native exports indent mixed XML content. Preserve record text exactly,
        // but do not mistake the message's formatting whitespace for a master.
        if (type === "#text" && typeof values === "string" && !values.trim())
          continue;
        for (const record of array(values)) {
          if (!record || typeof record !== "object")
            throw new Error("Incomplete export record.");
          // DayBook appends remote-company metadata after its vouchers. It is
          // not a voucher; accept only the trailer for the identity just read.
          if (period && type === "COMPANY") {
            const remote = array(record["REMOTECMPINFO.LIST"]);
            if (
              remote.length !== 1 ||
              scalar(remote[0].NAME) !== companyGuid ||
              scalar(remote[0].REMOTECMPNAME) !== company ||
              Object.keys(record).some(
                (key) =>
                  key !== "REMOTECMPINFO.LIST" &&
                  !key.startsWith("@_") &&
                  !(
                    key === "#text" &&
                    typeof record[key] === "string" &&
                    !record[key].trim()
                  ),
              )
            )
              throw new Error("Voucher export company identity mismatch.");
            continue;
          }
          records.push({ type, data: record });
        }
      }
    }
    return records;
  }
  for (const expected of scope) {
    const company = expected.company;
    const item = { company, port: config.port, status: "ready" };
    try {
      await report(company, "reading", "Checking company");
      if (!expected.company_guid)
        throw new Error("Company is not loaded or requires login.");
      item.identity = await exportData(company, "MinkopsIdentity", null, true);
      item.company_guid = scalar(item.identity?.GUID);
      if (
        item.company_guid !== expected.company_guid ||
        tallyCompanyNumber(item.identity?.COMPANYNUMBER) !==
          expected.company_number
      )
        throw new Error("Company identity changed during discovery.");
      completed++;
      await report(company, "reading", "Reading masters");
      // All Masters is an import report; the native master export is List of Accounts.
      const masters = await exportData(company, "List of Accounts");
      item.masters = {
        status: "ready",
        count: masters.length,
        records: masters,
      };
      completed++;
      await report(company, "reading", "Collected masters");
      const vouchers = [];
      // Date chunks bound individual responses; no record slicing or sampling.
      for (let start = new Date(from); start <= to; ) {
        const end = new Date(Math.min(+to, +start + 30 * 86400000));
        const period = {
          from: start.toISOString().slice(0, 10),
          to: end.toISOString().slice(0, 10),
        };
        await report(company, "reading", "Reading vouchers");
        const records = await exportData(
          company,
          "MinkopsPeriodVouchers",
          period,
          false,
          item.company_guid,
        );
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
        completed++;
        await report(company, "reading", "Collected vouchers");
        start = new Date(+end + 86400000);
      }
      item.vouchers = {
        status: "ready",
        count: vouchers.length,
        records: vouchers,
      };
    } catch (error) {
      if (error.code === "TASK_STOPPED") throw error;
      item.status = "unavailable";
      item.error =
        "Could not collect complete company data. Check access, detailed export support and collection size, then refresh.";
    }
    companies.push(item);
    await report(company, item.status, item.status === "ready" ? "Collected company" : "Company needs attention");
  }
  let scopeError;
  await report(null, "reading", "Checking company scope");
  try {
    const current = await companyScope();
    if (!sameCompanyScope(scope, current)) throw new Error("changed");
    completed++;
  } catch {
    scopeError =
      "Tally company scope changed or could not be verified. Load all original companies and refresh discovery.";
  }
  await report(null, scopeError || companies.some(c => c.status !== "ready") ? "unavailable" : "ready", scopeError ? "Company scope needs attention" : "Company scope checked");
  return {
    format_version: "2",
    period: config.period,
    companies,
    company_scope: scope,
    ...(scopeError ? { scope_error: scopeError } : {}),
    partial: Boolean(scopeError) || companies.some((c) => c.status !== "ready"),
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
    const existingDirectory = await lstat(target);
    // Windows rename can replace an occupied file with the package directory.
    if (existingDirectory.isSymbolicLink() || !existingDirectory.isDirectory())
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
