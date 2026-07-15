param(
  [Parameter(Mandatory=$true)][string]$InstallRoot,
  [Parameter(Mandatory=$true)][string]$StateRoot,
  [switch]$NoRestart,
  [switch]$SkipCadence
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Contract.ps1")
. (Join-Path $PSScriptRoot "Runtime.ps1")

$InstallRoot = Get-HwV3FullPath -Path $InstallRoot -Label "InstallRoot"
$StateRoot = Get-HwV3FullPath -Path $StateRoot -Label "StateRoot"
$env:INSTA360_HW_STATE_ROOT = $StateRoot
$setupRoot = Join-Path $StateRoot "lifecycle\v3\setup"
if (-not (Test-Path -LiteralPath $setupRoot -PathType Container)) { exit 0 }

function Test-SameSetupPath {
  param([Parameter(Mandatory=$true)][string]$Left, [Parameter(Mandatory=$true)][string]$Right)
  try {
    return [System.IO.Path]::GetFullPath($Left).TrimEnd("\") -ieq
      [System.IO.Path]::GetFullPath($Right).TrimEnd("\")
  } catch { return $false }
}

function Remove-SetupDirectory {
  param([Parameter(Mandatory=$true)][string]$Path)
  if (-not (Test-HwV3PathWithin -Path $Path -Parent $setupRoot)) {
    throw "Setup recovery transaction escapes its owned root."
  }
  if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path -Recurse -Force }
}

function Remove-SetupRuntimeTree {
  param([Parameter(Mandatory=$true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return }
  $runtimeParent = Join-Path $InstallRoot "runtime"
  if (-not (Test-HwV3PathWithin -Path $Path -Parent $runtimeParent)) {
    throw "Setup recovery refused an unowned runtime path."
  }
  $item = Get-Item -LiteralPath $Path -Force
  if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "Setup recovery refused a reparse-point runtime."
  }
  Remove-Item -LiteralPath $Path -Recurse -Force
}

$mutex = $null
try {
  $mutex = Enter-HwV3LifecycleMutex -TimeoutMilliseconds 30000
  $transactions = @(Get-ChildItem -LiteralPath $setupRoot -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -cmatch '^[0-9a-f]{32}$' } | Sort-Object Name)
  foreach ($transaction in $transactions) {
    if (($transaction.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw "Setup recovery transaction must not be a reparse point."
    }
    $jobId = Assert-HwV3JobId -JobId $transaction.Name
    $journal = Read-HwV3Json -Path (Join-Path $transaction.FullName "journal.json") -Required
    if ([int]$journal.schema -ne 3 -or [string]$journal.product -ne "Insta360_HW" -or
        [string]$journal.kind -ne "setup" -or [string]$journal.job_id -cne $jobId -or
        -not (Test-SameSetupPath -Left ([string]$journal.install_root) -Right $InstallRoot) -or
        -not (Test-SameSetupPath -Left ([string]$journal.state_root) -Right $StateRoot)) {
      throw "Setup recovery transaction identity is invalid."
    }

    $newRelative = [string]$journal.new_relative
    $newRuntime = Resolve-HwV3RuntimePointer -InstallRoot $InstallRoot -RelativePath $newRelative -Field "setup new_relative"
    $oldRelative = [string]$journal.old_relative
    $oldRuntime = if ([string]::IsNullOrWhiteSpace($oldRelative)) {
      $InstallRoot
    } else {
      Resolve-HwV3RuntimePointer -InstallRoot $InstallRoot -RelativePath $oldRelative -Field "setup old_relative"
    }
    $incoming = [System.IO.Path]::GetFullPath([string]$journal.incoming).TrimEnd("\")
    $runtimeParent = Join-Path $InstallRoot "runtime"
    if (-not (Test-HwV3PathWithin -Path $incoming -Parent $runtimeParent)) {
      throw "Setup recovery incoming path is invalid."
    }
    $launcherPath = Join-Path $InstallRoot "Insta360_HW.exe"
    $launcherBackup = Join-Path $transaction.FullName "launcher-before.exe"
    if (-not (Test-SameSetupPath -Left ([string]$journal.launcher_backup) -Right $launcherBackup)) {
      throw "Setup recovery launcher backup path is invalid."
    }
    $sameRuntimeBackup = [string]$journal.same_runtime_backup
    if (-not [string]::IsNullOrWhiteSpace($sameRuntimeBackup)) {
      $expectedBackup = $newRuntime + "." + $jobId + ".backup"
      if (-not (Test-SameSetupPath -Left $sameRuntimeBackup -Right $expectedBackup)) {
        throw "Setup recovery same-runtime backup path is invalid."
      }
    }

    if ([string]$journal.outcome -ceq "completed") {
      if (-not [string]::IsNullOrWhiteSpace($sameRuntimeBackup)) {
        Remove-SetupRuntimeTree -Path $sameRuntimeBackup
      }
      Remove-SetupRuntimeTree -Path $incoming
      Remove-SetupDirectory -Path $transaction.FullName
      continue
    }
    if ([string]$journal.outcome -cne "pending") {
      throw "Setup recovery transaction outcome is invalid."
    }

    if (([bool]$journal.new_runtime_created -or [bool]$journal.same_runtime_moved -or
        [bool]$journal.pointer_committed) -and (Test-Path -LiteralPath $newRuntime -PathType Container)) {
      try { Stop-HwV3Service -RuntimeRoot $newRuntime -StateRoot $StateRoot }
      catch {}
    }
    $sameRuntimeBackupExists = -not [string]::IsNullOrWhiteSpace($sameRuntimeBackup) -and
      (Test-Path -LiteralPath $sameRuntimeBackup -PathType Container)
    $restoreSameRuntime = [bool]$journal.same_runtime_moved -or
      ([bool]$journal.same_runtime_move_intent -and $sameRuntimeBackupExists)
    if ($restoreSameRuntime) {
      if (-not $sameRuntimeBackupExists) {
        throw "Setup recovery cannot find the moved previous runtime."
      }
      Remove-SetupRuntimeTree -Path $newRuntime
      Move-Item -LiteralPath $sameRuntimeBackup -Destination $newRuntime
    } elseif ([bool]$journal.new_runtime_created -and $newRelative -cne $oldRelative) {
      Remove-SetupRuntimeTree -Path $newRuntime
    }
    Remove-SetupRuntimeTree -Path $incoming

    if ([bool]$journal.pointer_committed -or [bool]$journal.pointer_commit_intent) {
      $installationPath = Join-Path $InstallRoot "installation.json"
      if ($null -ne $journal.original_metadata) {
        Write-HwV3JsonAtomic -Path $installationPath -Value $journal.original_metadata
      } else {
        Remove-Item -LiteralPath $installationPath -Force -ErrorAction SilentlyContinue
      }
    }
    if ([bool]$journal.launcher_replaced) {
      if ([bool]$journal.launcher_existed) {
        if (-not (Test-Path -LiteralPath $launcherBackup -PathType Leaf)) {
          throw "Setup recovery launcher backup is missing."
        }
        Copy-Item -LiteralPath $launcherBackup -Destination $launcherPath -Force
      } else {
        Remove-Item -LiteralPath $launcherPath -Force -ErrorAction SilentlyContinue
      }
    }

    $cadenceSnapshot = [string]$journal.cadence_snapshot
    if (-not $SkipCadence -and -not [string]::IsNullOrWhiteSpace($cadenceSnapshot)) {
      if (-not (Test-HwV3PathWithin -Path $cadenceSnapshot -Parent $StateRoot) -or
          -not (Test-Path -LiteralPath $cadenceSnapshot -PathType Container)) {
        throw "Setup recovery Cadence snapshot is invalid."
      }
      . (Join-Path $oldRuntime "scripts\lib\Paths.ps1")
      . (Join-Path $oldRuntime "scripts\lib\Cadence.ps1")
      . (Join-Path $oldRuntime "scripts\lib\TclScripts.ps1")
      Restore-HwAgentCadenceDeploymentTransaction -SnapshotRoot $cadenceSnapshot
      Complete-HwAgentCadenceDeploymentTransaction -SnapshotRoot $cadenceSnapshot
    }
    if ([bool]$journal.old_service_was_healthy -and -not $NoRestart -and
        (Test-Path -LiteralPath $oldRuntime -PathType Container)) {
      Start-HwV3Service -RuntimeRoot $oldRuntime -StateRoot $StateRoot
    }
    Remove-SetupDirectory -Path $transaction.FullName
  }
  if ((Test-Path -LiteralPath $setupRoot -PathType Container) -and
      @(Get-ChildItem -LiteralPath $setupRoot -Force -ErrorAction SilentlyContinue).Count -eq 0) {
    Remove-Item -LiteralPath $setupRoot -Force
  }
} finally {
  if ($null -ne $mutex) { Exit-HwV3LifecycleMutex -Mutex $mutex }
}

exit 0
