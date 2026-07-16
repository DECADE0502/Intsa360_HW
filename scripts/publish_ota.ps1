param(
  [string]$BundleDir = "",
  [string]$Repository = "DECADE0502/Intsa360_HW",
  [string]$Branch = "ota",
  [string]$RemoteUrl = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$Workspace = Split-Path -Parent $Root
$Version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw -Encoding UTF8).Trim()
if ([string]::IsNullOrWhiteSpace($BundleDir)) {
  $BundleDir = Join-Path $Workspace ("Insta360_HW_release_" + $Version)
}
$BundleDir = [System.IO.Path]::GetFullPath($BundleDir)
$Publisher = Join-Path $Root "scripts\release\git_ota.py"
$PublicKey = Join-Path $Root "config\update_public_key.pem"
$Arguments = @(
  $Publisher,
  "--bundle-dir", $BundleDir,
  "--public-key", $PublicKey,
  "--source-repo", $Root,
  "--repository", $Repository,
  "--branch", $Branch,
  "--verify-public"
)
if (-not [string]::IsNullOrWhiteSpace($RemoteUrl)) {
  $Arguments += @("--remote-url", $RemoteUrl)
}

Write-Host "Publishing signed OTA snapshot through Git send-pack..." -ForegroundColor Cyan
& python @Arguments
if ($LASTEXITCODE -ne 0) { throw "Git-only OTA publication failed." }
Write-Host "Git-only OTA publication completed and public manifest bytes were verified." -ForegroundColor Green
