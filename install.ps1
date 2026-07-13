param(
  [string]$InstallRoot = "",
  [string]$StateRoot = "",
  [switch]$NoStart,
  [switch]$SkipCadence,
  [switch]$PrepareUpgrade
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($InstallRoot)) { $InstallRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$entry = Join-Path $InstallRoot "scripts\lifecycle\Install.ps1"
try {
  if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) { throw "Lifecycle V2 installer entry is missing: $entry" }
  & $entry -InstallRoot $InstallRoot -StateRoot $StateRoot -NoStart:$NoStart -SkipCadence:$SkipCadence -PrepareUpgrade:$PrepareUpgrade
  exit 0
} catch {
  Write-Error $_
  exit 1
}
