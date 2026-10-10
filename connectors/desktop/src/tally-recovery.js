/** One crash restart per native job; never replay an import with unknown outcome.
 * Reads may repeat after readiness. Imports become reconciliation-only receipts.
 */
import { spawn } from "node:child_process";
import { dirname } from "node:path";
import { XMLParser } from "fast-xml-parser";
import { boundedText } from "./index.js";

export function recoveringTallyRequest({
  request = fetch,
  capture,
  isRunning,
  restart,
  ready,
  diagnose,
}) {
  let restarted = false,
    observed;
  return async function transport(url, options) {
    observed ??= await capture();
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
        await restart(observed);
        await ready(url, observed);
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
export async function waitForTally(url) {
  // Poll read-only company availability. Authentication screens remain a handoff.
  const body =
    '<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>MinkopsRecovery</ID></HEADER><BODY><DESC><TDL><TDLMESSAGE><COLLECTION NAME="MinkopsRecovery"><TYPE>Company</TYPE><FETCH>Name</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>';
  for (let attempt = 0; attempt < 20; attempt++) {
    try {
      const response = await fetch(url, {
        method: "POST",
        body,
        signal: AbortSignal.timeout(2000),
      });
      const value = await boundedText(response, 1_000_000);
      const parsed = new XMLParser().parse(value).ENVELOPE;
      if (
        String(parsed?.HEADER?.STATUS) === "1" &&
        parsed.BODY?.DATA?.COLLECTION?.COMPANY
      )
        return;
    } catch {
      /* Process startup and services may take a few seconds. */
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(
    "Tally restarted but its companies are not ready. Complete login or load companies, then Resume saves.",
  );
}
