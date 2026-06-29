param([switch]$SkipFrontend)

$ErrorActionPreference = "Stop"

# Build the distributable runtime tree (HWAgent_release) from the source tree.
# User installs and OTA updates consume this runtime tree. It must not contain
# development-only folders such as frontend source, tests, docs, or node_modules.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $Root
$Release = Join-Path $RepoRoot "HWAgent_release"
$Version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw -Encoding UTF8).Trim()

Write-Host "Building release tree -> $Release" -ForegroundColor Cyan

# 1. Compile the launcher exe into the source root.
& (Join-Path $Root "launcher\build.ps1")
$Exe = Join-Path $Root "Insta360_HW.exe"
if (-not (Test-Path -LiteralPath $Exe)) { throw "Insta360_HW.exe was not built" }

# 2. Build the frontend into app/frontend on the developer machine only.
if (-not $SkipFrontend) {
  & (Join-Path $Root "scripts\build_frontend.ps1")
}

# 3. Recreate runtime directories from source.
New-Item -ItemType Directory -Force -Path $Release | Out-Null

# Remove known runtime directories before mirroring so deleted files do not
# linger. Remove dev-only top-level dirs if a previous bad build copied them.
foreach ($dir in @("app", "cadence", "config", "plugins", "scripts", "tools", "frontend", "tests", "docs", "uploads", "outputs", "history")) {
  $dst = Join-Path $Release $dir
  if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Recurse -Force }
}
Get-ChildItem -LiteralPath $Release -Directory -Filter "BOM*" -ErrorAction SilentlyContinue |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }

foreach ($dir in @("app", "cadence", "config", "plugins", "scripts", "tools")) {
  $src = Join-Path $Root $dir
  $dst = Join-Path $Release $dir
  if (-not (Test-Path -LiteralPath $src)) { continue }
  robocopy $src $dst /E /XD "__pycache__" ".pytest_cache" "node_modules" ".vite" "src" "dist" "tests" "docs" /XF "*.pyc" | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $dir (exit $LASTEXITCODE)" }
}

foreach ($devScript in @("build_frontend.ps1", "build_installer.ps1", "build_release.ps1", "publish_release.ps1", "verify_all.ps1")) {
  $path = Join-Path $Release ("scripts\" + $devScript)
  if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
}

# 4. Copy top-level runtime launchers and metadata.
$keepFiles = @(
  "Insta360_HW.exe",
  "launch_tool_suite.ps1",
  "launch_tool_suite_hidden.vbs",
  "iac_jump.bat",
  "run_tool_suite.ps1",
  "install.ps1",
  "uninstall.ps1",
  "update.ps1",
  "oneclick_install.ps1",
  "oneclick_uninstall.ps1",
  "oneclick_update.ps1",
  "VERSION",
  ".gitignore"
)
foreach ($name in $keepFiles) {
  $src = Join-Path $Root $name
  if (Test-Path -LiteralPath $src) {
    Copy-Item -LiteralPath $src -Destination (Join-Path $Release $name) -Force
  }
}

# 5. Ensure runtime-owned data directories exist.
foreach ($d in @("runtime", "data", "data\uploads", "data\outputs", "data\history", "data\reports\runtime", "plugins\user\scripts")) {
  New-Item -ItemType Directory -Force -Path (Join-Path $Release $d) | Out-Null
}

# 6. Write a factual manifest for install/update/uninstall/self-check.
$manifest = [ordered]@{
  product = "Insta360_HW"
  version = $Version
  layout = "runtime"
  generated_at = (Get-Date).ToString("s")
  preserved_paths = @("data", "config/local.json", "plugins/user")
  runtime_paths = @("app/backend", "app/frontend", "cadence", "config", "plugins", "scripts", "tools", "runtime", "Insta360_HW.exe")
  excluded_dev_paths = @("frontend", "frontend/src", "frontend/node_modules", "tests", "docs", "BOM*", ".git")
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Release "install_manifest.json") -Encoding UTF8

Write-Host ""
Write-Host "Release tree ready: $Release" -ForegroundColor Green
Write-Host ("  Insta360_HW.exe present: " + (Test-Path -LiteralPath (Join-Path $Release "Insta360_HW.exe")))
Write-Host ("  app/frontend/index.html present: " + (Test-Path -LiteralPath (Join-Path $Release "app\frontend\index.html")))
Write-Host ("  install_manifest.json present: " + (Test-Path -LiteralPath (Join-Path $Release "install_manifest.json")))
