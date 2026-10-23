<#
Build the Windows installer from an export of this repository, on Windows.

Export what the Windows app needs (apps/windows-app, connectors/desktop,
platform/desktop-runtime and scripts) with `git archive`, then run from that
export, with a portable Node 24 when the machine has none:

  powershell.exe -ExecutionPolicy Bypass -File <export>\scripts\windows_build.ps1 -Kind dev -Node <node folder>

-Kind dev builds Minkops Dev, the local stack's companion installed beside the
production one; -Kind candidate an unsigned release candidate; -Kind release a
release signed with the organization's certificate (see docs/windows-app.md).

Each step must exit cleanly, and the build must write one installer for this
version, at least 50 MB, or nothing is reported as built: npm can return
success after electron-builder has failed to package.
#>
param(
  [ValidateSet("dev", "candidate", "release")] [string] $Kind = "dev",
  [string] $Node = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if ($Node) { $env:Path = "$Node;$env:Path" }
$app = Join-Path $root "apps\windows-app"
$version = (Get-Content (Join-Path $app "package.json") -Raw | ConvertFrom-Json).version
$started = Get-Date

function Step($folder, $command) {
  Write-Output "== $folder> npm $command"
  Push-Location (Join-Path $root $folder)
  try {
    & npm.cmd @($command -split ' ')
    if ($LASTEXITCODE -ne 0) { throw "npm $command failed in $folder ($LASTEXITCODE)" }
  } finally { Pop-Location }
}

$package = @{ dev = "run package:win:dev"; candidate = "run package:win:candidate"; release = "run package:win" }[$Kind]
Step "connectors\desktop" "ci"
Step "apps\windows-app" "ci"
Step "apps\windows-app" "test"
Step "apps\windows-app" $package

$written = @(Get-ChildItem (Join-Path $app "release\*.exe") |
  Where-Object { $_.Name -like "*-$version.exe" -and $_.LastWriteTime -ge $started })
if ($written.Count -ne 1) { throw "This build wrote no single installer for $version ($($written.Count) found)." }
$installer = $written[0]
if ($installer.Length -lt 50MB) { throw "$($installer.Name) is $($installer.Length) bytes: too small to be a complete installer." }
"{0}  {1} bytes  SHA256 {2}" -f $installer.Name, $installer.Length, (Get-FileHash $installer.FullName -Algorithm SHA256).Hash
