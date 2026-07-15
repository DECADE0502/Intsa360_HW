param(
  [string]$OutputDir = "",
  [string]$Version = "",
  [string]$Revision = "",
  [ValidateSet("dev", "published")][string]$BuildKind = "dev",
  [long]$SourceDateEpoch = 0,
  [switch]$SkipFrontend,
  [switch]$PreflightOnly,
  [string]$GitExecutable = "git"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$Workspace = Split-Path -Parent $Root
if ([string]::IsNullOrWhiteSpace($OutputDir)) { $OutputDir = Join-Path $Workspace "HWAgent_build\runtime" }
$Release = [System.IO.Path]::GetFullPath($OutputDir)
if ([string]::IsNullOrWhiteSpace($Version)) {
  $Version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw -Encoding UTF8).Trim()
}
if ([string]::IsNullOrWhiteSpace($Revision)) {
  $Revision = (& $GitExecutable -C $Root rev-parse HEAD 2>$null).Trim().ToLowerInvariant()
}
if ($Revision -notmatch '^[a-f0-9]{40}$') { throw "A full git revision is required for a canonical build." }

function Assert-PublicBuildIdentity {
  if ($BuildKind -ne "published") { return }
  $dirty = @(& $GitExecutable -C $Root status --porcelain --untracked-files=normal)
  if ($LASTEXITCODE -ne 0) { throw "Unable to verify the git worktree." }
  if ($dirty.Count -gt 0) { throw "Public build requires a clean git worktree." }
  $existingTags = @(& $GitExecutable -C $Root tag --list ("v" + $Version))
  if ($LASTEXITCODE -ne 0) { throw "Unable to verify existing public build tags." }
  if ($existingTags.Count -gt 0) { throw "Version $Version already has a public build tag." }
  if ($SkipFrontend) { throw "Published builds cannot skip the frontend build." }
}

Assert-PublicBuildIdentity
if ($PreflightOnly) {
  Write-Host "Canonical runtime preflight passed for $BuildKind $Version at $Revision."
  exit 0
}
if ($SourceDateEpoch -le 0) {
  $timestamp = (& $GitExecutable -C $Root show -s --format=%ct $Revision 2>$null)
  if ($LASTEXITCODE -ne 0 -or $null -eq $timestamp) { throw "Unable to resolve the git commit timestamp." }
  $SourceDateEpoch = [long](([string]$timestamp).Trim())
}
if ($SourceDateEpoch -le 0) { throw "A valid git commit timestamp is required for a canonical build." }

$Staging = Join-Path (Split-Path -Parent $Release) ("." + (Split-Path -Leaf $Release) + "." + [guid]::NewGuid().ToString("N") + ".staging")
if (Test-Path -LiteralPath $Staging) { Remove-Item -LiteralPath $Staging -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Staging | Out-Null

function Copy-ReleaseTree {
  param([Parameter(Mandatory=$true)][string]$Source, [Parameter(Mandatory=$true)][string]$Destination)
  if (-not (Test-Path -LiteralPath $Source -PathType Container)) { return }
  New-Item -ItemType Directory -Force -Path $Destination | Out-Null
  & robocopy $Source $Destination /E /XJ /XD "__pycache__" ".pytest_cache" "node_modules" ".vite" "src" "dist" "tests" "docs" "archive" /XF "*.pyc" "local.json" | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $Source (exit $LASTEXITCODE)" }
}

function Remove-PythonCacheArtifacts {
  param([Parameter(Mandatory=$true)][string]$Root)
  $cacheDirs = @(Get-ChildItem -LiteralPath $Root -Directory -Filter "__pycache__" -Recurse -Force -ErrorAction SilentlyContinue)
  $cacheDirs |
    Sort-Object { $_.FullName.Length } -Descending |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
  Get-ChildItem -LiteralPath $Root -File -Filter "*.pyc" -Recurse -Force -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
}

function Assert-NoPythonCacheArtifacts {
  param([Parameter(Mandatory=$true)][string]$Root)
  $artifact = Get-ChildItem -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "__pycache__" -or $_.Extension -ieq ".pyc" } |
    Select-Object -First 1
  if ($null -ne $artifact) {
    throw "Runtime payload contains Python cache artifact after finalization: $($artifact.FullName)"
  }
}

try {
  Write-Host "[1/6] Building immutable runtime tree: $Release" -ForegroundColor Cyan
  Copy-ReleaseTree -Source (Join-Path $Root "app\backend") -Destination (Join-Path $Staging "app\backend")
  foreach ($dir in @("cadence", "config", "plugins", "scripts", "tools")) {
    Copy-ReleaseTree -Source (Join-Path $Root $dir) -Destination (Join-Path $Staging $dir)
  }

  foreach ($devScript in @(
    "build_frontend.ps1", "build_installer.ps1", "build_release.ps1", "build_release_bundle.ps1",
    "bump_version.ps1", "pre_release_check.ps1", "publish_release.ps1", "verify_all.ps1"
  )) {
    Remove-Item -LiteralPath (Join-Path $Staging ("scripts\" + $devScript)) -Force -ErrorAction SilentlyContinue
  }
  foreach ($devPath in @("scripts\lib\EmbeddedPython.ps1", "scripts\release")) {
    Remove-Item -LiteralPath (Join-Path $Staging $devPath) -Recurse -Force -ErrorAction SilentlyContinue
  }

  Write-Host "[2/6] Building frontend..." -ForegroundColor Cyan
  if ($SkipFrontend) {
    Copy-ReleaseTree -Source (Join-Path $Root "app\frontend") -Destination (Join-Path $Staging "app\frontend")
  } else {
    & (Join-Path $Root "scripts\build_frontend.ps1") -Target (Join-Path $Staging "app\frontend")
    if ($LASTEXITCODE -ne 0) { throw "Frontend release build failed." }
  }

  Write-Host "[3/6] Building stable launcher..." -ForegroundColor Cyan
  & (Join-Path $Root "launcher\build.ps1") -Output (Join-Path $Staging "Insta360_HW.exe") -Version $Version
  if ($LASTEXITCODE -ne 0) { throw "Launcher release build failed." }

  $keepFiles = @(
    "Insta360_HW.exe",
    "launch_tool_suite.ps1",
    "launch_tool_suite_hidden.vbs",
    "iac_jump.bat",
    "VERSION",
    "REVISION",
    "UPDATE_NOTICE.json"
  )
  foreach ($name in $keepFiles) {
    if ($name -eq "Insta360_HW.exe") { continue }
    $source = Join-Path $Root $name
    if (Test-Path -LiteralPath $source -PathType Leaf) {
      Copy-Item -LiteralPath $source -Destination (Join-Path $Staging $name) -Force
    }
  }
  Set-Content -LiteralPath (Join-Path $Staging "VERSION") -Value $Version -Encoding UTF8
  Set-Content -LiteralPath (Join-Path $Staging "REVISION") -Value $Revision -Encoding UTF8
  $noticePath = Join-Path $Staging "UPDATE_NOTICE.json"
  $notice = Get-Content -LiteralPath $noticePath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ([string]$notice.version -cne $Version) { throw "UPDATE_NOTICE.json version does not match VERSION." }
  $notice.revision = $Revision
  $notice | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $noticePath -Encoding UTF8

  Write-Host "[4/6] Preparing verified embedded Python..." -ForegroundColor Cyan
  . (Join-Path $Root "scripts\lib\EmbeddedPython.ps1")
  $runtimePyDir = Join-Path $Staging "runtime\python"
  Download-EmbeddedPython -OutDir $runtimePyDir
  Install-HwAgentRuntimeWheels -PythonDir $runtimePyDir
  & (Join-Path $runtimePyDir "python.exe") -c "import cryptography, fastapi, multipart, openpyxl, pydantic, starlette, uvicorn"
  if ($LASTEXITCODE -ne 0) { throw "Embedded Python dependency verification failed." }

  Write-Host "[5/6] Writing runtime-v3 identity..." -ForegroundColor Cyan
  $generatedAt = [DateTimeOffset]::FromUnixTimeSeconds($SourceDateEpoch).UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ssZ")
  $manifest = [ordered]@{
    schema = 3
    product = "Insta360_HW"
    version = $Version
    revision = $Revision
    build_kind = $BuildKind
    layout = "runtime-v3"
    generated_at = $generatedAt
    state_root = "%LOCALAPPDATA%\Insta360_HW"
    mutable_paths = @("data", "config/local.json", "plugins/user", "logs", "lifecycle")
    runtime_paths = @("app/backend", "app/frontend", "cadence", "config", "plugins", "scripts", "tools", "runtime")
    excluded_dev_paths = @("frontend", "tests", "docs", ".git", "data")
  }
  $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Staging "install_manifest.json") -Encoding UTF8

  Write-Host "[6/6] Validating runtime-v3 payload..." -ForegroundColor Cyan
  $validator = @'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
from app.backend.contracts.releases import ReleaseManifestV3
from app.backend.lifecycle_v3_archive import validate_payload
identity = json.loads((root / "install_manifest.json").read_text(encoding="utf-8-sig"))
manifest = ReleaseManifestV3.model_validate({
    "schema_version": 3,
    "version": identity["version"],
    "revision": identity["revision"],
    "build_kind": identity["build_kind"],
    "published_at": identity["generated_at"],
    "min_updater_version": "0.4.0",
    "assets": [{"name": "fixture.zip", "url": "https://example.invalid/fixture.zip", "size": 1, "sha256": "a" * 64}],
    "signature": "validation-only",
})
validate_payload(root, manifest)
'@
  $ValidatorPath = Join-Path ([System.IO.Path]::GetTempPath()) `
    ("insta360_runtime_validator_" + [guid]::NewGuid().ToString("N") + ".py")
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($ValidatorPath, $validator, $utf8NoBom)
  try {
    & (Join-Path $runtimePyDir "python.exe") $ValidatorPath $Staging
    if ($LASTEXITCODE -ne 0) { throw "Runtime-v3 payload validation failed." }
  } finally {
    Remove-Item -LiteralPath $ValidatorPath -Force -ErrorAction SilentlyContinue
  }

  Remove-PythonCacheArtifacts -Root $Staging
  Assert-NoPythonCacheArtifacts -Root $Staging

  if (Test-Path -LiteralPath $Release) { Remove-Item -LiteralPath $Release -Recurse -Force }
  Move-Item -LiteralPath $Staging -Destination $Release
} catch {
  Remove-Item -LiteralPath $Staging -Recurse -Force -ErrorAction SilentlyContinue
  throw
}

Write-Host "Runtime-v3 tree ready: $Release" -ForegroundColor Green
