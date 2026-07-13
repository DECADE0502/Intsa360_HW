param(
  [Parameter(Mandatory=$true)][string]$InstallRoot,
  [string]$StateRoot = "",
  [switch]$NoRestart,
  [switch]$Elevated
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Contract.ps1")

$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot).TrimEnd("\")
Assert-HwLifecycleRuntimeRoot -Path $InstallRoot -AllowMissing | Out-Null
if ([string]::IsNullOrWhiteSpace($StateRoot)) { $StateRoot = Get-HwLifecycleStateRoot -RuntimeRoot $InstallRoot }
$StateRoot = [System.IO.Path]::GetFullPath($StateRoot).TrimEnd("\")
$transactions = Join-Path $StateRoot "lifecycle\transactions"
if (-not (Test-Path -LiteralPath $transactions -PathType Container)) { return }

function Test-LiveLifecycleWorker {
  param([Parameter(Mandatory=$true)]$Journal)
  $jobId = [string]$Journal.job_id
  if ([string]::IsNullOrWhiteSpace($jobId)) { return $false }
  $job = Read-HwLifecycleJson -Path (Get-HwLifecycleJobPath -StateRoot $StateRoot -JobId $jobId)
  if ($null -eq $job -or [string]$job.phase -notin @(
    "awaiting_elevation", "committing", "switching", "integrating", "verifying_runtime"
  )) { return $false }
  try {
    $pidValue = [int]$job.worker_pid
    if ($pidValue -le 0) { return $false }
    $process = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $pidValue) -ErrorAction SilentlyContinue
    if ($null -eq $process -or [string]::IsNullOrWhiteSpace([string]$process.CommandLine)) { return $false }
    $commandLine = [string]$process.CommandLine
    return $commandLine.IndexOf("Worker.ps1", [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
      $commandLine.IndexOf($jobId, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
  } catch { return $false }
}

function Test-HwLifecycleAdministrator {
  $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
  return $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-HwElevatedRecovery {
  foreach ($value in @($PSCommandPath, $InstallRoot, $StateRoot)) {
    if ($value.Contains('"')) { throw "Recovery path contains an unsupported quote character." }
  }
  $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath +
    '" -InstallRoot "' + $InstallRoot + '" -StateRoot "' + $StateRoot + '" -Elevated'
  if ($NoRestart) { $arguments += ' -NoRestart' }
  $startInfo = New-Object System.Diagnostics.ProcessStartInfo
  $startInfo.FileName = "powershell.exe"
  $startInfo.Arguments = $arguments
  $startInfo.WorkingDirectory = $ScriptDir
  $startInfo.UseShellExecute = $true
  $startInfo.Verb = "runas"
  $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
  $process = [System.Diagnostics.Process]::Start($startInfo)
  if ($null -eq $process) { throw "Windows did not start the elevated recovery process." }
  $process.WaitForExit()
  exit $process.ExitCode
}

$pending = @()
foreach ($directory in Get-ChildItem -LiteralPath $transactions -Directory -ErrorAction SilentlyContinue) {
  $journalPath = Join-Path $directory.FullName "journal.json"
  $journal = Read-HwLifecycleJson -Path $journalPath
  if ($null -eq $journal -or [string]$journal.phase -in @("completed", "rolled_back")) { continue }
  if ([string]$journal.install_root -and -not ([System.IO.Path]::GetFullPath([string]$journal.install_root).TrimEnd("\") -ieq $InstallRoot)) { continue }
  $pending += [pscustomobject]@{ directory = $directory; journal = $journal }
}

$active = @($pending | Where-Object { Test-LiveLifecycleWorker -Journal $_.journal })
if ($active.Count -gt 0) {
  [Console]::Error.WriteLine("Lifecycle update worker is still active; recovery was not started.")
  exit 23
}

if ($pending.Count -gt 0 -and -not (Test-HwLifecycleAdministrator)) {
  if ($Elevated) { throw "Recovery was relaunched but did not receive administrator rights." }
  Invoke-HwElevatedRecovery
}

foreach ($item in @($pending | Sort-Object { [string]$_.journal.updated_at })) {
  $worker = Join-Path $ScriptDir "Worker.ps1"
  if (-not (Test-Path -LiteralPath $worker -PathType Leaf)) {
    throw "Trusted lifecycle recovery worker is missing: $worker"
  }
  & $worker -Action Recover -InstallRoot $InstallRoot -StateRoot $StateRoot `
    -JobId ([string]$item.journal.job_id) -NoRestart:$NoRestart
}
