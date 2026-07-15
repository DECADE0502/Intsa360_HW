param(
  [string]$RuntimeDir = "",
  [string]$BundleDir = "",
  [string]$Revision = "",
  [switch]$SkipTests
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$Workspace = Split-Path -Parent $Root
$Errors = New-Object System.Collections.Generic.List[string]
function Add-Failure { param([string]$Message) $script:Errors.Add($Message) | Out-Null }

$Version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw -Encoding UTF8).Trim()
if ($Version -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?$') {
  Add-Failure "VERSION is not semantic: $Version"
}
if ([string]::IsNullOrWhiteSpace($Revision)) { $Revision = (& git -C $Root rev-parse HEAD 2>$null).Trim().ToLowerInvariant() }
if ($Revision -notmatch '^[a-f0-9]{40}$') { Add-Failure "A full git revision is required." }
$Notice = Get-Content -LiteralPath (Join-Path $Root "UPDATE_NOTICE.json") -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$Notice.version -cne $Version) { Add-Failure "UPDATE_NOTICE.version does not match VERSION." }
if (@($Notice.highlights).Count -eq 0) { Add-Failure "UPDATE_NOTICE.highlights is empty." }

if ([string]::IsNullOrWhiteSpace($RuntimeDir)) {
  $RuntimeDir = Join-Path $Workspace ("HWAgent_build\" + $Version + "+" + $Revision + "\runtime")
}
if ([string]::IsNullOrWhiteSpace($BundleDir)) { $BundleDir = Join-Path $Workspace ("Insta360_HW_release_" + $Version) }

foreach ($relative in @(
  "Insta360_HW.exe", "VERSION", "REVISION", "install_manifest.json",
  "app\backend\suite_app.py", "app\frontend\index.html", "runtime\python\python.exe",
  "scripts\lifecycle_v3\Worker.ps1", "scripts\lifecycle_v3\Install.ps1",
  "scripts\lifecycle_v3\Uninstall.ps1", "scripts\lifecycle_v3\SetupRecover.ps1",
  "config\update_public_key.pem"
)) {
  if (-not (Test-Path -LiteralPath (Join-Path $RuntimeDir $relative) -PathType Leaf)) {
    Add-Failure "Release payload is missing $relative"
  }
}
foreach ($forbidden in @("data", "frontend", "tests", "docs", ".git", "scripts\release")) {
  if (Test-Path -LiteralPath (Join-Path $RuntimeDir $forbidden)) {
    Add-Failure "Release payload contains forbidden mutable/development path: $forbidden"
  }
}
Get-ChildItem -LiteralPath $RuntimeDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | ForEach-Object {
  Add-Failure ("Release payload contains Python cache artifact: " + $_.FullName)
}
Get-ChildItem -LiteralPath $RuntimeDir -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue | ForEach-Object {
  Add-Failure ("Release payload contains Python cache artifact: " + $_.FullName)
}
$identityPath = Join-Path $RuntimeDir "install_manifest.json"
if (Test-Path -LiteralPath $identityPath -PathType Leaf) {
  $Identity = Get-Content -LiteralPath $identityPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ([int]$Identity.schema -ne 3 -or [string]$Identity.product -ne "Insta360_HW" -or
      [string]$Identity.layout -ne "runtime-v3" -or [string]$Identity.version -cne $Version -or
      ([string]$Identity.revision).ToLowerInvariant() -cne $Revision) {
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

if (-not $SkipTests) {
  & python -m pytest -q
  if ($LASTEXITCODE -ne 0) { Add-Failure "pytest failed." } else { Write-Host "[OK] pytest" -ForegroundColor Green }
  Push-Location (Join-Path $Root "frontend")
  try {
    & npm run test:unit
    if ($LASTEXITCODE -ne 0) { Add-Failure "frontend unit tests failed." }
    & npm run build
    if ($LASTEXITCODE -ne 0) { Add-Failure "frontend build failed." } else { Write-Host "[OK] frontend build" -ForegroundColor Green }
  } finally { Pop-Location }
}

$releaseTool = Join-Path $Root "scripts\release\release_bundle.py"
$publicKey = Join-Path $Root "config\update_public_key.pem"
if (Test-Path -LiteralPath $BundleDir -PathType Container) {
  & python $releaseTool verify --bundle-dir $BundleDir --public-key $publicKey --version $Version --revision $Revision
  if ($LASTEXITCODE -ne 0) { Add-Failure "Signed release bundle verification failed." }
} else {
  Add-Failure "Release bundle is missing: $BundleDir"
}

if ($Errors.Count -gt 0) {
  Write-Host "PRE-RELEASE CHECK FAILED" -ForegroundColor Red
  foreach ($failure in $Errors) { Write-Host ("  - " + $failure) -ForegroundColor Red }
  exit 1
}
Write-Host "ALL LOCAL RELEASE CHECKS PASSED" -ForegroundColor Green
