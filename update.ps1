param(
  [string]$Repo = "https://github.com/DECADE0502/Intsa360_HW.git",
  [string]$Branch = "main",
  [ValidateSet("zip", "git")]
  [string]$Method = "zip",
  [switch]$BuildFrontend
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

. (Join-Path $Root "scripts\lib\Paths.ps1")
. (Join-Path $Root "scripts\lib\Update.ps1")
. (Join-Path $Root "scripts\lib\Cadence.ps1")
. (Join-Path $Root "scripts\lib\TclScripts.ps1")

$Root = Get-HwAgentRoot -StartPath $Root
Write-Host "__HWAGENT_PROGRESS__ 0 starting update"
Write-Host "Starting Insta360_HW update..."
Write-Host "User data will be preserved: data, uploads, outputs, history, config/local.json, plugins/user"

# Default to zip-based update so end users need nothing installed (no git).
# Falls back to git only when -Method git is passed explicitly.
$UpdateMethod = if ($Method) { $Method } else { "zip" }

try {
  Invoke-HwAgentUpdate -Root $Root -Repo $Repo -Branch $Branch -Method $UpdateMethod | Out-Null

  if ($BuildFrontend -and (Test-Path -LiteralPath (Join-Path $Root "frontend\package.json"))) {
    Write-Host "__HWAGENT_PROGRESS__ 96 building frontend"
    & (Join-Path $Root "scripts\build_frontend.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
  } else {
    Write-Host "Using shipped app/frontend assets; skipping local frontend build."
  }

  $Python = Find-Python -Root $Root
  foreach ($vendorAutoLoadDir in Find-CadenceVendorAutoLoadDirs) {
    Disable-HwAgentVendorAutoLoadScripts -VendorAutoLoadDir $vendorAutoLoadDir | Out-Null
  }
  $AutoLoadDirs = Find-CadenceLoaderInstallDirs
  foreach ($autoLoadDir in $AutoLoadDirs) {
    Move-HwAgentAutoLoadBackupDirs -AutoLoadDir $autoLoadDir | Out-Null
  }
  Install-CadenceLoader -ToolRoot $Root -PythonPath $Python -AutoLoadDirs $AutoLoadDirs | Out-Null

  $verify = Join-Path $Root "scripts\verify_all.ps1"
  # verify_all needs tests/ and frontend/ source, which only exist in the dev
  # repo. Installed runtime copies lack them, so updates there must not fail
  # merely because the development verification tree is absent.
  if ((Test-Path -LiteralPath $verify) -and (Test-Path -LiteralPath (Join-Path $Root "tests"))) {
    Write-Host "__HWAGENT_PROGRESS__ 98 verifying update"
    Write-Host "Starting verification..."
    & $verify
    if ($LASTEXITCODE -ne 0) { throw "Verification failed." }
  } else {
    Write-Host "Verification script or test tree not found; skipping verification."
  }

  Write-Host "Update flow complete."
  Write-Host "__HWAGENT_PROGRESS__ 100 update complete; restarting service"
  Write-Host "__HWAGENT_DONE__"
} catch {
  Write-Host ("__HWAGENT_FAILED__ " + $_.Exception.Message)
  throw
}
