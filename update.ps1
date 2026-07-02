param(
  [string]$Repo = "https://github.com/DECADE0502/Intsa360_HW.git",
  [string]$Branch = "main",
  [ValidateSet("zip", "git")]
  [string]$Method = "zip",
  [switch]$BuildFrontend,
  [switch]$AllowDowngrade
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

. (Join-Path $Root "scripts\lib\Paths.ps1")
. (Join-Path $Root "scripts\lib\Service.ps1")
. (Join-Path $Root "scripts\lib\Update.ps1")
. (Join-Path $Root "scripts\lib\Cadence.ps1")
. (Join-Path $Root "scripts\lib\TclScripts.ps1")

$Root = Get-HwAgentRoot -StartPath $Root
$UpdateMutex = New-Object System.Threading.Mutex($false, "Global\Insta360_HW_Update")
$HasUpdateMutex = $false
Write-Host "__HWAGENT_PROGRESS__ 0 starting update"
Write-Host "Starting Insta360_HW update..."
Write-Host "User data will be preserved: data, uploads, outputs, history, config/local.json, plugins/user"

# Default to zip-based update so end users need nothing installed (no git).
# Falls back to git only when -Method git is passed explicitly.
$UpdateMethod = if ($Method) { $Method } else { "zip" }

try {
  $HasUpdateMutex = $UpdateMutex.WaitOne(0)
  if (-not $HasUpdateMutex) {
    Write-Host "__HWAGENT_PROGRESS__ 100 another update is already running"
    Write-Host "another update is already running"
    Write-Host "__HWAGENT_DONE__"
    exit 0
  }

  Restore-HwAgentInterruptedUpdate -Root $Root | Out-Null
  Invoke-HwAgentUpdate -Root $Root -Repo $Repo -Branch $Branch -Method $UpdateMethod -AllowDowngrade:$AllowDowngrade | Out-Null

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

  # Release verification (verify_all.ps1) intentionally does NOT run here.
  # It belongs to scripts/pre_release_check.ps1 on the dev machine, before
  # tagging. Running it during OTA was a footgun: the rollback transaction is
  # already committed by this point, so a verification failure could not roll
  # anything back — it only left the tree updated but flagged FAILED, and the
  # service below never restarted. Installed runtimes also lack .git, which
  # made git-dependent consistency tests fail on every single update.

  Start-HwAgentService -Root $Root -PythonPath $Python | Out-Null

  Write-Host "Update flow complete."
  Write-Host "__HWAGENT_PROGRESS__ 100 update complete; restarting service"
  Write-Host "__HWAGENT_DONE__"
} catch {
  Write-Host ("__HWAGENT_FAILED__ " + $_.Exception.Message)
  throw
} finally {
  if ($HasUpdateMutex) {
    $UpdateMutex.ReleaseMutex() | Out-Null
  }
  $UpdateMutex.Dispose()
}
