param([string]$CaptureAutoLoadDir = "")

$ErrorActionPreference = "Stop"
$cadenceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$toolRoot = Split-Path -Parent $cadenceDir
$repair = Join-Path $toolRoot "scripts\redeploy_cadence_loader.ps1"
if (-not (Test-Path -LiteralPath $repair -PathType Leaf)) {
  throw "Cadence integration repair script is missing: $repair"
}

if (-not [string]::IsNullOrWhiteSpace($CaptureAutoLoadDir)) {
  & $repair -CaptureAutoLoadDir $CaptureAutoLoadDir -Force
} else {
  & $repair -Force
}
