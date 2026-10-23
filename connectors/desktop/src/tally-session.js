/** The user's Tally session, read-only.
 *
 * Tally belongs to the user: Minkops never starts, closes, restarts or locates
 * it, never handles its passwords and never chooses its data folders. Work uses
 * the companies the user opened, from any folder. Every failure becomes one
 * typed state with a single user action, so Check connection, discovery and
 * bill saves can never disagree about the same session.
 */
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { XMLParser, XMLValidator } from "fast-xml-parser";

const MAX_OPEN_COMPANIES = 50;

/** Read a Tally HTTP response, refusing oversized bodies before parsing. */
export async function boundedText(response, limit = 1_000_000) {
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

/** A failure the user can act on. Its message is safe to show verbatim. */
export class TallyUnavailable extends Error {
  constructor(state, message, detail = {}) {
    super(message.slice(0, 300));
    this.tallyState = state;
    this.userSafe = true;
    this.detail = detail;
  }
}

const settings =
  "In Tally: Help (F1) > Settings > Connectivity, set TallyPrime to act as Server or Both";
const MESSAGES = {
  not_running: (pc) => `Tally isn't open on ${pc}. Open it and your companies, then try again.`,
  unreachable: (pc, port) =>
    `Tally isn't reachable on ${pc}. Open Tally and your companies. If it is open, enable port ${port} in Help (F1) > Settings > Connectivity.`,
  port_closed: (pc, port) =>
    `Tally on ${pc} isn't accepting connections on port ${port}. ${settings} on port ${port}, then try again.`,
  // A pending prompt and a very large report both time out; name both causes.
  busy: (pc) =>
    `Tally on ${pc} is not responding. Finish any password prompt or open dialog in Tally, or wait for a large report to finish, then try again.`,
  no_company: (pc) => `Open at least one company in Tally on ${pc}, then try again.`,
  duplicate_company: (pc, name, other) => other
    ? `${name} and ${other} share one company identity. Close one in Tally on ${pc}, then try again.`
    : `Two open companies are named ${name}. Close one in Tally on ${pc}, then try again.`,
  too_many: (pc) =>
    `More than ${MAX_OPEN_COMPANIES} companies are open in Tally on ${pc}. Close the ones you don't need, then try again.`,
  invalid_response: (pc) =>
    `Tally on ${pc} returned an unexpected response. Use Send diagnostics in the Minkops tray menu.`,
  other_session: (pc, port) =>
    `Tally on port ${port} belongs to another Windows user on ${pc}. Give your own Tally a port of its own in Help (F1) > Settings > Connectivity, and set the same port for this PC in Minkops.`,
  ownership_unknown: (pc, port) =>
    `Minkops could not confirm that Tally on port ${port} is your own on ${pc}, a shared server. Ask your provider to allow PowerShell for Minkops, or use Send diagnostics in the Minkops tray menu.`,
};
const unavailable = (state, pc, ...args) =>
  new TallyUnavailable(state === "unreachable" ? "not_running" : state, MESSAGES[state](pc, ...args));

/** Tally emits COMPANYNUMBER as typed numeric text with leading whitespace.
 * Numbers are folder-local display data; GUIDs identify companies. */
export function tallyCompanyNumber(value) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    if (Object.keys(value).some((key) => key !== "#text" && !key.startsWith("@_")))
      return null;
    value = value["#text"];
  }
  return typeof value === "string" && /^\d{1,10}$/.test(value.trim()) ? value.trim() : null;
}

const scalar = (value) => {
  if (typeof value === "string") return value;
  if (
    value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.keys(value).every((key) => key === "#text" || key.startsWith("@_")) &&
    (value["#text"] === undefined || typeof value["#text"] === "string")
  )
    return value["#text"] ?? "";
  return undefined;
};
const isoDate = (value) => {
  const text = scalar(value)?.trim();
  if (!/^\d{8}$/.test(text ?? "")) return undefined;
  const iso = `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6)}`;
  return new Date(`${iso}T00:00:00Z`).toISOString().slice(0, 10) === iso ? iso : undefined;
};

/** One fixed Company collection: never Company on Disk, which covers only the
 * folder named by tally.ini and misleads in multi-folder practices. */
export async function readOpenCompanies({ port = 9000, request = fetch, timeout = 8000, pc = "this PC" } = {}) {
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error("Invalid Tally port.");
  const body =
    '<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>MinkopsOpenCompanies</ID></HEADER><BODY><DESC><TDL><TDLMESSAGE><COLLECTION NAME="MinkopsOpenCompanies"><TYPE>Company</TYPE><FETCH>Name,GUID,CompanyNumber,BooksFrom</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>';
  const response = await request(`http://127.0.0.1:${port}`, {
    method: "POST",
    body,
    headers: { "Content-Type": "text/xml; charset=utf-8" },
    redirect: "error",
    signal: AbortSignal.timeout(timeout),
  });
  const invalid = () => unavailable("invalid_response", pc);
  let source;
  try {
    source = await boundedText(response, 1_000_000);
  } catch {
    throw invalid();
  }
  if (/<!DOCTYPE|<!ENTITY|<LINEERROR\b/i.test(source) || XMLValidator.validate(source) !== true)
    throw invalid();
  const envelope = new XMLParser({
    ignoreAttributes: false,
    parseTagValue: false,
    parseAttributeValue: false,
    trimValues: true,
  }).parse(source).ENVELOPE;
  if (!envelope || String(scalar(envelope.HEADER?.STATUS)) !== "1") throw invalid();
  const node = envelope.BODY?.DATA?.COLLECTION?.COMPANY;
  return (Array.isArray(node) ? node : node ? [node] : []).map((record) => {
    const name = (scalar(record.NAME) || record["@_NAME"] || "").trim();
    const guid = (scalar(record.GUID) ?? "").trim();
    if (!name || name.length > 200 || /[\x00-\x1f]/.test(name) || !guid || guid.length > 200)
      throw invalid();
    const company = { company: name, company_guid: guid, company_number: tallyCompanyNumber(record.COMPANYNUMBER) };
    const books = isoDate(record.BOOKSFROM);
    return books ? { ...company, books_from: books } : company;
  });
}

/** Validate an open scope. Names must be unique because every Tally request
 * selects its company by name (SVCURRENTCOMPANY); GUIDs identify it. */
export function openCompanyScope(companies, { pc = "this PC" } = {}) {
  if (!companies.length) throw unavailable("no_company", pc);
  if (companies.length > MAX_OPEN_COMPANIES) throw unavailable("too_many", pc);
  const names = new Map(),
    guids = new Map();
  for (const company of companies) {
    const name = company.company.toLowerCase();
    if (names.get(name)) throw unavailable("duplicate_company", pc, names.get(name).company);
    // A repeated GUID with different names: name both companies, not the first twice.
    const twin = guids.get(company.company_guid);
    if (twin) throw unavailable("duplicate_company", pc, twin.company, company.company);
    names.set(name, company);
    guids.set(company.company_guid, company);
  }
  return [...companies].sort((a, b) => a.company.localeCompare(b.company));
}

const failureCode = (error) =>
  error?.name === "TimeoutError" || error?.cause?.name === "TimeoutError"
    ? "TimeoutError"
    : error?.cause?.code ?? error?.code ?? error?.name ?? "unknown";

/** Turn a transport failure into one user action, using a read-only process check. */
export async function classifyTallyFailure(error, { processes = tallyProcesses, pc = "this PC", port = 9000 } = {}) {
  if (error instanceof TallyUnavailable) return error;
  const code = failureCode(error);
  const running = await Promise.resolve()
    .then(processes)
    .then((list) => (Array.isArray(list) ? list.length : null))
    .catch(() => null);
  let result;
  if (running === 0) result = unavailable("not_running", pc);
  else if (code === "ECONNREFUSED")
    result = running ? unavailable("port_closed", pc, port) : unavailable("unreachable", pc, port);
  else if (running === null && code !== "TimeoutError") result = unavailable("unreachable", pc, port);
  else result = unavailable("busy", pc);
  result.detail = { cause: code, running };
  return result;
}

/** On a server several Windows users share, a TCP port is the machine's, not the
 * user's: Tally on this port may be another user's, with another firm's books.
 * Its session must be this companion's own before anything is read from it. */
export async function requireOwnTally({ port = 9000, observe = observeTally, shared = sharedSession(), pc = "this PC" } = {}) {
  const seen = await Promise.resolve().then(() => observe(port)).catch(() => null);
  const known = Number.isInteger(seen?.own);
  if (known && seen.listener && seen.listener.session !== seen.own) throw unavailable("other_session", pc, port);
  // Unobservable on a shared server, the Tally is not assumed to be this user's; on a PC of their own it is.
  if (!known && shared) throw unavailable("ownership_unknown", pc, port);
  return known ? seen : null;
}

/** Whether this companion runs in a remote session, as on a server several users share. */
export function sharedSession(name = process.env.SESSIONNAME) {
  return process.platform === "win32" && Boolean(name) && !/^console$/i.test(name);
}

/** Check connection, discovery preflight and pre-save checks share this. */
export async function checkTally({
  port = 9000,
  request = fetch,
  processes = tallyProcesses,
  observe = observeTally,
  shared = sharedSession(),
  pc = "this PC",
  retries = 2,
  wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
} = {}) {
  const seen = await requireOwnTally({ port, observe, shared, pc });
  for (let attempt = 0; ; attempt++) {
    try {
      const companies = openCompanyScope(await readOpenCompanies({ port, request, pc }), { pc });
      const instances = seen?.processes;
      return {
        state: "ready",
        port,
        companies,
        warnings:
          Array.isArray(instances) && instances.length > 1
            ? [{ state: "multiple_instances", message: `More than one Tally is open on ${pc}; Minkops uses the one on port ${port}.` }]
            : [],
      };
    } catch (error) {
      const failure = await classifyTallyFailure(error, { processes, pc, port });
      if (failure.tallyState !== "busy" || attempt >= retries) throw failure;
      await wait(1000 * (attempt + 1));
    }
  }
}

/** The company a save targets must be open, and be the same company: a
 * same-named copy from another folder is never written to. */
export async function requireOpenCompany({ company, company_guid }, options = {}) {
  const pc = options.pc ?? "this PC";
  const { companies } = await checkTally(options);
  const open = companies.find((c) => c.company.toLowerCase() === company.toLowerCase());
  if (!open)
    throw new TallyUnavailable("company_not_open", `Open ${company} in Tally on ${pc}, then try again.`);
  if (company_guid && open.company_guid !== company_guid)
    throw new TallyUnavailable(
      "company_not_open",
      `A different company named ${company} is open in Tally on ${pc}. Close it, open the company Minkops discovered, then try again.`,
    );
  return open;
}

/** Only known exports may repeat. New JSON/action contracts never become
 * replayable merely by omitting an Import tag. */
const isWrite = (body) =>
  !/<TALLYREQUEST>\s*Export(?:\s*Data)?\s*<\/TALLYREQUEST>/i.test(body) ||
  /<TYPE>\s*(?:Function|Action)\s*<\/TYPE>/i.test(body);

/** Request transport for native jobs: classifies failures and diagnoses them.
 * A timed-out read may repeat twice (a dialog was briefly open); a write never
 * repeats, and an unacknowledged write becomes a reconciliation-only outcome. */
export function tallyTransport({
  request = fetch,
  processes = tallyProcesses,
  diagnose = async () => {},
  pc = "this PC",
  retries = 2,
  wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
}) {
  return async function transport(url, options) {
    const write = isWrite(options.body);
    const port = Number(new URL(url).port) || 80;
    for (let attempt = 0; ; attempt++) {
      const started = Date.now();
      try {
        const response = await request(url, attempt ? { ...options, signal: AbortSignal.timeout(60000) } : options);
        const body = await boundedText(response, 32_000_000);
        const json = body.trimStart().startsWith("{") ? JSON.parse(body) : null;
        if (
          /<LINEERROR\b|<ERRORS>\s*[1-9]|<STATUS>\s*0\s*<\/STATUS>/i.test(body) ||
          (json && (String(json.status) === "0" || Number(json.data?.import_result?.errors) > 0))
        ) {
          const rejected = new Error("Tally rejected the request.");
          rejected.tallyLineError =
            body
              .match(/<LINEERROR[^>]*>([\s\S]*?)<\/LINEERROR>/i)?.[1]
              ?.replace(/<[^>]*>/g, "")
              .slice(0, 1000) ?? "Tally returned a failure status.";
          throw rejected;
        }
        return new Response(body, { status: response.status, headers: response.headers });
      } catch (error) {
        const failure = error.tallyLineError ? null : await classifyTallyFailure(error, { processes, pc, port });
        await diagnose({
          error: String(error.message).slice(0, 300),
          cause: failure?.detail.cause ?? "rejected",
          state: failure?.tallyState ?? "rejected",
          ...(error.tallyLineError ? { line_error: error.tallyLineError } : {}),
          write,
          attempt,
          elapsed_ms: Date.now() - started,
        });
        if (write) {
          const ambiguous = new Error("Tally write outcome is unknown. Reconcile the approved bill before another write.");
          ambiguous.tallyAmbiguous = true;
          ambiguous.tallyLineError = error.tallyLineError;
          if (failure) Object.assign(ambiguous, { tallyState: failure.tallyState, userMessage: failure.message });
          throw ambiguous;
        }
        if (!failure) throw error;
        if (failure.tallyState === "busy" && attempt < retries) {
          await wait(1000 * (attempt + 1));
          continue;
        }
        throw failure;
      }
    }
  };
}

function powershell(script, config = {}) {
  if (process.platform !== "win32") return Promise.resolve(null);
  return new Promise((resolve, reject) => {
    const child = spawn("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script], {
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
    });
    let result = "",
      size = 0;
    const timeout = setTimeout(() => child.kill(), 15000);
    child.stdout.on("data", (chunk) => {
      size += chunk.length;
      if (size > 32000) child.kill();
      else result += chunk.toString("utf8");
    });
    child.on("error", reject);
    child.on("close", (code) => {
      clearTimeout(timeout);
      if (code !== 0 || size > 32000) reject(new Error("Could not inspect the local Tally process."));
      else {
        try {
          resolve(JSON.parse(result));
        } catch {
          reject(new Error("Invalid process observation."));
        }
      }
    });
    child.stdin.end(JSON.stringify(config));
  });
}

// Read-only observation. Never a command line, never a process handle.
const PROCESSES = String.raw`$ErrorActionPreference='Stop';[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$p=@(Get-CimInstance Win32_Process -Filter "Name='tally.exe' OR Name='tallyprime.exe'" | ForEach-Object {
  $v=$null; if ($_.ExecutablePath) { try { $v=(Get-Item -LiteralPath $_.ExecutablePath).VersionInfo } catch {} }
  @{pid=$_.ProcessId; exe=$_.ExecutablePath; product=$v.ProductName; version=$v.ProductVersion; session=$_.SessionId}
})
ConvertTo-Json -InputObject $p -Compress -Depth 3`;
const EVENTS = String.raw`$events=@(Get-WinEvent -FilterHashtable @{LogName='Application';Id=1000,1001;StartTime=(Get-Date).AddMinutes(-3)} -MaxEvents 20 -ErrorAction SilentlyContinue | Where-Object {$_.Message -match '(?i)tally(?:prime)?\.exe'} | Select-Object TimeCreated,Id,ProviderName,Message)
ConvertTo-Json -InputObject $events -Depth 3 -Compress`;

// Read-only: which process listens on the port, in which Windows session, beside
// this companion's own session and the running Tally processes. Never a handle.
const OBSERVE = String.raw`$ErrorActionPreference='Stop';[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$port=[int](([Console]::In.ReadToEnd() | ConvertFrom-Json).port)
$own=(Get-CimInstance Win32_Process -Filter "ProcessId=$PID").SessionId
$owner=$null
try { $owner=@(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop)[0].OwningProcess } catch {}
$listener=$null
if ($owner) { $l=Get-CimInstance Win32_Process -Filter "ProcessId=$owner"; if ($l) { $listener=@{pid=$l.ProcessId; name=$l.Name; session=$l.SessionId} } }
$p=@(Get-CimInstance Win32_Process -Filter "Name='tally.exe' OR Name='tallyprime.exe'" | ForEach-Object { @{pid=$_.ProcessId; session=$_.SessionId} })
ConvertTo-Json -InputObject @{own=$own; listener=$listener; processes=$p} -Compress -Depth 4`;

/** Who serves Tally's port and this companion's session, or null when they cannot be observed. */
export async function observeTally(port) {
  const seen = await powershell(OBSERVE, { port });
  if (!seen) return null;
  const processes = Array.isArray(seen.processes) ? seen.processes : seen.processes ? [seen.processes] : [];
  return { own: seen.own, listener: seen.listener ?? null, processes };
}

/** Running Tally processes, or null when they cannot be observed. */
export async function tallyProcesses() {
  const list = await powershell(PROCESSES);
  return Array.isArray(list) ? list : list ? [list] : null;
}
export async function tallyCrashEvents() {
  return powershell(EVENTS).catch(() => []);
}

// Settings that explain connection and folder problems; nothing else leaves the PC.
const INI_KEYS = ["Tally Gateway Server", "User TDL", "Default Companies", "Load", "Data",
  "Client Server", "ServerPort", "Enable ODBC Server"];
export function parseTallyIni(text) {
  const settings = {};
  for (const line of String(text).split(/\r?\n/)) {
    const match = line.match(/^\s*([^;=][^=]*?)\s*=\s*(.*?)\s*$/);
    const key = match && INI_KEYS.find((k) => k.toLowerCase() === match[1].toLowerCase());
    if (key) settings[key] = match[2].slice(0, 300);
  }
  return settings;
}
/** Read next to the running executable only; Minkops never searches for Tally. */
export async function readTallyIni(exe, { read = readFile } = {}) {
  if (typeof exe !== "string" || !exe) return null;
  try {
    return parseTallyIni(await read(join(dirname(exe), "tally.ini"), "utf8"));
  } catch {
    return null;
  }
}
