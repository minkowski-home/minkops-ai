/** ODBC metadata only. No SELECT, SQL execution, row reader, or schema-by-sampling.
 * The fixed Windows helper uses the installed Tally driver and loopback port.
 * ODBC exposes top-level methods; it does not enumerate every nested XML/UDF.
 */
import { spawn } from "node:child_process";
import { join } from "node:path";

const SCRIPT = String.raw`
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$inputConfig = [Console]::In.ReadToEnd() | ConvertFrom-Json
$port = [int]$inputConfig.port
if ($port -lt 1 -or $port -gt 65535) { throw 'Invalid port' }
$dsnName = "TallyODBC64_$port"
$dsn = Get-OdbcDsn -Name $dsnName -Platform '64-bit' | Select-Object -First 1
if (!$dsn -or $dsn.DriverName -ne 'Tally ODBC Driver64' -or [int]$dsn.Attribute['Port'] -ne $port -or $dsn.Attribute['Server'] -notin @('(local)', 'localhost', '127.0.0.1')) { throw 'A local Tally ODBC DSN is required' }
$connection = [System.Data.Odbc.OdbcConnection]::new("DSN=$dsnName;")
try {
  $connection.Open()
  $tables = $connection.GetSchema('Tables')
  if ($tables.Rows.Count -gt 500) { throw 'Metadata scope too large' }
  $columnCount = 0
  $result = @($tables.Rows | ForEach-Object {
    $tableName = [string]$_['TABLE_NAME']
    $columns = $connection.GetSchema('Columns', @($null, $null, $tableName, $null))
    $columnCount += $columns.Rows.Count
    if ($columns.Rows.Count -gt 2000 -or $columnCount -gt 100000) { throw 'Metadata scope too large' }
    $fields = @($columns.Rows | ForEach-Object {
      @{ name = [string]$_['COLUMN_NAME']; type = [string]$_['TYPENAME']; nullable = ([string]$_['IS_NULLABLE'] -eq 'Y'); ordinal = [int]$_['ORDINAL_POSITION'] }
    })
    @{ table = $tableName; columns = $fields }
  })
  ConvertTo-Json -InputObject $result -Depth 5 -Compress
} finally { $connection.Dispose() }
`;

export async function tallySchema({ port = 9000 }) {
  if (!Number.isInteger(port) || port < 1 || port > 65535)
    throw new Error("Invalid Tally port.");
  if (process.platform !== "win32")
    throw new Error("Tally structure discovery requires the Windows Tally ODBC driver.");
  return new Promise((resolve, reject) => {
    const executable = join(process.env.SystemRoot || "C:\\Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
    const child = spawn(executable, ["-NoProfile", "-NonInteractive", "-EncodedCommand", Buffer.from(SCRIPT, "utf16le").toString("base64")], { windowsHide: true, stdio: ["pipe", "pipe", "ignore"] });
    const parts = [];
    let size = 0;
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error("Tally metadata timed out. Enable the local ODBC service and retry."));
    }, 60000);
    child.stdout.on("data", (part) => {
      size += part.length;
      if (size > 16_000_000) { child.kill(); reject(new Error("Tally metadata exceeds the supported size.")); }
      else parts.push(part);
    });
    child.on("error", (error) => { clearTimeout(timer); reject(error); });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) return reject(new Error("Enable Tally ODBC on this PC and install its 64-bit driver, then retry discovery."));
      try { resolve(JSON.parse(Buffer.concat(parts).toString("utf8").replace(/^\uFEFF/, ""))); }
      catch { reject(new Error("Tally metadata could not be read.")); }
    });
    child.stdin.on("error", () => {});
    child.stdin.end(JSON.stringify({ port }));
  });
}
