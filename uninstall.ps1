param(
  [ValidateSet("PreserveData", "PurgeData", "CadenceOnly", "Detach", "Full")]
  [string]$Mode = "PreserveData",
  [string]$InstallDir = "",
  [string]$StateRoot = "",
  [switch]$PreUpgrade,
  [switch]$Force,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($InstallDir)) { $InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
try {
  if ($PreUpgrade) {
    $installEntry = Join-Path $InstallDir "scripts\lifecycle\Install.ps1"
    if (Test-Path -LiteralPath $installEntry -PathType Leaf) {
      & $installEntry -InstallRoot $InstallDir -StateRoot $StateRoot -PrepareUpgrade -NoStart -SkipCadence
    }
    exit 0
  }
  if ($DryRun) { Write-Host "Lifecycle V2 dry run: mode=$Mode root=$InstallDir"; exit 0 }
  $entry = Join-Path $InstallDir "scripts\lifecycle\Uninstall.ps1"
  if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) { throw "Lifecycle V2 uninstall entry is missing: $entry" }
  $mapped = switch ($Mode) {
    "Detach" { "PreserveData" }
    "Full" { "PurgeData" }
    default { $Mode }
  }
  & $entry -InstallRoot $InstallDir -StateRoot $StateRoot -Mode $mapped
  exit 0
} catch {
  Write-Error $_
  exit 1
}
