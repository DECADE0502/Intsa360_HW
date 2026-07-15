param(
  [ValidateSet("PreserveData", "PurgeData", "Detach", "Full")]
  [string]$Mode = "PurgeData",
  [string]$InstallDir = "",
  [string]$StateRoot = "",
  [switch]$NoStop,
  [switch]$SkipCadence,
  [switch]$SkipRecoveryRegistration,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$sourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($InstallDir)) {
  $InstallDir = Join-Path $env:ProgramFiles "Insta360\HWAgent"
}
if ([string]::IsNullOrWhiteSpace($StateRoot)) {
  $StateRoot = Join-Path $env:LOCALAPPDATA "Insta360_HW"
}
$mappedMode = if ($Mode -eq "Detach") { "PreserveData" } elseif ($Mode -eq "Full") { "PurgeData" } else { $Mode }

try {
  if ($DryRun) { Write-Host "Lifecycle V3 dry run: mode=$mappedMode root=$InstallDir"; exit 0 }
  $entry = Join-Path $InstallDir "maintenance\Uninstall.ps1"
  if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) {
    $metadataPath = Join-Path $InstallDir "installation.json"
    if (Test-Path -LiteralPath $metadataPath -PathType Leaf) {
      $metadata = Get-Content -LiteralPath $metadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
      $relative = [string]$metadata.active_runtime
      if ([int]$metadata.schema_version -ne 3 -or [string]$metadata.product -ne "Insta360_HW" -or
          $relative -notmatch '^runtime/[0-9A-Za-z.+-]+\+[0-9a-fA-F]{40}$') {
        throw "Installation metadata is invalid."
      }
      $runtime = [System.IO.Path]::GetFullPath((Join-Path $InstallDir $relative.Replace("/", "\")))
      $runtimeParent = [System.IO.Path]::GetFullPath((Join-Path $InstallDir "runtime")).TrimEnd("\")
      if (-not $runtime.StartsWith($runtimeParent + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Active runtime pointer escapes the installation."
      }
      $entry = Join-Path $runtime "scripts\lifecycle_v3\Uninstall.ps1"
    }
  }
  if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) {
    $entry = Join-Path $sourceRoot "scripts\lifecycle_v3\Uninstall.ps1"
  }
  if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) {
    throw "Lifecycle V3 uninstall entry is missing. Use Insta360_HW_Setup.exe or Windows Settings."
  }
  & $entry -InstallRoot $InstallDir -StateRoot $StateRoot -Mode $mappedMode `
    -NoStop:$NoStop -SkipCadence:$SkipCadence -SkipRecoveryRegistration:$SkipRecoveryRegistration
  if (-not $?) { throw "Lifecycle V3 uninstaller failed." }
  exit 0
} catch {
  Write-Error $_
  exit 1
}
