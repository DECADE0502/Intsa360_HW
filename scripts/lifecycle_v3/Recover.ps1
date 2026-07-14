param(
  [Parameter(Mandatory=$true)][string]$InstallRoot,
  [Parameter(Mandatory=$true)][string]$StateRoot,
  [string]$JobId = "",
  [string]$RecoveryTaskName = "",
  [switch]$NoRestart,
  [switch]$SkipCadence
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Contract.ps1")
. (Join-Path $PSScriptRoot "Runtime.ps1")

$InstallRoot = Get-HwV3FullPath -Path $InstallRoot -Label "InstallRoot"
$StateRoot = Get-HwV3FullPath -Path $StateRoot -Label "StateRoot"
$env:INSTA360_HW_STATE_ROOT = $StateRoot
$expectedTaskName = if ([string]::IsNullOrWhiteSpace($JobId)) { "" } else { "Insta360_HW_Recovery_" + (Assert-HwV3JobId -JobId $JobId) }
if (-not [string]::IsNullOrWhiteSpace($RecoveryTaskName) -and $RecoveryTaskName -cne $expectedTaskName) {
  throw "Recovery task identity is invalid."
}

function Test-SameHwV3Path {
  param([Parameter(Mandatory=$true)][string]$Left, [Parameter(Mandatory=$true)][string]$Right)
  try {
    return [System.IO.Path]::GetFullPath($Left).TrimEnd("\") -ieq [System.IO.Path]::GetFullPath($Right).TrimEnd("\")
  } catch { return $false }
}

function Clear-HwV3RecoveryTask {
  if ([string]::IsNullOrWhiteSpace($RecoveryTaskName)) { return $true }
  $scheduler = Get-HwV3TaskSchedulerPath
  & $scheduler /Delete /TN $RecoveryTaskName /F 2>$null | Out-Null
  $deleteExit = $LASTEXITCODE
  if ($deleteExit -eq 0) { return $true }
  & $scheduler /Query /TN $RecoveryTaskName 2>$null | Out-Null
  $queryExit = $LASTEXITCODE
  if ($queryExit -ne 0) { return $true }
  throw "Failed to remove the protected lifecycle recovery task."
}

$transactions = Join-Path $StateRoot "lifecycle\v3\transactions"
$protectedRecoveryParent = Join-Path $InstallRoot ".recovery"

function Assert-ProtectedRecoveryDirectory {
  param([Parameter(Mandatory=$true)][string]$RecoveryRoot, [Parameter(Mandatory=$true)][string]$RecoveryJobId)
  if (-not (Test-Path -LiteralPath $protectedRecoveryParent -PathType Container) -or
      -not (Test-Path -LiteralPath $RecoveryRoot -PathType Container)) {
    throw "Protected lifecycle recovery metadata is missing."
  }
  $parentItem = Get-Item -LiteralPath $protectedRecoveryParent -Force
  $rootItem = Get-Item -LiteralPath $RecoveryRoot -Force
  if (($parentItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
      ($rootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
      -not (Test-HwV3PathWithin -Path $RecoveryRoot -Parent $protectedRecoveryParent) -or
      (Split-Path -Leaf $RecoveryRoot) -cne $RecoveryJobId) {
    throw "Protected lifecycle recovery directory is unsafe."
  }
}

function Remove-ProtectedRecoveryDirectory {
  param([Parameter(Mandatory=$true)][string]$RecoveryRoot, [Parameter(Mandatory=$true)][string]$RecoveryJobId)
  Assert-ProtectedRecoveryDirectory -RecoveryRoot $RecoveryRoot -RecoveryJobId $RecoveryJobId
  Remove-Item -LiteralPath $RecoveryRoot -Recurse -Force
  if (Test-Path -LiteralPath $RecoveryRoot) {
    throw "Protected lifecycle recovery directory could not be removed."
  }
}

$mutex = $null
try {
  $mutex = Enter-HwV3LifecycleMutex -TimeoutMilliseconds 30000
  $recoveryJobIds = if (-not [string]::IsNullOrWhiteSpace($JobId)) {
    @((Assert-HwV3JobId -JobId $JobId))
  } else {
    $discovered = @()
    if (Test-Path -LiteralPath $transactions -PathType Container) {
      $discovered += @(Get-ChildItem -LiteralPath $transactions -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
    }
    if (Test-Path -LiteralPath $protectedRecoveryParent -PathType Container) {
      $discovered += @(Get-ChildItem -LiteralPath $protectedRecoveryParent -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
    }
    @($discovered | Where-Object { $_ -cmatch '^[0-9a-f]{32}$' } | Sort-Object -Unique)
  }
  foreach ($recoveryJobId in $recoveryJobIds) {
    $recoveryJobId = Assert-HwV3JobId -JobId $recoveryJobId
    $transactionRoot = Join-Path $transactions $recoveryJobId
    $protectedRecoveryRoot = Join-Path $InstallRoot (".recovery\" + $recoveryJobId)
    $protectedInstallationSnapshot = Join-Path $protectedRecoveryRoot "installation-before.json"
    $protectedTransactionSnapshot = Join-Path $protectedRecoveryRoot "transaction.json"
    if (-not (Test-Path -LiteralPath $protectedTransactionSnapshot -PathType Leaf)) {
      if (-not [string]::IsNullOrWhiteSpace($JobId)) {
        throw "Protected lifecycle recovery metadata is missing."
      }
      continue
    }

    Assert-ProtectedRecoveryDirectory -RecoveryRoot $protectedRecoveryRoot -RecoveryJobId $recoveryJobId
    $protectedTransaction = Read-HwV3Json -Path $protectedTransactionSnapshot -Required
    $outcome = [string]$protectedTransaction.outcome
    if ([int]$protectedTransaction.schema -ne 3 -or [string]$protectedTransaction.product -ne "Insta360_HW" -or
        [string]$protectedTransaction.job_id -cne $recoveryJobId -or
        -not (Test-SameHwV3Path -Left ([string]$protectedTransaction.install_root) -Right $InstallRoot) -or
        -not (Test-SameHwV3Path -Left ([string]$protectedTransaction.state_root) -Right $StateRoot) -or
        -not ($protectedTransaction.runtime_created -is [bool]) -or
        ($outcome -cne "pending" -and $outcome -cne "completed")) {
      throw "Protected lifecycle transaction metadata is invalid."
    }
    $oldRelative = [string]$protectedTransaction.old_relative
    $newRelative = [string]$protectedTransaction.new_relative
    $oldRuntime = Resolve-HwV3RuntimePointer -InstallRoot $InstallRoot -RelativePath $oldRelative -Field "old_relative"
    $newRuntime = Resolve-HwV3RuntimePointer -InstallRoot $InstallRoot -RelativePath $newRelative -Field "new_relative"
    $runtimeWasCreated = [bool]$protectedTransaction.runtime_created
    $journalPath = Join-Path $transactionRoot "journal.json"

    if ($outcome -ceq "completed") {
      [void](Clear-HwV3RecoveryTask)
      Remove-ProtectedRecoveryDirectory -RecoveryRoot $protectedRecoveryRoot -RecoveryJobId $recoveryJobId
      Write-HwV3JsonAtomic -Path $journalPath -Value ([ordered]@{
        schema = 3
        product = "Insta360_HW"
        job_id = $recoveryJobId
        phase = "completed"
        install_root = $InstallRoot
        state_root = $StateRoot
        old_relative = $oldRelative
        new_relative = $newRelative
        recovered = $false
        cleanup_completed = $true
        updated_at = (Get-Date).ToUniversalTime().ToString("o")
      })
      Set-HwV3JobPhase -StateRoot $StateRoot -JobId $recoveryJobId -Phase "completed" -Progress 100 `
        -Message "Update cleanup completed; the verified runtime remains active." `
        -Additional @{ rolled_back = $false; recovery_required = $false; cleanup_pending = $false; cancellable = $false } | Out-Null
      continue
    }

    if (-not (Test-Path -LiteralPath $protectedInstallationSnapshot -PathType Leaf)) {
      throw "Protected lifecycle installation snapshot is missing."
    }

    $before = Read-HwV3Json -Path $protectedInstallationSnapshot -Required
    if ([int]$before.schema_version -ne 3 -or [string]$before.product -ne "Insta360_HW" -or
        [string]$before.layout -ne "versioned-runtime-v3" -or [int]$before.generation -lt 1 -or
        [string]$before.active_runtime -cne $oldRelative) {
      throw "Protected installation recovery metadata is invalid."
    }
    $beforeActive = Resolve-HwV3RuntimePointer -InstallRoot $InstallRoot `
      -RelativePath ([string]$before.active_runtime) -Field "protected active_runtime"
    if (-not (Test-SameHwV3Path -Left $beforeActive -Right $oldRuntime)) {
      throw "Protected installation recovery metadata identifies the wrong runtime."
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$before.previous_runtime)) {
      Resolve-HwV3RuntimePointer -InstallRoot $InstallRoot `
        -RelativePath ([string]$before.previous_runtime) -Field "protected previous_runtime" | Out-Null
    }
    $oldManifest = Read-HwV3Json -Path (Join-Path $oldRuntime "install_manifest.json") -Required
    Assert-HwV3RuntimeTree -Path $oldRuntime -ExpectedVersion ([string]$oldManifest.version) `
      -ExpectedRevision ([string]$oldManifest.revision) -RequireCadence:(-not $SkipCadence) | Out-Null

    $current = $null
    try { $current = Read-HwV3Installation -InstallRoot $InstallRoot } catch { $current = $null }
    $pointerCommitted = $false
    $pointerUnchanged = $false
    if ($null -ne $current) {
      if ([string]$current.active_runtime -ceq $newRelative) {
        if ([string]$current.previous_runtime -cne $oldRelative -or
            [int]$current.generation -ne ([int]$before.generation + 1)) {
          throw "Committed installation metadata does not match the protected recovery transaction."
        }
        $pointerCommitted = $true
      } elseif ([string]$current.active_runtime -ceq $oldRelative) {
        if ([int]$current.generation -ne [int]$before.generation -or
            [string]$current.previous_runtime -cne [string]$before.previous_runtime) {
          throw "Uncommitted installation metadata changed unexpectedly."
        }
        $pointerUnchanged = $true
      } else {
        throw "Current installation pointer does not match the protected recovery transaction."
      }
    }

    $cadenceSnapshot = ""
    if (-not $SkipCadence) {
      $expectedSnapshot = Join-Path $protectedRecoveryRoot "cadence_snapshot"
      if (Test-Path -LiteralPath $expectedSnapshot -PathType Container) { $cadenceSnapshot = $expectedSnapshot }
    }
    $restored = $before
    if (-not $NoRestart -and $pointerCommitted -and (Test-Path -LiteralPath $newRuntime -PathType Container)) {
      Stop-HwV3Service -RuntimeRoot $newRuntime -StateRoot $StateRoot
    }
    if (-not $pointerUnchanged) {
      Write-HwV3JsonAtomic -Path (Join-Path $InstallRoot "installation.json") -Value $restored
    }
    if (-not [string]::IsNullOrWhiteSpace($cadenceSnapshot)) {
      . (Join-Path $oldRuntime "scripts\lib\Paths.ps1")
      . (Join-Path $oldRuntime "scripts\lib\Cadence.ps1")
      . (Join-Path $oldRuntime "scripts\lib\TclScripts.ps1")
      Restore-HwAgentCadenceDeploymentTransaction -SnapshotRoot $cadenceSnapshot
    }
    if (-not $NoRestart) { Start-HwV3Service -RuntimeRoot $oldRuntime -StateRoot $StateRoot }
    $cleanupWarning = ""
    if ($runtimeWasCreated -and [string]$restored.previous_runtime -cne $newRelative -and
        (Test-Path -LiteralPath $newRuntime)) {
      try {
        $newRuntimeItem = Get-Item -LiteralPath $newRuntime -Force
        if (($newRuntimeItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
          throw "Refusing to remove a reparse-point runtime during recovery."
        }
        Remove-Item -LiteralPath $newRuntime -Recurse -Force
      }
      catch { $cleanupWarning = $_.Exception.Message }
    }
    [void](Clear-HwV3RecoveryTask)
    if (-not [string]::IsNullOrWhiteSpace($cadenceSnapshot)) {
      Complete-HwAgentCadenceDeploymentTransaction -SnapshotRoot $cadenceSnapshot
    }
    Remove-ProtectedRecoveryDirectory -RecoveryRoot $protectedRecoveryRoot -RecoveryJobId $recoveryJobId
    $recoveredJournal = [ordered]@{
      schema = 3
      product = "Insta360_HW"
      job_id = $recoveryJobId
      phase = "rolled_back"
      install_root = $InstallRoot
      state_root = $StateRoot
      old_runtime = $oldRuntime
      new_runtime = $newRuntime
      old_relative = $oldRelative
      new_relative = $newRelative
      recovered = $true
      updated_at = (Get-Date).ToUniversalTime().ToString("o")
    }
    Write-HwV3JsonAtomic -Path $journalPath -Value $recoveredJournal
    Set-HwV3JobPhase -StateRoot $StateRoot -JobId $recoveryJobId -Phase "failed" -Progress 100 `
      -Message "An interrupted update was rolled back to the previous runtime." `
      -Additional @{ rolled_back = $true; recovery_required = $false; cleanup_pending = (-not [string]::IsNullOrWhiteSpace($cleanupWarning)); cleanup_warning = $cleanupWarning; cancellable = $false } | Out-Null
  }
} finally {
  if ($null -ne $mutex) { Exit-HwV3LifecycleMutex -Mutex $mutex }
}
