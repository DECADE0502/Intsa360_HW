param([switch]$SkipFrontend)

$ErrorActionPreference = "Stop"

# Build the distributable runtime tree (HWAgent_release) from the source tree.
# User installs and OTA updates consume this runtime tree. It must not contain
# development-only folders such as frontend source, tests, docs, or node_modules.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $Root
$Release = Join-Path $RepoRoot "HWAgent_release"
. (Join-Path $Root "scripts\lib\EmbeddedPython.ps1")
$Version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw -Encoding UTF8).Trim()
$Revision = ""
try {
  $Revision = (& git -C $Root rev-parse HEAD 2>$null).Trim()
} catch {
  $Revision = ""
}

Write-Host "Building release tree -> $Release" -ForegroundColor Cyan

# 1. Compile the launcher exe into the source root.
& (Join-Path $Root "launcher\build.ps1")
$Exe = Join-Path $Root "Insta360_HW.exe"
if (-not (Test-Path -LiteralPath $Exe)) { throw "Insta360_HW.exe was not built" }

# 2. Build the frontend into app/frontend on the developer machine only.
if (-not $SkipFrontend) {
  & (Join-Path $Root "scripts\build_frontend.ps1")
}

# 3. Recreate the immutable runtime tree from an empty directory. A complete
# rebuild prevents unknown files from an older layout entering the release ZIP.
if (Test-Path -LiteralPath $Release) {
  Remove-Item -LiteralPath $Release -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $Release | Out-Null

foreach ($dir in @("app", "cadence", "config", "plugins", "scripts", "tools")) {
  $src = Join-Path $Root $dir
  $dst = Join-Path $Release $dir
  if (-not (Test-Path -LiteralPath $src)) { continue }
  robocopy $src $dst /E /XD "__pycache__" ".pytest_cache" "node_modules" ".vite" "src" "dist" "tests" "docs" "archive" /XF "*.pyc" "local.json" | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $dir (exit $LASTEXITCODE)" }
}

foreach ($devScript in @("build_frontend.ps1", "build_installer.ps1", "build_release.ps1", "bump_version.ps1", "pre_release_check.ps1", "publish_release.ps1", "verify_all.ps1")) {
  $path = Join-Path $Release ("scripts\" + $devScript)
  if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
}
foreach ($devPath in @("scripts\lib\EmbeddedPython.ps1")) {
  $path = Join-Path $Release $devPath
  if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
}

# 4. Copy top-level runtime launchers and metadata.
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
  $src = Join-Path $Root $name
  if (Test-Path -LiteralPath $src) {
    Copy-Item -LiteralPath $src -Destination (Join-Path $Release $name) -Force
  }
}
if (-not [string]::IsNullOrWhiteSpace($Revision)) {
  Set-Content -LiteralPath (Join-Path $Release "REVISION") -Value $Revision -Encoding UTF8
}

# 5. Prepare the immutable embedded runtime. Mutable user state is created
# under %LOCALAPPDATA% by lifecycle V2 and is never packaged in the runtime.
foreach ($d in @("runtime")) {
  New-Item -ItemType Directory -Force -Path (Join-Path $Release $d) | Out-Null
}

$runtimePyDir = Join-Path $Release "runtime\python"
Write-Host "Preparing embedded Python runtime..." -ForegroundColor Cyan
Download-EmbeddedPython -OutDir $runtimePyDir
Install-OpenpyxlWheel -PythonDir $runtimePyDir
& (Join-Path $runtimePyDir "python.exe") -c "import openpyxl; print('openpyxl', openpyxl.__version__)"
if ($LASTEXITCODE -ne 0) { throw "Embedded Python openpyxl verification failed" }
Get-ChildItem -LiteralPath $Release -Directory -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue |
  Sort-Object { $_.FullName.Length } -Descending |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
Get-ChildItem -LiteralPath $Release -File -Filter "*.pyc" -Recurse -ErrorAction SilentlyContinue |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }

# 6. Write a factual manifest for install/update/uninstall/self-check.
$manifest = [ordered]@{
  product = "Insta360_HW"
  version = $Version
  revision = $Revision
  schema = 2
  layout = "runtime-v2"
  generated_at = (Get-Date).ToString("s")
  state_root = "%LOCALAPPDATA%\Insta360_HW"
  mutable_paths = @("data", "config/local.json", "plugins/user", "logs", "lifecycle")
  runtime_paths = @("app/backend", "app/frontend", "cadence", "config", "plugins", "scripts", "tools", "runtime", "Insta360_HW.exe")
  excluded_dev_paths = @("frontend", "frontend/src", "frontend/node_modules", "tests", "docs", "BOM*", ".git")
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Release "install_manifest.json") -Encoding UTF8

Write-Host ""
Write-Host "Release tree ready: $Release" -ForegroundColor Green
Write-Host ("  Insta360_HW.exe present: " + (Test-Path -LiteralPath (Join-Path $Release "Insta360_HW.exe")))
Write-Host ("  app/frontend/index.html present: " + (Test-Path -LiteralPath (Join-Path $Release "app\frontend\index.html")))
Write-Host ("  install_manifest.json present: " + (Test-Path -LiteralPath (Join-Path $Release "install_manifest.json")))
