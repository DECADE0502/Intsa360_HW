param(
  [Parameter(Mandatory=$true)][ValidateSet("Install", "Uninstall")][string]$Operation,
  [Parameter(Mandatory=$true)][string]$EntryPath,
  [Parameter(Mandatory=$true)][string]$InstallRoot,
  [Parameter(Mandatory=$true)][string]$StateRoot,
  [Parameter(Mandatory=$true)][string]$ResultPath,
  [Parameter(Mandatory=$true)][string]$ProgressPath,
  [string]$PayloadRoot = "",
  [string]$Action = "Install",
  [string]$Mode = "PurgeData",
  [switch]$NoStart,
  [switch]$NoStop,
  [switch]$SkipCadence,
  [switch]$SkipRecoveryRegistration
)

$ErrorActionPreference = "Stop"
$resultCode = 9001
$process = $null

function ConvertTo-ProcessArgument {
  param([Parameter(Mandatory=$true)][AllowEmptyString()][string]$Value)
  if ($Value.IndexOf('"') -ge 0) { throw "Lifecycle argument contains an invalid quote character." }
  return '"' + $Value + '"'
}

try {
  $windows = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Windows)
  $powershell = Join-Path $windows "System32\WindowsPowerShell\v1.0\powershell.exe"
  if (-not (Test-Path -LiteralPath $powershell -PathType Leaf)) { throw "System Windows PowerShell is missing." }
  if (-not (Test-Path -LiteralPath $EntryPath -PathType Leaf)) { throw "Lifecycle entry is missing: $EntryPath" }
  $arguments = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $EntryPath,
    "-InstallRoot", $InstallRoot, "-StateRoot", $StateRoot, "-ProgressPath", $ProgressPath
  )
  if ($Operation -eq "Install") {
    if ([string]::IsNullOrWhiteSpace($PayloadRoot)) { throw "Install operation requires PayloadRoot." }
    $arguments += @("-PayloadRoot", $PayloadRoot, "-Action", $Action)
    if ($NoStart) { $arguments += "-NoStart" }
  } else {
    $arguments += @("-Mode", $Mode)
    if ($NoStop) { $arguments += "-NoStop" }
  }
  if ($SkipCadence) { $arguments += "-SkipCadence" }
  if ($SkipRecoveryRegistration) { $arguments += "-SkipRecoveryRegistration" }
  $argumentLine = (($arguments | ForEach-Object { ConvertTo-ProcessArgument -Value ([string]$_) }) -join " ")
  $startInfo = New-Object System.Diagnostics.ProcessStartInfo
  $startInfo.FileName = $powershell
  $startInfo.Arguments = $argumentLine
  $startInfo.UseShellExecute = $false
  $startInfo.CreateNoWindow = $true
  $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
  $process = New-Object System.Diagnostics.Process
  $process.StartInfo = $startInfo
  if (-not $process.Start()) { throw "Lifecycle process could not be started." }
  $process.WaitForExit()
  $resultCode = [int]$process.ExitCode
} catch {
  try {
    $runnerLog = Join-Path $StateRoot "logs\setup_runner.log"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $runnerLog) | Out-Null
    Add-Content -LiteralPath $runnerLog -Encoding UTF8 -Value ((Get-Date).ToString("s") + " " + $_.Exception.ToString())
  } catch {}
} finally {
  if ($null -ne $process) {
    try { $process.Dispose() }
    catch {}
  }
  try {
    $target = [System.IO.Path]::GetFullPath($ResultPath)
    $parent = Split-Path -Parent $target
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $temporary = $target + "." + [guid]::NewGuid().ToString("N") + ".tmp"
    [System.IO.File]::WriteAllText($temporary, [string]$resultCode, (New-Object System.Text.UTF8Encoding($false)))
    [System.IO.File]::Move($temporary, $target)
  } catch {}
}

exit 0
