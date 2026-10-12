/** One crash restart per native job; never replay an import with unknown outcome.
 * Reads may repeat after readiness. Imports become reconciliation-only receipts.
 */
import { spawn } from "node:child_process";
import { dirname, resolve, join, isAbsolute } from "node:path";
import { readFile, readdir } from "node:fs/promises";
import { XMLParser, XMLValidator } from "fast-xml-parser";
import { boundedText } from "./index.js";

/** Tally emits COMPANYNUMBER as typed numeric text with leading whitespace.
 * Normalize only this startup argument; discovery retains the original XML data.
 */
export function tallyCompanyNumber(value) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    if (
      Object.keys(value).some((key) => key !== "#text" && !key.startsWith("@_"))
    )
      return null;
    value = value["#text"];
  }
  return typeof value === "string" && /^\d{1,10}$/.test(value.trim())
    ? value.trim()
    : null;
}

const scopeFailure = () =>
  Object.assign(
    new Error(
      "Tally company scope could not be verified. Check its data path and company access, then retry discovery.",
    ),
    { tallyScope: true },
  );

/** Live identities, never cached startup history, define discovery's restart scope. */
async function readCompanyList(
  { port = 9000, request = fetch, allowEmpty = false, timeout = 8000 } = {},
  disk = false,
) {
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw scopeFailure();
  try {
    const id = disk ? "MinkopsAvailableCompanies" : "MinkopsCompanyScope";
    const body = `<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>${id}</ID></HEADER><BODY><DESC><TDL><TDLMESSAGE><COLLECTION NAME="${id}"><TYPE>${disk ? "Company on Disk" : "Company"}</TYPE><FETCH>Name,GUID,CompanyNumber</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>`;
    const response = await request(`http://127.0.0.1:${port}`, {
      method: "POST",
      body,
      headers: { "Content-Type": "text/xml; charset=utf-8" },
      redirect: "error",
      signal: AbortSignal.timeout(timeout),
    });
    const source = await boundedText(response, 1_000_000);
    if (
      /<!DOCTYPE|<!ENTITY|<LINEERROR\b/i.test(source) ||
      XMLValidator.validate(source) !== true
    )
      throw scopeFailure();
    const parsed = new XMLParser({
      ignoreAttributes: false,
      parseTagValue: false,
      parseAttributeValue: false,
      trimValues: true,
    }).parse(source).ENVELOPE;
    if (String(parsed?.HEADER?.STATUS) !== "1") throw scopeFailure();
    const node =
      parsed.BODY?.DATA?.COLLECTION?.[disk ? "COMPANYONDISK" : "COMPANY"];
    const companies = Array.isArray(node) ? node : node ? [node] : [];
    const scalar = (v) => (typeof v === "string" ? v : v?.["#text"]);
    const scope = companies.map((c) => ({
      company: scalar(c.NAME) || c["@_NAME"],
      ...(disk ? {} : { company_guid: scalar(c.GUID) }),
      company_number: tallyCompanyNumber(c.COMPANYNUMBER),
    }));
    if (
      (!scope.length && !allowEmpty) ||
      scope.length > 50 ||
      scope.some(
        (c) =>
          typeof c.company !== "string" ||
          !c.company.trim() ||
          c.company.length > 200 ||
          /[\x00-\x1f]/.test(c.company) ||
          (!disk &&
            (typeof c.company_guid !== "string" || !c.company_guid.trim())) ||
          !c.company_number,
      ) ||
      (disk
        ? ["company", "company_number"]
        : ["company", "company_guid", "company_number"]
      ).some((key) => new Set(scope.map((c) => c[key])).size !== scope.length)
    )
      throw scopeFailure();
    return scope;
  } catch {
    throw scopeFailure();
  }
}

export const readTallyCompanyScope = (options) => readCompanyList(options);
export const readTallyAvailableCompanies = (options) =>
  readCompanyList(options, true);

const serviceFailure = (message) =>
  Object.assign(new Error(message), { tallyScope: true });

/** Prepare all companies from Tally's configured data directory, not just those
 * someone happened to open. Never force-kill a live accounting application. */
export async function ensureTallyDiscovery(
  config,
  {
    installation = inspectTallyInstallation,
    isRunning = tallyProcessRunning,
    start = restartTallyProcess,
    stop = closeTallyProcess,
    ready = waitForTally,
    request = fetch,
  } = {},
) {
  let observed = await installation();
  if (!observed)
    throw serviceFailure(
      "Tally installation was not found. Install TallyPrime on this PC and retry discovery.",
    );
  const url = `http://127.0.0.1:${config.port}`;
  const running = await isRunning(observed);
  if (running === null)
    throw serviceFailure(
      "Tally process identity is uncertain. Close additional Tally instances and retry discovery.",
    );
  if (!running) {
    if (!observed.loads.length)
      throw serviceFailure(
        "Tally company data path could not be verified. Configure its data path in Tally and retry discovery.",
      );
    await start(observed);
    await ready(url, observed);
    observed = await installation();
    if (!observed)
      throw serviceFailure(
        "Tally startup could not be verified. Retry discovery.",
      );
  }
  const available = await readTallyAvailableCompanies({
    port: config.port,
    request,
  });
  const loaded = await readTallyCompanyScope({
    port: config.port,
    request,
    allowEmpty: true,
  });
  const missing = available.filter(
    (c) =>
      !loaded.some(
        (l) => l.company === c.company && l.company_number === c.company_number,
      ),
  );
  if (missing.length) {
    const startup = {
      ...observed,
      company_scope: loaded,
      required_companies: available,
      loads: [
        ...new Set([...available, ...loaded].map((c) => c.company_number)),
      ],
    };
    // A normal window-close lets Tally protect unsaved work and login prompts.
    // If it refuses, hand off; never terminate it to manufacture a full scope.
    await stop(observed);
    await start(startup);
    await ready(url, startup);
  }
  const verified = await readTallyCompanyScope({ port: config.port, request });
  if (
    !available.every((c) =>
      verified.some(
        (l) => l.company === c.company && l.company_number === c.company_number,
      ),
    ) ||
    !loaded.every((c) =>
      verified.some(
        (l) =>
          l.company === c.company &&
          l.company_guid === c.company_guid &&
          l.company_number === c.company_number,
      ),
    )
  )
    throw serviceFailure(
      "Tally company scope is incomplete. Complete company login in Tally and retry discovery.",
    );
  return {
    ...observed,
    loads: verified.map((c) => c.company_number),
    company_scope: verified,
  };
}

/** Parse only the locally configured data path; never accept one from a web job. */
export async function startupCompanies(exe, ini, { list = readdir } = {}) {
  const configured = ini
    .match(/^\s*Data\s*=\s*([^;\r\n]+)\s*$/im)?.[1]
    .trim()
    .replace(/^"(.*)"$/, "$1");
  if (!configured) return [];
  const root = isAbsolute(configured)
    ? resolve(configured)
    : resolve(dirname(exe), configured);
  const directories = await list(root, { withFileTypes: true });
  const numbers = [];
  for (const entry of directories) {
    if (!entry.isDirectory() || !/^\d{1,10}$/.test(entry.name)) continue;
    const files = await list(join(root, entry.name), { withFileTypes: true });
    if (files.some((f) => f.isFile() && /^company\.\d+$/i.test(f.name)))
      numbers.push(entry.name);
  }
  if (numbers.length > 50)
    throw serviceFailure(
      "Tally discovery supports up to 50 companies. Configure a smaller company data directory.",
    );
  return numbers;
}

export function sameCompanyScope(expected, actual) {
  const canonical = (scope) =>
    scope
      .map((c) => JSON.stringify([c.company, c.company_guid, c.company_number]))
      .sort();
  return (
    JSON.stringify(canonical(expected)) === JSON.stringify(canonical(actual))
  );
}

export function recoveringTallyRequest({
  request = fetch,
  capture,
  isRunning,
  restart,
  ready,
  diagnose,
  preserveCompanyScope = false,
}) {
  let restarted = false,
    observed,
    scopeCaptured = false;
  return async function transport(url, options) {
    observed ??= await capture();
    if (preserveCompanyScope && !scopeCaptured) {
      // This preflight deliberately bypasses recovery: without live evidence a
      // restart from remembered companies could silently narrow discovery.
      const scope = await readTallyCompanyScope({
        port: Number(new URL(url).port),
        request,
      });
      if (observed)
        observed = {
          ...observed,
          company_scope: scope,
          loads: scope.map((c) => c.company_number),
        };
      scopeCaptured = true;
    }
    // Retry only a known read. Unclassified requests, including new JSON/action
    // contracts, must never become replayable merely by omitting an Import tag.
    const write =
      !/<TALLYREQUEST>\s*Export(?:\s*Data)?\s*<\/TALLYREQUEST>/i.test(
        options.body,
      ) || /<TYPE>\s*(?:Function|Action)\s*<\/TYPE>/i.test(options.body);
    try {
      const response = await request(url, options);
      const body = await boundedText(response, 32_000_000);
      const json = body.trimStart().startsWith("{") ? JSON.parse(body) : null;
      if (
        /<LINEERROR\b|<ERRORS>\s*[1-9]|<STATUS>\s*0\s*<\/STATUS>/i.test(body) ||
        (json &&
          (String(json.status) === "0" ||
            Number(json.data?.import_result?.errors) > 0))
      ) {
        const diagnostic = new Error("Tally rejected the request.");
        diagnostic.tallyLineError =
          body
            .match(/<LINEERROR[^>]*>([\s\S]*?)<\/LINEERROR>/i)?.[1]
            ?.replace(/<[^>]*>/g, "")
            .slice(0, 1000) ?? "Tally returned a failure status.";
        throw diagnostic;
      }
      return new Response(body, {
        status: response.status,
        headers: response.headers,
      });
    } catch (error) {
      const running = observed ? await isRunning(observed) : null;
      await diagnose({
        error: error.tallyLineError ?? error.message,
        process_disappeared: running === false,
        write,
        observed,
      });
      if (!restarted && observed && running === false) {
        restarted = true;
        try {
          await restart(observed);
          await ready(url, observed);
        } catch (recoveryError) {
          // A licence/readiness handoff does not establish whether the import
          // applied. Preserve its uncertainty through this secondary failure.
          if (write) recoveryError.tallyAmbiguous = true;
          throw recoveryError;
        }
        if (!write) {
          // The restart fence makes a second failure terminal, while retaining diagnosis.
          return transport(url, {
            ...options,
            signal: AbortSignal.timeout(60000),
          });
        }
      }
      if (write) {
        const ambiguous = new Error(
          "Tally write outcome is unknown. Reconcile the approved bill before another write.",
        );
        ambiguous.tallyAmbiguous = true;
        ambiguous.tallyLineError = error.tallyLineError;
        throw ambiguous;
      }
      throw error;
    }
  };
}

function powershell(script, config = {}) {
  if (process.platform !== "win32")
    return Promise.reject(new Error("Tally restart requires Windows."));
  return new Promise((resolve, reject) => {
    const child = spawn(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", script],
      { windowsHide: true, stdio: ["pipe", "pipe", "pipe"] },
    );
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
      if (code !== 0 || size > 32000)
        reject(new Error("Could not inspect the local Tally process."));
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
const PROCESS = String.raw`$ErrorActionPreference='Stop';[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$p=@(Get-CimInstance Win32_Process -Filter "Name='tally.exe' OR Name='tallyprime.exe'")
if ($p.Count -ne 1 -or !$p[0].ExecutablePath) { 'null'; exit }
$exe=$p[0].ExecutablePath
$version=(Get-Item -LiteralPath $exe).VersionInfo
if ($version.CompanyName -notmatch 'Tally') { 'null'; exit }
# Keep only company-number LOAD arguments. Never replay arbitrary command lines/TDL.
$loads=@([regex]::Matches([string]$p[0].CommandLine,'(?i)/LOAD\s*:\s*(\d+)') | ForEach-Object {$_.Groups[1].Value})
@{exe=$exe;pid=$p[0].ProcessId;loads=$loads} | ConvertTo-Json -Compress`;
const RUNNING = String.raw`$c=[Console]::In.ReadToEnd() | ConvertFrom-Json
$p=@(Get-CimInstance Win32_Process -Filter "Name='tally.exe' OR Name='tallyprime.exe'")
if (@($p | Where-Object {$_.ExecutablePath -eq $c.exe}).Count -gt 0) {'true'} elseif ($p.Count -gt 0) {'null'} else {'false'}`;
const EVENTS = String.raw`$c=[Console]::In.ReadToEnd() | ConvertFrom-Json
$events=@(Get-WinEvent -FilterHashtable @{LogName='Application';Id=1000,1001;StartTime=(Get-Date).AddMinutes(-3)} -MaxEvents 20 -ErrorAction SilentlyContinue | Where-Object {$_.Message -match '(?i)tally(?:prime)?\.exe'} | Select-Object TimeCreated,Id,ProviderName,Message)
ConvertTo-Json -InputObject $events -Depth 3 -Compress`;

const INSTALLATION = String.raw`$ErrorActionPreference='Stop';[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$p=@(Get-CimInstance Win32_Process -Filter "Name='tally.exe' OR Name='tallyprime.exe'")
if ($p.Count -gt 1) { throw 'Multiple Tally processes' }
$exe=if ($p.Count -eq 1) {$p[0].ExecutablePath} else {$null}
if (!$exe) {
  $candidates=@()
  foreach ($root in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\tally.exe','HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\tally.exe')) {
    if (Test-Path -LiteralPath $root) {$candidates+= (Get-Item -LiteralPath $root).GetValue('')}
  }
  foreach ($base in @($env:ProgramFiles,[Environment]::GetEnvironmentVariable('ProgramFiles(x86)'))) {
    if ($base) {$candidates+=Join-Path $base 'TallyPrime\tally.exe'}
  }
  $valid=@($candidates | Select-Object -Unique | Where-Object {$_ -and (Test-Path -LiteralPath $_) -and (Get-Item -LiteralPath $_).VersionInfo.CompanyName -match 'Tally'})
  if ($valid.Count -ne 1) {'null';exit}
  $exe=$valid[0]
}
if ((Get-Item -LiteralPath $exe).VersionInfo.CompanyName -notmatch 'Tally') {'null';exit}
@{exe=$exe;pid=if($p.Count){$p[0].ProcessId}else{$null};loads=@()} | ConvertTo-Json -Compress`;

const CLOSE = String.raw`$ErrorActionPreference='Stop';$c=[Console]::In.ReadToEnd() | ConvertFrom-Json
$p=Get-CimInstance Win32_Process -Filter "ProcessId=$($c.pid)"
if (!$p -or $p.ExecutablePath -ne $c.exe) {throw 'Tally process changed'}
$native=Get-Process -Id $c.pid
if (!$native.CloseMainWindow()) {throw 'Tally cannot close safely'}
if (!$native.WaitForExit(10000)) {throw 'Tally needs attention before closing'}
'true'`;

export async function inspectTallyInstallation() {
  const observed = await powershell(INSTALLATION);
  if (!observed) return null;
  try {
    observed.loads = await startupCompanies(
      observed.exe,
      await readFile(join(dirname(observed.exe), "tally.ini"), "utf8"),
    );
  } catch (error) {
    if (error.tallyScope) throw error;
    observed.loads = [];
  }
  return observed;
}

export async function closeTallyProcess(observed) {
  if (!Number.isInteger(observed?.pid) || observed.pid < 1)
    throw serviceFailure("Tally process changed. Retry discovery.");
  try {
    await powershell(CLOSE, { exe: observed.exe, pid: observed.pid });
  } catch {
    throw serviceFailure(
      "Tally needs attention before remaining companies can load. Save your work and close Tally, then retry discovery; Minkops will start it.",
    );
  }
}

export async function captureTallyProcess() {
  return powershell(PROCESS);
}
export async function tallyProcessRunning(observed) {
  return powershell(RUNNING, { exe: observed.exe });
}
export async function tallyCrashEvents() {
  return powershell(EVENTS).catch(() => []);
}
export async function restartTallyProcess(observed) {
  // The executable comes only from an observed local Tally process, never a web payload.
  if (
    !observed?.exe ||
    !/tally(?:prime)?\.exe$/i.test(observed.exe) ||
    observed.loads.some((n) => !/^\d{1,10}$/.test(n))
  )
    throw new Error("Tally startup identity is unavailable.");
  if ((await tallyProcessRunning(observed)) !== false)
    throw new Error(
      "Tally is already running or process identity is uncertain.",
    );
  const child = spawn(
    observed.exe,
    observed.loads.map((n) => `/LOAD:${n}`),
    {
      cwd: dirname(observed.exe),
      detached: true,
      stdio: "ignore",
      shell: false,
    },
  );
  await new Promise((resolve, reject) => {
    child.once("spawn", resolve);
    child.once("error", reject);
  });
  child.unref();
}
export async function waitForTally(url, observed) {
  // Poll read-only company availability. Authentication screens remain a handoff.
  const body =
    '<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>MinkopsRecovery</ID></HEADER><BODY><DESC><TDL><TDLMESSAGE><COLLECTION NAME="MinkopsRecovery"><TYPE>Company</TYPE><FETCH>Name,CompanyNumber</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>';
  for (let attempt = 0; attempt < 20; attempt++) {
    try {
      if (observed?.company_scope) {
        const scope = await readTallyCompanyScope({
          port: Number(new URL(url).port),
          timeout: 2000,
        });
        if (
          observed.required_companies
            ? observed.company_scope.every((c) =>
                scope.some(
                  (a) =>
                    a.company === c.company &&
                    a.company_guid === c.company_guid &&
                    a.company_number === c.company_number,
                ),
              ) &&
              observed.required_companies.every((c) =>
                scope.some(
                  (a) =>
                    a.company === c.company &&
                    a.company_number === c.company_number,
                ),
              )
            : sameCompanyScope(observed.company_scope, scope)
        )
          return;
        throw scopeFailure();
      }
      const response = await fetch(url, {
        method: "POST",
        body,
        signal: AbortSignal.timeout(2000),
      });
      const value = await boundedText(response, 1_000_000);
      const parsed = new XMLParser({ parseTagValue: false }).parse(
        value,
      ).ENVELOPE;
      const collection = parsed?.BODY?.DATA?.COLLECTION?.COMPANY;
      const companies = Array.isArray(collection)
        ? collection
        : collection
          ? [collection]
          : [];
      const numbers = new Set(
        companies.map((c) => tallyCompanyNumber(c.COMPANYNUMBER)),
      );
      // Tally exposes its listener while companies are still loading. Waiting
      // for the full observed startup scope prevents reads against that state.
      if (
        String(parsed?.HEADER?.STATUS) === "1" &&
        companies.length &&
        (observed?.loads ?? []).every((n) => numbers.has(n))
      )
        return;
    } catch {
      /* Process startup and services may take a few seconds. */
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(
    "Tally restarted but its company scope is not ready. Load all original companies, then retry.",
  );
}
