param([switch]$SkipNetwork)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$Workspace = Split-Path -Parent $Root
$Errors = New-Object System.Collections.Generic.List[string]
function Add-Failure { param([string]$Message) $script:Errors.Add($Message) | Out-Null }

$Version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw -Encoding UTF8).Trim()
if ($Version -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?$') {
  Add-Failure "VERSION is not semantic: $Version"
}
$Notice = Get-Content -LiteralPath (Join-Path $Root "UPDATE_NOTICE.json") -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$Notice.version -ne $Version) { Add-Failure "UPDATE_NOTICE.version does not match VERSION." }
if (@($Notice.highlights).Count -eq 0) { Add-Failure "UPDATE_NOTICE.highlights is empty." }

$Release = Join-Path $Workspace "HWAgent_release"
foreach ($relative in @(
  "Insta360_HW.exe", "VERSION", "REVISION", "install_manifest.json",
  "app\backend\suite_app.py", "app\frontend\index.html", "runtime\python\python.exe",
  "scripts\lifecycle\Contract.ps1", "scripts\lifecycle\Runtime.ps1", "scripts\lifecycle\Worker.ps1"
)) {
  if (-not (Test-Path -LiteralPath (Join-Path $Release $relative) -PathType Leaf)) {
    Add-Failure "Release payload is missing $relative"
  }
}
foreach ($forbidden in @("data", "frontend", "tests", "docs", ".git")) {
  if (Test-Path -LiteralPath (Join-Path $Release $forbidden)) { Add-Failure "Release payload contains forbidden mutable/development path: $forbidden" }
}
Get-ChildItem -LiteralPath $Release -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | ForEach-Object {
  Add-Failure ("Release payload contains Python cache artifact: " + $_.FullName)
}
Get-ChildItem -LiteralPath $Release -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue | ForEach-Object {
  Add-Failure ("Release payload contains Python cache artifact: " + $_.FullName)
}
if (Test-Path -LiteralPath (Join-Path $Release "install_manifest.json")) {
  $InstallManifest = Get-Content -LiteralPath (Join-Path $Release "install_manifest.json") -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($InstallManifest.product -ne "Insta360_HW" -or $InstallManifest.layout -ne "runtime-v2" -or [string]$InstallManifest.version -ne $Version) {
    Add-Failure "Release install manifest identity is invalid."
  }
}

$ParseFailed = $false
Get-ChildItem -LiteralPath $Root -Recurse -Filter *.ps1 -File | Where-Object { $_.FullName -notmatch '\\node_modules\\|\\data\\' } | ForEach-Object {
  $tokens = $null
  $parseErrors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$parseErrors) | Out-Null
  if ($parseErrors.Count -gt 0) {
    $ParseFailed = $true
    Add-Failure ("PowerShell parse failed: " + $_.FullName + " - " + (($parseErrors | ForEach-Object Message) -join "; "))
  }
}
if (-not $ParseFailed) { Write-Host "[OK] PowerShell scripts parse" -ForegroundColor Green }

& python -m pytest -q
if ($LASTEXITCODE -ne 0) { Add-Failure "pytest failed." } else { Write-Host "[OK] pytest" -ForegroundColor Green }
Push-Location (Join-Path $Root "frontend")
try { & npm run build; if ($LASTEXITCODE -ne 0) { Add-Failure "frontend build failed." } else { Write-Host "[OK] frontend build" -ForegroundColor Green } }
finally { Pop-Location }

$ManifestPath = Join-Path $Workspace "update-manifest.json"
if (Test-Path -LiteralPath $ManifestPath) {
  & python -c "import json, pathlib; from app.backend.release_manifest import ReleaseManifest; ReleaseManifest.parse(json.loads(pathlib.Path(r'$ManifestPath').read_text(encoding='utf-8-sig'))); print('manifest OK')"
  if ($LASTEXITCODE -ne 0) { Add-Failure "update-manifest.json is invalid." }
  if (-not $SkipNetwork) {
    $Remote = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($asset in @($Remote.assets.runtime, $Remote.assets.setup)) {
      try {
        $probe = Invoke-WebRequest -Uri ([string]$asset.url) -Method Head -MaximumRedirection 8 -TimeoutSec 20 -UseBasicParsing
        if ($probe.StatusCode -lt 200 -or $probe.StatusCode -ge 400) { Add-Failure "Release asset is unreachable: $($asset.url)" }
      } catch { Add-Failure "Release asset is unreachable: $($asset.url) - $($_.Exception.Message)" }
    }
  }
}

if ($Errors.Count -gt 0) {
  Write-Host "PRE-RELEASE CHECK FAILED" -ForegroundColor Red
  foreach ($failure in $Errors) { Write-Host ("  - " + $failure) -ForegroundColor Red }
  exit 1
}
Write-Host "ALL PRE-RELEASE CHECKS PASSED" -ForegroundColor Green
