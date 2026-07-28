param(
  [Parameter(Mandatory=$true)][string]$InstallRoot,
  [string]$StateRoot = "",
  [ValidateSet("PreserveData", "PurgeData", "CadenceOnly")]
  [string]$Mode = "PreserveData",
  [switch]$NoStop
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
$UninstallLogPath = Join-Path $StateRoot "logs\uninstall_latest.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $UninstallLogPath) | Out-Null
Set-Content -LiteralPath $UninstallLogPath -Value "" -Encoding UTF8
$script:UninstallStage = "initializing"

function Write-UninstallLog {
  param([Parameter(Mandatory=$true)][string]$Message)
  $line = "[{0}] {1}" -f ([DateTime]::Now.ToString("s")), $Message
  try { Add-Content -LiteralPath $UninstallLogPath -Value $line -Encoding UTF8 } catch {}
}

function Set-UninstallStage {
  param(
    [Parameter(Mandatory=$true)][string]$Stage,
    [Parameter(Mandatory=$true)][int]$Percent
  )
  $script:UninstallStage = $Stage
  Write-UninstallLog ("stage=" + $Stage)
  Write-Host ("__HWAGENT_UNINSTALL_PROGRESS__ {0} {1}" -f $Percent, $Stage)
}

Assert-HwLifecycleRuntimeRoot -Path $InstallRoot -AllowMissing | Out-Null

function Remove-OwnedProtocolRegistrationAtPath {
  param([Parameter(Mandatory=$true)][string]$ProtocolPath)

  $protocolPath = $ProtocolPath
  if (-not (Test-Path -LiteralPath $protocolPath)) { return }
  $protocolKey = Get-Item -LiteralPath $protocolPath -ErrorAction SilentlyContinue
  if ($null -eq $protocolKey) { return }
  $owner = [string]$protocolKey.GetValue("Owner", "")
  $label = [string]$protocolKey.GetValue("", "")
  $commandPath = Join-Path $protocolPath "shell\open\command"
  $command = ""
  if (Test-Path -LiteralPath $commandPath) {
    $command = [string](Get-Item -LiteralPath $commandPath).GetValue("")
  }
  $expectedExe = Join-Path $InstallRoot "Insta360_HW.exe"
  $commandMatchesInstall = $command.IndexOf($expectedExe, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
  $legacyOwned = $label -eq "URL:Insta360_HW reconnect protocol" -and $commandMatchesInstall
  if (($owner -eq "Insta360_HW" -and $commandMatchesInstall) -or $legacyOwned) {
    Remove-Item -LiteralPath $protocolPath -Recurse -Force
  }
}

function Remove-OwnedProtocolRegistration {
  # 0.3.0 and later use the machine-wide key. The user key is checked only to
  # remove installations created by earlier releases.
  foreach ($protocolPath in @(
    "HKLM:\Software\Classes\insta360-hw",
    "HKCU:\Software\Classes\insta360-hw"
  )) {
    Remove-OwnedProtocolRegistrationAtPath -ProtocolPath $protocolPath
  }
}

function Remove-RecoveryRegistrations {
  $runOnce = "HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce"
  if (-not (Test-Path -LiteralPath $runOnce)) { return }
  $properties = (Get-ItemProperty -LiteralPath $runOnce).PSObject.Properties
  foreach ($property in $properties) {
    if ($property.Name -like "Insta360_HW_Recovery_*") {
      Remove-ItemProperty -LiteralPath $runOnce -Name $property.Name -ErrorAction SilentlyContinue
    }
  }
}

$lifecycleMutex = $null
$uninstallFailed = $false
Write-UninstallLog ("uninstall started root=" + $InstallRoot + " state=" + $StateRoot + " mode=" + $Mode)
try {
  Set-UninstallStage -Stage "acquiring_lifecycle" -Percent 5
  $lifecycleMutex = Enter-HwLifecycleMutex -TimeoutMilliseconds 0
  Assert-HwLifecycleQuiescent -StateRoot $StateRoot
  Remove-HwLifecycleTerminalRuntimeTrees -RuntimeRoot $InstallRoot -StateRoot $StateRoot
  Set-UninstallStage -Stage "stopping_service" -Percent 10
  if (-not $NoStop) { Stop-HwLifecycleService -RuntimeRoot $InstallRoot -StateRoot $StateRoot -AllowLegacyIdentity }

  Set-UninstallStage -Stage "removing_cadence_integration" -Percent 30
  $removeCadence = Join-Path $InstallRoot "scripts\remove_cadence_loader.ps1"
  if (Test-Path -LiteralPath $removeCadence -PathType Leaf) {
    & $removeCadence -InstallDir $InstallRoot
  }
  if ($Mode -eq "CadenceOnly") {
    Set-UninstallStage -Stage "completed" -Percent 100
    Write-Host "__HWAGENT_UNINSTALL_DONE__"
  } else {
    Set-UninstallStage -Stage "detaching_runtime_state" -Percent 50
    if (Test-Path -LiteralPath $InstallRoot -PathType Container) {
      Initialize-HwLifecycleState -RuntimeRoot $InstallRoot -StateRoot $StateRoot | Out-Null
      Remove-HwLifecycleRuntimeJunctions -RuntimeRoot $InstallRoot -StateRoot $StateRoot
    }
    Remove-OwnedProtocolRegistration
    Remove-RecoveryRegistrations

    Set-UninstallStage -Stage "cleaning_lifecycle_state" -Percent 70
    foreach ($relative in @("runtime\service.json", "runtime\install.json")) {
      Remove-Item -LiteralPath (Join-Path $StateRoot $relative) -Force -ErrorAction SilentlyContinue
    }
    foreach ($relative in @("lifecycle\cache", "lifecycle\transactions", "lifecycle\jobs")) {
      $path = Join-Path $StateRoot $relative
      if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
    }

    if ($Mode -eq "PurgeData" -and (Test-Path -LiteralPath $StateRoot)) {
      Set-UninstallStage -Stage "purging_user_data" -Percent 85
      $expected = if ($env:LOCALAPPDATA) {
        [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Insta360_HW")).TrimEnd("\")
      } else {
        ""
      }
      if ([string]::IsNullOrWhiteSpace($expected) -or $StateRoot -ine $expected) {
        throw "Refusing to purge an unexpected state root: $StateRoot"
      }
      Set-Location -LiteralPath ([System.IO.Path]::GetTempPath())
      Remove-Item -LiteralPath $StateRoot -Recurse -Force
    }

    Set-UninstallStage -Stage "completed" -Percent 100
    Write-Host "__HWAGENT_UNINSTALL_DONE__"
  }
} catch {
  $uninstallFailure = $_
  $uninstallFailed = $true
  $details = $uninstallFailure.Exception.ToString()
  if (-not [string]::IsNullOrWhiteSpace([string]$uninstallFailure.ScriptStackTrace)) {
    $details += [Environment]::NewLine + $uninstallFailure.ScriptStackTrace
  }
  Write-UninstallLog ("FAILED stage=" + $script:UninstallStage + [Environment]::NewLine + $details)
  [Console]::Error.WriteLine("Uninstall failed at stage {0}: {1}", $script:UninstallStage, $uninstallFailure.Exception.Message)
} finally {
  if ($null -ne $lifecycleMutex) { Exit-HwLifecycleMutex -Mutex $lifecycleMutex }
}

if ($uninstallFailed) { exit 1 }
exit 0
