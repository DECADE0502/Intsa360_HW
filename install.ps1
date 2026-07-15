param(
  [string]$InstallRoot = "",
  [string]$StateRoot = "",
  [string]$PayloadRoot = "",
  [ValidateSet("Install", "Upgrade", "Repair", "Reinstall")]
  [string]$Action = "Install",
  [switch]$NoStart,
  [switch]$SkipCadence,
  [switch]$SkipRecoveryRegistration
)

$ErrorActionPreference = "Stop"
$sourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
  $InstallRoot = Join-Path $env:ProgramFiles "Insta360\HWAgent"
}
if ([string]::IsNullOrWhiteSpace($StateRoot)) {
  $StateRoot = Join-Path $env:LOCALAPPDATA "Insta360_HW"
}
if ([string]::IsNullOrWhiteSpace($PayloadRoot)) {
  $release = Join-Path (Split-Path -Parent $sourceRoot) "HWAgent_release"
  $PayloadRoot = if (Test-Path -LiteralPath (Join-Path $release "install_manifest.json") -PathType Leaf) {
    $release
  } else {
    $sourceRoot
  }
}

$entry = Join-Path $PayloadRoot "scripts\lifecycle_v3\Install.ps1"
try {
  if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) {
    throw "Lifecycle V3 installer entry is missing: $entry"
  }
  & $entry -InstallRoot $InstallRoot -StateRoot $StateRoot -PayloadRoot $PayloadRoot -Action $Action `
    -NoStart:$NoStart -SkipCadence:$SkipCadence -SkipRecoveryRegistration:$SkipRecoveryRegistration
  if (-not $?) { throw "Lifecycle V3 installer failed." }
  exit 0
} catch {
  Write-Error $_
  exit 1
}
