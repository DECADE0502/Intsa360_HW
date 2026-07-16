param(
  [string]$Repository = "DECADE0502/Intsa360_HW",
  [string]$BundleDir = "",
  [string]$PrivateKeyPath = "",
  [string]$InnoCompiler = "",
  [switch]$InitializeSigningKey
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$Workspace = Split-Path -Parent $Root
$Version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw -Encoding UTF8).Trim()
$Revision = (& git -C $Root rev-parse HEAD).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $Revision -notmatch '^[a-f0-9]{40}$') { throw "A full git revision is required." }
$SourceDateEpoch = [long]((& git -C $Root show -s --format=%ct $Revision).Trim())
if ($SourceDateEpoch -le 0) { throw "Unable to resolve the release commit timestamp." }
if ([string]::IsNullOrWhiteSpace($BundleDir)) { $BundleDir = Join-Path $Workspace ("Insta360_HW_release_" + $Version) }
if ([string]::IsNullOrWhiteSpace($PrivateKeyPath)) {
  $PrivateKeyPath = Join-Path $env:LOCALAPPDATA "Insta360_HW\release-keys\update_private_key.pem"
}
$BundleDir = [System.IO.Path]::GetFullPath($BundleDir)
$PrivateKeyPath = [System.IO.Path]::GetFullPath($PrivateKeyPath)
$PublicKeyPath = Join-Path $Root "config\update_public_key.pem"
$ReleaseTool = Join-Path $Root "scripts\release\release_bundle.py"

function Assert-NoRuntimeCacheArtifacts {
  param([Parameter(Mandatory=$true)][string]$RuntimeRoot)
  $artifact = Get-ChildItem -LiteralPath $RuntimeRoot -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "__pycache__" -or $_.Extension -ieq ".pyc" } |
    Select-Object -First 1
  if ($null -ne $artifact) {
    throw "Runtime tree was mutated by the release pipeline: $($artifact.FullName)"
  }
}

if ($InitializeSigningKey) {
  if (Test-Path -LiteralPath $PublicKeyPath -PathType Leaf) {
    throw "-InitializeSigningKey is bootstrap-only and the committed trust anchor already exists. Restore the matching private key from secure backup to $PrivateKeyPath, then run this script without -InitializeSigningKey."
  }
  & python $ReleaseTool initialize-key --private-key $PrivateKeyPath --public-key $PublicKeyPath
  if ($LASTEXITCODE -ne 0) { throw "Signing key initialization failed." }
  if ($env:OS -eq "Windows_NT") {
    & icacls $PrivateKeyPath /inheritance:r /grant:r ("$env:USERNAME`:(R,W)") | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to restrict the private signing key ACL." }
  }
  Write-Host "The public key was added to config/update_public_key.pem." -ForegroundColor Yellow
  Write-Host "Commit and review that trust anchor before building a release; back up the private key securely." -ForegroundColor Yellow
  exit 0
}

if (-not (Test-Path -LiteralPath $PrivateKeyPath -PathType Leaf)) {
  throw "Release signing key is missing. Restore the matching private key from secure backup to $PrivateKeyPath. Do not generate a replacement for the committed trust anchor."
}
if (-not (Test-Path -LiteralPath $PublicKeyPath -PathType Leaf)) {
  throw "Committed update trust anchor is missing: $PublicKeyPath. Key initialization is bootstrap-only and requires both key paths to be absent."
}
& python $ReleaseTool verify-key --private-key $PrivateKeyPath --public-key $PublicKeyPath
if ($LASTEXITCODE -ne 0) { throw "Release signing key does not match the committed trust anchor. Restore the correct key from secure backup." }
$dirty = @(& git -C $Root status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0) { throw "Unable to verify the git worktree." }
if ($dirty.Count -gt 0) { throw "Release builds require a clean git worktree." }
$tags = @(& git -C $Root tag --list ("v" + $Version))
if ($tags.Count -gt 0) { throw "Version $Version already has a release tag; bump VERSION first." }

Write-Host "[1/5] Running the complete source verification suite..." -ForegroundColor Cyan
& (Join-Path $Root "scripts\verify_all.ps1")
if ($LASTEXITCODE -ne 0) { throw "Source verification failed." }

$BuildRoot = Join-Path $Workspace ("HWAgent_build\" + $Version + "+" + $Revision)
$RuntimeRoot = Join-Path $BuildRoot "runtime"
$SetupRoot = Join-Path $BuildRoot "setup"
if (Test-Path -LiteralPath $BuildRoot) { Remove-Item -LiteralPath $BuildRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $BuildRoot, $SetupRoot | Out-Null

Write-Host "[2/5] Building the immutable runtime-v3 tree..." -ForegroundColor Cyan
$runtimeArgs = @{
  OutputDir = $RuntimeRoot
  Version = $Version
  Revision = $Revision
  BuildKind = "published"
  SourceDateEpoch = $SourceDateEpoch
}
& (Join-Path $Root "scripts\build_release.ps1") @runtimeArgs
if ($LASTEXITCODE -ne 0) { throw "Runtime build failed." }
Assert-NoRuntimeCacheArtifacts -RuntimeRoot $RuntimeRoot

Write-Host "[3/5] Compiling Setup from the exact runtime tree..." -ForegroundColor Cyan
& (Join-Path $Root "scripts\build_installer.ps1") -ReleaseDir $RuntimeRoot -OutputDir $SetupRoot `
  -Version $Version -InnoCompiler $InnoCompiler
if ($LASTEXITCODE -ne 0) { throw "Setup build failed." }

$PublishedAt = [DateTimeOffset]::FromUnixTimeSeconds($SourceDateEpoch).UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ssZ")
$EmbeddedPython = Join-Path $RuntimeRoot "runtime\python\python.exe"
$AssetBaseUrl = "https://raw.githubusercontent.com/$Repository/ota/versions/$Version"
Write-Host "[4/5] Creating root-layout ZIP, signed manifest, legacy bridge and checksums..." -ForegroundColor Cyan
& $EmbeddedPython -B $ReleaseTool build `
  --runtime-root $RuntimeRoot `
  --setup (Join-Path $SetupRoot "Insta360_HW_Setup.exe") `
  --output-dir $BundleDir `
  --private-key $PrivateKeyPath `
  --public-key $PublicKeyPath `
  --version $Version `
  --revision $Revision `
  --repository $Repository `
  --asset-base-url $AssetBaseUrl `
  --notice (Join-Path $Root "UPDATE_NOTICE.json") `
  --published-at $PublishedAt `
  --source-date-epoch $SourceDateEpoch `
  --min-updater-version "0.4.0"
if ($LASTEXITCODE -ne 0) { throw "Signed release bundle creation failed." }
$ExpectedArtifacts = @(
  "Insta360_HW_Runtime_$Version.zip",
  "Insta360_HW_runtime_v$Version.zip",
  "Insta360_HW_Setup.exe",
  "update-manifest-v3.json",
  "update-manifest.json",
  "SHA256SUMS.txt"
)
foreach ($name in $ExpectedArtifacts) {
  if (-not (Test-Path -LiteralPath (Join-Path $BundleDir $name) -PathType Leaf)) {
    throw "Signed release bundle is incomplete; missing $name."
  }
}

Write-Host "[5/5] Re-verifying the exact publishable bytes..." -ForegroundColor Cyan
& $EmbeddedPython -B $ReleaseTool verify --bundle-dir $BundleDir --public-key $PublicKeyPath `
  --version $Version --revision $Revision
if ($LASTEXITCODE -ne 0) { throw "Final release bundle verification failed." }
Assert-NoRuntimeCacheArtifacts -RuntimeRoot $RuntimeRoot

$CanonicalSetup = Join-Path $Workspace "Insta360_HW_Setup.exe"
$IncomingSetup = $CanonicalSetup + ".incoming"
Copy-Item -LiteralPath (Join-Path $BundleDir "Insta360_HW_Setup.exe") -Destination $IncomingSetup -Force
Move-Item -LiteralPath $IncomingSetup -Destination $CanonicalSetup -Force

Write-Host ""
Write-Host "LOCAL RELEASE BUILD COMPLETE" -ForegroundColor Green
Write-Host "  Bundle: $BundleDir"
Write-Host "  Setup:  $CanonicalSetup"
Write-Host "  Version: $Version"
Write-Host "  Revision: $Revision"
Write-Host "Nothing was installed, updated, uninstalled, or uploaded."
