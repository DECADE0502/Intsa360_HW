param(
  [Parameter(Mandatory=$true)][string]$InstallRoot,
  [Parameter(Mandatory=$true)][string]$StateRoot,
  [ValidateSet("PreserveData", "PurgeData")]
  [string]$Mode = "PurgeData",
  [string]$ProgressPath = "",
  [switch]$NoStop,
  [switch]$SkipCadence,
  [switch]$SkipRecoveryRegistration
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Contract.ps1")
. (Join-Path $PSScriptRoot "Runtime.ps1")

$InstallRoot = Get-HwV3FullPath -Path $InstallRoot -Label "InstallRoot"
$StateRoot = Get-HwV3FullPath -Path $StateRoot -Label "StateRoot"
$env:INSTA360_HW_STATE_ROOT = $StateRoot
$logPath = Join-Path $StateRoot "logs\uninstall_latest.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $logPath) | Out-Null
Set-Content -LiteralPath $logPath -Value "" -Encoding UTF8
$script:stage = "initializing"

function Write-UninstallLog {
  param([Parameter(Mandatory=$true)][string]$Message)
  try { Add-Content -LiteralPath $logPath -Encoding UTF8 -Value ((Get-Date).ToString("s") + " " + $Message) }
  catch {}
}

function Set-UninstallProgress {
  param(
    [Parameter(Mandatory=$true)][string]$Stage,
    [Parameter(Mandatory=$true)][ValidateRange(0, 100)][int]$Percent,
    [Parameter(Mandatory=$true)][string]$Message
  )
  $script:stage = $Stage
  Write-UninstallLog ("stage=" + $Stage + " progress=" + $Percent + " message=" + $Message)
  Write-Host ("__HWAGENT_UNINSTALL_PROGRESS__ {0} {1}" -f $Percent, $Stage)
  if (-not [string]::IsNullOrWhiteSpace($ProgressPath)) {
    $progressTarget = [System.IO.Path]::GetFullPath($ProgressPath)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $progressTarget) | Out-Null
    Write-HwV3JsonAtomic -Path $progressTarget -Value ([ordered]@{
      schema = 3
      stage = $Stage
      progress = $Percent
      message = $Message
      updated_at = (Get-Date).ToUniversalTime().ToString("o")
    })
  }
}

function Remove-OwnedProtocolRegistrationAtPath {
  param([Parameter(Mandatory=$true)][string]$ProtocolPath)
  if (-not (Test-Path -LiteralPath $ProtocolPath)) { return }
  $key = Get-Item -LiteralPath $ProtocolPath -ErrorAction SilentlyContinue
  if ($null -eq $key) { return }
  $owner = [string]$key.GetValue("Owner", "")
  $label = [string]$key.GetValue("", "")
  $commandKey = Join-Path $ProtocolPath "shell\open\command"
  $command = if (Test-Path -LiteralPath $commandKey) { [string](Get-Item -LiteralPath $commandKey).GetValue("") } else { "" }
  $expectedLauncher = Join-Path $InstallRoot "Insta360_HW.exe"
  $legacyOwned = $label -eq "URL:Insta360_HW reconnect protocol" -and
    $command.IndexOf($expectedLauncher, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
  if ($owner -eq "Insta360_HW" -or $legacyOwned) {
    Remove-Item -LiteralPath $ProtocolPath -Recurse -Force
  }
}

function Remove-OwnedProtocolRegistration {
  foreach ($path in @("HKLM:\Software\Classes\insta360-hw", "HKCU:\Software\Classes\insta360-hw")) {
    Remove-OwnedProtocolRegistrationAtPath -ProtocolPath $path
  }
}

function Remove-HwV3RecoveryRegistrations {
  if ($SkipRecoveryRegistration) { return }
  $ownedTasks = @(Get-ScheduledTask -TaskName "Insta360_HW_Recovery_*" -ErrorAction SilentlyContinue | Where-Object {
    [string]$_.TaskPath -eq "\" -and [string]$_.TaskName -cmatch '^Insta360_HW_Recovery_[0-9a-f]{32}$'
  })
  foreach ($task in $ownedTasks) {
    Unregister-ScheduledTask -TaskName ([string]$task.TaskName) -TaskPath ([string]$task.TaskPath) -Confirm:$false
  }
  $runOnce = "HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce"
  if (Test-Path -LiteralPath $runOnce) {
    foreach ($property in (Get-ItemProperty -LiteralPath $runOnce).PSObject.Properties) {
      if ($property.Name -cmatch '^Insta360_HW_Recovery_[0-9a-f]{32}$') {
        Remove-ItemProperty -LiteralPath $runOnce -Name $property.Name -ErrorAction SilentlyContinue
      }
    }
  }
}

function Resolve-UninstallRuntime {
  $installationPath = Join-Path $InstallRoot "installation.json"
  if (Test-Path -LiteralPath $installationPath -PathType Leaf) {
    try {
      $metadata = Read-HwV3Installation -InstallRoot $InstallRoot
      $runtime = Resolve-HwV3RuntimePointer -InstallRoot $InstallRoot -RelativePath ([string]$metadata.active_runtime) `
        -Field "active_runtime"
      if (Test-Path -LiteralPath $runtime -PathType Container) { return $runtime }
      Write-UninstallLog "active runtime is missing; continuing with stable maintenance cleanup"
    } catch {
      Write-UninstallLog ("installation metadata is damaged; continuing with stable maintenance cleanup: " + $_.Exception.Message)
    }
  }
  $legacyManifest = Join-Path $InstallRoot "install_manifest.json"
  if (Test-Path -LiteralPath $legacyManifest -PathType Leaf) {
    try {
      $manifest = Get-Content -LiteralPath $legacyManifest -Raw -Encoding UTF8 | ConvertFrom-Json
      if ([int]$manifest.schema -eq 2 -and [string]$manifest.product -eq "Insta360_HW" -and
          [string]$manifest.layout -eq "runtime-v2") { return $InstallRoot }
    } catch {}
  }
  return ""
}

function Remove-PreservedLifecycleState {
  foreach ($relative in @(
    "runtime\service.json",
    "runtime\install.json",
    "cadence_integration.json",
    "cadence_ownership.json"
  )) {
    Remove-Item -LiteralPath (Join-Path $StateRoot $relative) -Force -ErrorAction SilentlyContinue
  }
  foreach ($relative in @("lifecycle\v3", "lifecycle\setup", "lifecycle\transactions", "lifecycle\jobs", "lifecycle\cache")) {
    $path = Join-Path $StateRoot $relative
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
  }
}

function Remove-ExactStateRoot {
  if (-not (Test-Path -LiteralPath $StateRoot)) { return }
  $expected = if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    ""
  } else {
    [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Insta360_HW")).TrimEnd("\")
  }
  if ([string]::IsNullOrWhiteSpace($expected) -or $StateRoot -ine $expected) {
    throw "Refusing to purge an unexpected state root: $StateRoot"
  }
  Set-Location -LiteralPath ([System.IO.Path]::GetTempPath())
  Remove-Item -LiteralPath $StateRoot -Recurse -Force
}

$pendingV3Setup = Join-Path $StateRoot "lifecycle\v3\setup"
if ((Test-Path -LiteralPath $pendingV3Setup -PathType Container) -and
    @(Get-ChildItem -LiteralPath $pendingV3Setup -Directory -Force -ErrorAction SilentlyContinue).Count -gt 0) {
  Set-UninstallProgress -Stage "recovering_interrupted_setup" -Percent 1 `
    -Message "Recovering an interrupted setup transaction before uninstall continues."
  & (Join-Path $PSScriptRoot "SetupRecover.ps1") -InstallRoot $InstallRoot -StateRoot $StateRoot `
    -NoRestart -SkipCadence:$SkipCadence
}

$legacySetupTransaction = Join-Path $StateRoot "lifecycle\setup\active"
if (Test-Path -LiteralPath $legacySetupTransaction -PathType Container) {
  Set-UninstallProgress -Stage "recovering_legacy_setup" -Percent 1 `
    -Message "Recovering an interrupted legacy setup before uninstall continues."
  Restore-HwV2InterruptedSetup -InstallRoot $InstallRoot -StateRoot $StateRoot `
    -SkipRecoveryRegistration:$SkipRecoveryRegistration | Out-Null
}

$legacyUpdateTransactions = Join-Path $StateRoot "lifecycle\transactions"
if ((Test-Path -LiteralPath $legacyUpdateTransactions -PathType Container) -and
    @(Get-ChildItem -LiteralPath $legacyUpdateTransactions -Directory -Force -ErrorAction SilentlyContinue).Count -gt 0) {
  Set-UninstallProgress -Stage "recovering_legacy_update" -Percent 2 `
    -Message "Recovering an interrupted legacy update before uninstall continues."
  Restore-HwV2InterruptedUpdates -InstallRoot $InstallRoot -StateRoot $StateRoot `
    -WorkerPath (Join-Path $InstallRoot "maintenance\legacy_lifecycle\Worker.ps1") -NoRestart `
    -SkipCadence:$SkipCadence -SkipRecoveryRegistration:$SkipRecoveryRegistration | Out-Null
}

if (Test-Path -LiteralPath (Join-Path $InstallRoot ".recovery") -PathType Container) {
  Set-UninstallProgress -Stage "recovering_interrupted_operation" -Percent 2 `
    -Message "Recovering an interrupted runtime switch before uninstall continues."
  $recoverArguments = @{
    InstallRoot = $InstallRoot
    StateRoot = $StateRoot
    NoRestart = $true
    SkipCadence = [bool]$SkipCadence
  }
  & (Join-Path $PSScriptRoot "Recover.ps1") @recoverArguments
}

$mutex = $null
$failed = $false
try {
  Set-UninstallProgress -Stage "acquiring_lifecycle" -Percent 5 -Message "Waiting for other lifecycle operations."
  $mutex = Enter-HwV3LifecycleMutex -TimeoutMilliseconds 30000
  $runtimeRoot = Resolve-UninstallRuntime

  Set-UninstallProgress -Stage "stopping_service" -Percent 18 -Message "Stopping the exact platform backend instance."
  if (-not $NoStop -and -not [string]::IsNullOrWhiteSpace($runtimeRoot)) {
    Stop-HwV3Service -RuntimeRoot $runtimeRoot -StateRoot $StateRoot
  }

  Set-UninstallProgress -Stage "removing_cadence" -Percent 38 -Message "Removing owned Cadence integration files."
  if (-not $SkipCadence -and -not [string]::IsNullOrWhiteSpace($runtimeRoot)) {
    $removeCadence = Join-Path $runtimeRoot "scripts\remove_cadence_loader.ps1"
  } else {
    $removeCadence = ""
  }
  if (-not $SkipCadence) {
    if ([string]::IsNullOrWhiteSpace($removeCadence) -or -not (Test-Path -LiteralPath $removeCadence -PathType Leaf)) {
      $removeCadence = Join-Path $InstallRoot "maintenance\scripts\remove_cadence_loader.ps1"
    }
    if (-not (Test-Path -LiteralPath $removeCadence -PathType Leaf)) {
      throw "Cadence cleanup component is missing from both the active runtime and stable maintenance files."
    }
    $cadenceToolRoot = if ([string]::IsNullOrWhiteSpace($runtimeRoot)) { $InstallRoot } else { $runtimeRoot }
    & $removeCadence -InstallDir $cadenceToolRoot
  }

  Set-UninstallProgress -Stage "removing_recovery" -Percent 58 -Message "Removing owned recovery registrations."
  Remove-HwV3RecoveryRegistrations
  Remove-OwnedProtocolRegistration

  Set-UninstallProgress -Stage "cleaning_state" -Percent 76 -Message "Cleaning platform lifecycle state."
  if ($Mode -eq "PreserveData") {
    Remove-PreservedLifecycleState
  } else {
    Set-UninstallProgress -Stage "purging_user_data" -Percent 86 -Message "Removing platform data requested by the user."
    Remove-ExactStateRoot
  }

  Set-UninstallProgress -Stage "completed" -Percent 100 -Message "Uninstall preparation completed."
  Write-Host "__HWAGENT_UNINSTALL_DONE__"
} catch {
  $failure = $_
  $failed = $true
  Write-UninstallLog ("FAILED stage=" + $script:stage + " " + $failure.Exception.ToString())
  [Console]::Error.WriteLine("Uninstall failed at stage {0}: {1}", $script:stage, $failure.Exception.Message)
} finally {
  if ($null -ne $mutex) { Exit-HwV3LifecycleMutex -Mutex $mutex }
}

if ($failed) { exit 1 }
exit 0
