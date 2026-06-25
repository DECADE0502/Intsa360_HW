param([switch]$SkipFrontend)

$ErrorActionPreference = "Stop"

# Build the distributable runtime tree (HWAgent_release) from the source tree.
# The release tree is what HWAgent_Setup.iss packages: it mirrors the install
# layout — built app/, cadence/, config/, plugins/, scripts/, tools/, the
# launchers and Insta360_HW.exe — but drops dev-only cruft (frontend source,
# node_modules, tests, docs, .git).

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $Root
$Release = Join-Path $RepoRoot "HWAgent_release"

Write-Host "Building release tree -> $Release" -ForegroundColor Cyan

# 1. Compile the launcher exe into the source root (it is both the dev entry
#    point and ships in the release tree).
& (Join-Path $Root "launcher\build.ps1")
$Exe = Join-Path $Root "Insta360_HW.exe"
if (-not (Test-Path -LiteralPath $Exe)) { throw "Insta360_HW.exe was not built" }

# 2. Build the frontend into app/frontend (skipped only when caller already did it).
if (-not $SkipFrontend) {
  & (Join-Path $Root "scripts\build_frontend.ps1")
}

# 3. Recreate the release tree from source, mirroring the runtime layout.
if (Test-Path -LiteralPath $Release) {
  # Preserve data/ and config/local.json in an existing release so we never
  # wipe a real install when the release dir happens to be a live install.
} else {
  New-Item -ItemType Directory -Force -Path $Release | Out-Null
}

# Mirror top-level runtime directories that ship verbatim from source.
foreach ($dir in @("app", "cadence", "config", "plugins", "scripts", "tools")) {
  $src = Join-Path $Root $dir
  $dst = Join-Path $Release $dir
  if (-not (Test-Path -LiteralPath $src)) { continue }
  if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Recurse -Force }
  robocopy $src $dst /E /XD "__pycache__" ".pytest_cache" "node_modules" ".vite" /XF "*.pyc" | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $dir (exit $LASTEXITCODE)" }
}

# 4. Copy top-level launchers and the exe. Drop the dev-only .bat entry points
#    that the single-exe model replaces, keep iac_jump.bat (Cadence menu jump).
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

# 5. Ensure runtime data directories exist (empty) so first run has somewhere
#    to write; the .gitignore already excludes their contents.
foreach ($d in @("data", "uploads", "outputs", "history", "plugins\user\scripts")) {
  $p = Join-Path $Release $d
  New-Item -ItemType Directory -Force -Path $p | Out-Null
}

Write-Host ""
Write-Host "Release tree ready: $Release" -ForegroundColor Green
Write-Host ("  Insta360_HW.exe present: " + (Test-Path -LiteralPath (Join-Path $Release "Insta360_HW.exe")))
Write-Host ("  app/frontend/index.html present: " + (Test-Path -LiteralPath (Join-Path $Release "app\frontend\index.html")))
