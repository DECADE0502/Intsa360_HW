param(
  [Parameter(Mandatory=$true)][string]$InstallRoot,
  [string]$StateRoot = "",
  [switch]$NoStart,
  [switch]$SkipCadence,
  [switch]$PrepareUpgrade
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Contract.ps1")
. (Join-Path $ScriptDir "Runtime.ps1")

$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot).TrimEnd("\")
if ([string]::IsNullOrWhiteSpace($StateRoot)) {
  if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    $StateRoot = Join-Path $env:LOCALAPPDATA "Insta360_HW"
  } else {
    $StateRoot = Get-HwLifecycleStateRoot -RuntimeRoot $InstallRoot
  }
}
$StateRoot = [System.IO.Path]::GetFullPath($StateRoot).TrimEnd("\")
$env:INSTA360_HW_STATE_ROOT = $StateRoot
$InstallLogPath = Join-Path $StateRoot "logs\install_latest.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $InstallLogPath) | Out-Null
Set-Content -LiteralPath $InstallLogPath -Value "" -Encoding UTF8
$script:InstallStage = "initializing"

function Write-InstallLog {
  param([Parameter(Mandatory=$true)][string]$Message)
  $line = "[{0}] {1}" -f ([DateTime]::Now.ToString("s")), $Message
  try { Add-Content -LiteralPath $InstallLogPath -Value $line -Encoding UTF8 } catch {}
}

function Set-InstallStage {
  param(
    [Parameter(Mandatory=$true)][string]$Stage,
    [Parameter(Mandatory=$true)][int]$Percent
  )
  $script:InstallStage = $Stage
  Write-InstallLog ("stage=" + $Stage)
  Write-Host ("__HWAGENT_INSTALL_PROGRESS__ {0} {1}" -f $Percent, $Stage)
}

function Assert-InstallPayload {
  Assert-HwLifecycleRuntimeRoot -Path $InstallRoot | Out-Null
  $required = @(
    "app\frontend\index.html",
    "runtime\python\python.exe",
    "scripts\lifecycle\Worker.ps1",
    "scripts\lifecycle\Recover.ps1",
    "scripts\lib\Paths.ps1",
    "scripts\lib\CadenceDiscovery.ps1",
    "REVISION"
  )
  foreach ($relative in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot $relative) -PathType Leaf)) {
      throw "Installation payload is incomplete; missing $relative"
    }
  }
  try {
    $manifest = Get-Content -LiteralPath (Join-Path $InstallRoot "install_manifest.json") -Raw -Encoding UTF8 | ConvertFrom-Json
  } catch {
    throw "Installation payload has an invalid install_manifest.json."
  }
  $version = (Get-Content -LiteralPath (Join-Path $InstallRoot "VERSION") -Raw -Encoding UTF8).Trim()
  $revision = (Get-Content -LiteralPath (Join-Path $InstallRoot "REVISION") -Raw -Encoding UTF8).Trim()
  if ([int]$manifest.schema -ne 2) { throw "Installation manifest schema must be 2." }
  if ([string]$manifest.product -ne "Insta360_HW") { throw "Installation manifest product is invalid." }
  if ([string]$manifest.layout -ne "runtime-v2") { throw "Installation manifest layout must be runtime-v2." }
  if ([string]$manifest.version -ne $version) { throw "Installation manifest version does not match VERSION." }
  if ([string]$manifest.revision -ne $revision) { throw "Installation manifest revision does not match REVISION." }
  return [pscustomobject]@{ version = $version; revision = $revision }
}

function Invoke-CadenceDeploymentAttempt {
  param(
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][AllowEmptyCollection()][string[]]$AutoLoadDirs
  )
  $snapshot = Start-HwAgentCadenceDeploymentTransaction -AutoLoadDirs $AutoLoadDirs
  try {
    foreach ($autoLoadDir in $AutoLoadDirs) {
      Move-HwAgentAutoLoadBackupDirs -AutoLoadDir $autoLoadDir | Out-Null
    }
    $installedLoaders = @(Install-CadenceLoader -ToolRoot $InstallRoot -PythonPath $PythonPath -AutoLoadDirs $AutoLoadDirs)
    $installedDirs = @($installedLoaders | ForEach-Object { Split-Path -Parent $_ })
    Update-HwAgentCadenceOwnershipManifest -LoaderPaths $installedLoaders | Out-Null
    Set-HwAgentCadenceIntegrationState -Enabled:$true -LoaderPaths $installedDirs | Out-Null
  } catch {
    $deploymentFailure = $_
    try {
      Restore-HwAgentCadenceDeploymentTransaction -SnapshotRoot $snapshot
    } catch {
      throw ("Cadence deployment failed and rollback also failed: " + $_.Exception.Message)
    }
    throw $deploymentFailure
  } finally {
    try { Complete-HwAgentCadenceDeploymentTransaction -SnapshotRoot $snapshot } catch {}
  }
}

function Install-CadenceIntegration {
  . (Join-Path $InstallRoot "scripts\lib\Paths.ps1")
  . (Join-Path $InstallRoot "scripts\lib\Cadence.ps1")
  . (Join-Path $InstallRoot "scripts\lib\TclScripts.ps1")
  $python = Find-Python -Root $InstallRoot
  $autoLoadDirs = @(Get-HwAgentManagedCadenceAutoLoadDirs)

  foreach ($attempt in 1..2) {
    try {
      Invoke-CadenceDeploymentAttempt -PythonPath $python -AutoLoadDirs $autoLoadDirs
      Write-InstallLog ("cadence deployment completed on attempt " + $attempt)
      return
    } catch {
      Write-InstallLog ("cadence attempt " + $attempt + " failed: " + $_.Exception.ToString())
      if ($attempt -ge 2) { throw }
      Start-Sleep -Milliseconds 750
    }
  }
}

$lifecycleMutex = $null
$installFailed = $false
$serviceStartedByInstall = $false
Write-InstallLog ("install started root=" + $InstallRoot + " state=" + $StateRoot)
try {
  Set-InstallStage -Stage "acquiring_lifecycle" -Percent 5
  $lifecycleMutex = Enter-HwLifecycleMutex -TimeoutMilliseconds 0
  Assert-HwLifecycleQuiescent -StateRoot $StateRoot
  Remove-HwLifecycleTerminalRuntimeTrees -RuntimeRoot $InstallRoot -StateRoot $StateRoot
  if ($PrepareUpgrade) {
    Set-InstallStage -Stage "preparing_upgrade" -Percent 20
    Assert-HwLifecycleRuntimeRoot -Path $InstallRoot -AllowMissing | Out-Null
    if (Test-Path -LiteralPath $InstallRoot -PathType Container) {
      Stop-HwLifecycleService -RuntimeRoot $InstallRoot -StateRoot $StateRoot -AllowLegacyIdentity
      Initialize-HwLifecycleState -RuntimeRoot $InstallRoot -StateRoot $StateRoot | Out-Null
      Remove-HwLifecycleRuntimeJunctions -RuntimeRoot $InstallRoot -StateRoot $StateRoot
    }
    Write-InstallLog "upgrade preparation completed"
    return
  }

  Set-InstallStage -Stage "validating_runtime" -Percent 10
  $payload = Assert-InstallPayload

  Set-InstallStage -Stage "migrating_user_state" -Percent 30
  Initialize-HwLifecycleState -RuntimeRoot $InstallRoot -StateRoot $StateRoot | Out-Null

  Set-InstallStage -Stage "verifying_backend" -Percent 55
  if (-not $NoStart) {
    Start-HwLifecycleService -RuntimeRoot $InstallRoot -StateRoot $StateRoot
    $serviceStartedByInstall = $true
  }

  Set-InstallStage -Stage "deploying_cadence" -Percent 75
  if (-not $SkipCadence) { Install-CadenceIntegration }

  $identity = [ordered]@{
    schema = 2
    product = "Insta360_HW"
    install_root = $InstallRoot
    state_root = $StateRoot
    version = $payload.version
    revision = $payload.revision
    installed_at = (Get-Date).ToUniversalTime().ToString("o")
  }
  Set-InstallStage -Stage "committing_identity" -Percent 90
  Write-HwLifecycleJsonAtomic -Path (Join-Path $StateRoot "runtime\install.json") -Value $identity

  Set-InstallStage -Stage "completed" -Percent 100
  Write-Host "__HWAGENT_INSTALL_DONE__"
  Write-InstallLog "install completed"
} catch {
  $installFailure = $_
  $installFailed = $true
  if ($serviceStartedByInstall) {
    try {
      Stop-HwLifecycleService -RuntimeRoot $InstallRoot -StateRoot $StateRoot -AllowLegacyIdentity
      Write-InstallLog "stopped backend after installation failure"
    } catch {
      Write-InstallLog ("failed to stop backend after installation failure: " + $_.Exception.Message)
    }
  }
  $details = $installFailure.Exception.ToString()
  if (-not [string]::IsNullOrWhiteSpace([string]$installFailure.ScriptStackTrace)) {
    $details += [Environment]::NewLine + $installFailure.ScriptStackTrace
  }
  Write-InstallLog ("FAILED stage=" + $script:InstallStage + [Environment]::NewLine + $details)
  [Console]::Error.WriteLine("Install failed at stage {0}: {1}", $script:InstallStage, $installFailure.Exception.Message)
} finally {
  if ($null -ne $lifecycleMutex) { Exit-HwLifecycleMutex -Mutex $lifecycleMutex }
}

if ($installFailed) { exit 1 }
exit 0
