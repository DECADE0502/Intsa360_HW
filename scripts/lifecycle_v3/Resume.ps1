param()

$ErrorActionPreference = "Stop"

function Resolve-RecoveryRuntime {
  param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$RelativePath
  )
  if ($RelativePath -cnotmatch '^runtime/[0-9A-Za-z][0-9A-Za-z._-]*\+[0-9a-f]{40}$' -or
      $RelativePath.Contains("\")) {
    throw "Protected recovery runtime pointer is invalid."
  }
  $runtimeParent = [System.IO.Path]::GetFullPath((Join-Path $InstallRoot "runtime")).TrimEnd("\")
  $runtimeRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $InstallRoot ($RelativePath.Replace("/", "\")))
  ).TrimEnd("\")
  if (-not $runtimeRoot.StartsWith(
      $runtimeParent + [System.IO.Path]::DirectorySeparatorChar,
      [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Protected recovery runtime pointer escapes the installation root."
  }
  return $runtimeRoot
}

try {
  $jobId = Split-Path -Leaf $PSScriptRoot
  if ($jobId -cnotmatch '^[0-9a-f]{32}$') { throw "Protected recovery job identity is invalid." }
  $descriptorPath = Join-Path $PSScriptRoot "transaction.json"
  if (-not (Test-Path -LiteralPath $descriptorPath -PathType Leaf)) {
    throw "Protected recovery transaction is missing."
  }
  $descriptor = Get-Content -LiteralPath $descriptorPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $outcome = [string]$descriptor.outcome
  if ([int]$descriptor.schema -ne 3 -or [string]$descriptor.product -ne "Insta360_HW" -or
      [string]$descriptor.job_id -cne $jobId -or
      ($outcome -cne "pending" -and $outcome -cne "completed") -or
      -not ($descriptor.skip_cadence -is [bool])) {
    throw "Protected recovery transaction is invalid."
  }

  $installRoot = [System.IO.Path]::GetFullPath([string]$descriptor.install_root).TrimEnd("\")
  $stateRoot = [System.IO.Path]::GetFullPath([string]$descriptor.state_root).TrimEnd("\")
  $relative = if ($outcome -ceq "completed") {
    [string]$descriptor.new_relative
  } else {
    [string]$descriptor.old_relative
  }
  $runtimeRoot = Resolve-RecoveryRuntime -InstallRoot $installRoot -RelativePath $relative
  $recover = Join-Path $runtimeRoot "scripts\lifecycle_v3\Recover.ps1"
  if (-not (Test-Path -LiteralPath $recover -PathType Leaf) -and $outcome -ceq "completed") {
    $runtimeRoot = Resolve-RecoveryRuntime -InstallRoot $installRoot -RelativePath ([string]$descriptor.old_relative)
    $recover = Join-Path $runtimeRoot "scripts\lifecycle_v3\Recover.ps1"
  }
  if (-not (Test-Path -LiteralPath $recover -PathType Leaf)) {
    throw "Trusted recovery script is unavailable."
  }

  $parameters = @{
    InstallRoot = $installRoot
    StateRoot = $stateRoot
    JobId = $jobId
    RecoveryTaskName = "Insta360_HW_Recovery_" + $jobId
    NoRestart = $true
  }
  if ([bool]$descriptor.skip_cadence) { $parameters["SkipCadence"] = $true }
  & $recover @parameters
  if (-not $?) { exit 1 }
  exit 0
} catch {
  Write-Error $_.Exception.Message
  exit 1
}
