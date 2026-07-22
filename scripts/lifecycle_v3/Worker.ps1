param(
  [Parameter(Mandatory=$true)][string]$InstallRoot,
  [Parameter(Mandatory=$true)][string]$StateRoot,
  [Parameter(Mandatory=$true)][string]$JobId,
  [Parameter(Mandatory=$true)][string]$StageRoot,
  [Parameter(Mandatory=$true)][string]$ExpectedVersion,
  [Parameter(Mandatory=$true)][string]$ExpectedRevision,
  [Parameter(Mandatory=$true)][string]$ExpectedTreeSha256,
  [string]$FaultAt = "",
  [switch]$NoRestart,
  [switch]$SkipCadence,
  [switch]$SkipRecoveryRegistration
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Contract.ps1")
. (Join-Path $PSScriptRoot "Runtime.ps1")

$InstallRoot = Get-HwV3FullPath -Path $InstallRoot -Label "InstallRoot"
$StateRoot = Get-HwV3FullPath -Path $StateRoot -Label "StateRoot"
$env:INSTA360_HW_STATE_ROOT = $StateRoot
$JobId = Assert-HwV3JobId -JobId $JobId
$ExpectedVersion = Assert-HwV3Version -Version $ExpectedVersion
$ExpectedRevision = Assert-HwV3Revision -Revision $ExpectedRevision
$ExpectedTreeSha256 = $ExpectedTreeSha256.ToLowerInvariant()
if ($ExpectedTreeSha256 -notmatch '^[0-9a-f]{64}$') { throw "ExpectedTreeSha256 must be a lowercase SHA256." }
if ($InstallRoot -ieq $StateRoot -or (Test-HwV3PathWithin -Path $StateRoot -Parent $InstallRoot) -or
    (Test-HwV3PathWithin -Path $InstallRoot -Parent $StateRoot)) {
  throw "Mutable lifecycle state must be outside the installation root."
}

$transactionRoot = Join-Path $StateRoot ("lifecycle\v3\transactions\" + $JobId)
$expectedStage = Join-Path $transactionRoot "stage"
$StageRoot = Get-HwV3FullPath -Path $StageRoot -Label "StageRoot"
if ($StageRoot -ine [System.IO.Path]::GetFullPath($expectedStage).TrimEnd("\")) {
  throw "StageRoot does not belong to this lifecycle transaction."
}
New-Item -ItemType Directory -Force -Path $transactionRoot | Out-Null
$journalPath = Join-Path $transactionRoot "journal.json"
$installationPath = Join-Path $InstallRoot "installation.json"
$runtimeParent = Join-Path $InstallRoot "runtime"
New-Item -ItemType Directory -Force -Path $runtimeParent | Out-Null

$metadata = Read-HwV3Installation -InstallRoot $InstallRoot
$originalMetadata = $metadata | ConvertTo-Json -Depth 24 | ConvertFrom-Json
$oldRelative = [string]$metadata.active_runtime
$oldRuntime = Resolve-HwV3RuntimePointer -InstallRoot $InstallRoot -RelativePath $oldRelative -Field "active_runtime"
$oldManifest = Read-HwV3Json -Path (Join-Path $oldRuntime "install_manifest.json") -Required
Assert-HwV3RuntimeTree -Path $oldRuntime -ExpectedVersion ([string]$oldManifest.version) `
  -ExpectedRevision ([string]$oldManifest.revision) -RequireCadence:(-not $SkipCadence) | Out-Null

$newRelative = Get-HwV3RuntimeRelativePath -Version $ExpectedVersion -Revision $ExpectedRevision
if ($newRelative -ceq $oldRelative) { throw "The requested runtime is already active." }
$newRuntime = Resolve-HwV3RuntimePointer -InstallRoot $InstallRoot -RelativePath $newRelative -Field "active_runtime"
$runtimeId = Get-HwV3RuntimeId -Version $ExpectedVersion -Revision $ExpectedRevision
$incoming = Join-Path $runtimeParent ("." + $runtimeId + "." + $JobId + ".incoming")
$recoveryTaskName = "Insta360_HW_Recovery_" + $JobId
$protectedRecoveryRoot = Join-Path $InstallRoot (".recovery\" + $JobId)
$protectedCadenceSnapshot = Join-Path $protectedRecoveryRoot "cadence_snapshot"
$protectedInstallationSnapshot = Join-Path $protectedRecoveryRoot "installation-before.json"
$protectedTransactionSnapshot = Join-Path $protectedRecoveryRoot "transaction.json"
$protectedRecoveryBootstrap = Join-Path $protectedRecoveryRoot "Resume.ps1"
$pointerCommitted = $false
$serviceStopped = $false
$transactionCompleted = $false
$runtimeCreatedByThisWorker = $false
$cadenceSnapshot = ""
$cadenceEnabled = $false
$cadenceDirs = @()
$armedBootId = Get-HwV3BootIdentity

function Write-WorkerJournal {
  param([Parameter(Mandatory=$true)][string]$Phase, [hashtable]$Additional = @{})
  $value = [ordered]@{
    schema = 3
    product = "Insta360_HW"
    job_id = $JobId
    phase = $Phase
    install_root = $InstallRoot
    state_root = $StateRoot
    stage_root = $StageRoot
    incoming_root = $incoming
    old_runtime = $oldRuntime
    new_runtime = $newRuntime
    old_relative = $oldRelative
    new_relative = $newRelative
    runtime_created = [bool]$runtimeCreatedByThisWorker
    cadence_snapshot = $cadenceSnapshot
    recovery_task_name = $recoveryTaskName
    updated_at = (Get-Date).ToUniversalTime().ToString("o")
  }
  foreach ($key in $Additional.Keys) { $value[$key] = $Additional[$key] }
  Write-HwV3JsonAtomic -Path $journalPath -Value $value
}

function Remove-IncomingTree {
  if (-not (Test-Path -LiteralPath $incoming)) { return }
  if (-not (Test-HwV3PathWithin -Path $incoming -Parent $runtimeParent) -or
      (Split-Path -Leaf $incoming) -cne ("." + $runtimeId + "." + $JobId + ".incoming")) {
    throw "Refusing to remove an unrelated runtime tree."
  }
  Remove-Item -LiteralPath $incoming -Recurse -Force
}

function Set-WorkerProgress {
  param(
    [Parameter(Mandatory=$true)][int]$Progress,
    [Parameter(Mandatory=$true)][string]$Message,
    [int]$DetailCurrent = 0,
    [int]$DetailTotal = 0
  )
  $additional = @{
    cancellable = $false
    worker_pid = $PID
    detail_current = [Math]::Max(0, $DetailCurrent)
    detail_total = [Math]::Max(0, $DetailTotal)
    detail_unit = $(if ($DetailTotal -gt 0) { "files" } else { "" })
  }
  Set-HwV3JobPhase -StateRoot $StateRoot -JobId $JobId -Phase "committing" -Progress $Progress `
    -Message $Message -Additional $additional | Out-Null
}

function Get-WorkerTreeSha256 {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][int]$StartProgress,
    [Parameter(Mandatory=$true)][int]$EndProgress,
    [Parameter(Mandatory=$true)][string]$Message
  )
  $state = [pscustomobject]@{ progress = $StartProgress - 1 }
  $callback = {
    param([int]$Processed, [int]$Total)
    $ratio = if ($Total -gt 0) { [Math]::Min(1.0, $Processed / [double]$Total) } else { 1.0 }
    $overall = $StartProgress + [int][Math]::Floor(($EndProgress - $StartProgress) * $ratio)
    if ($overall -gt [int]$state.progress) {
      Set-WorkerProgress -Progress $overall -Message $Message -DetailCurrent $Processed -DetailTotal $Total
      $state.progress = $overall
    }
  }.GetNewClosure()
  return Get-HwV3TreeSha256 -Path $Path -ProgressCallback $callback
}

function Copy-StagedRuntime {
  Set-WorkerProgress -Progress 70 -Message "Verifying staged runtime files."
  Assert-HwV3RuntimeTree -Path $StageRoot -ExpectedVersion $ExpectedVersion -ExpectedRevision $ExpectedRevision `
    -RequireCadence:(-not $SkipCadence) | Out-Null
  if ((Get-WorkerTreeSha256 -Path $StageRoot -StartProgress 70 -EndProgress 73 `
        -Message "Verifying staged runtime files.") -cne $ExpectedTreeSha256) {
    throw "Staged runtime tree SHA256 does not match the verified release."
  }
  Set-WorkerProgress -Progress 74 -Message "Copying the candidate runtime into the installation."
  Remove-IncomingTree
  New-Item -ItemType Directory -Force -Path $incoming | Out-Null
  $robocopy = Get-HwV3RobocopyPath
  & $robocopy $StageRoot $incoming /MIR /COPY:DAT /DCOPY:DAT /R:2 /W:1 /XJ /NFL /NDL /NJH /NJS | Out-Null
  $copyExit = $LASTEXITCODE
  if ($copyExit -ge 8) { throw "Runtime copy failed with robocopy exit code $copyExit." }
  Set-WorkerProgress -Progress 75 -Message "Verifying copied runtime files."
  Assert-HwV3RuntimeTree -Path $incoming -ExpectedVersion $ExpectedVersion -ExpectedRevision $ExpectedRevision `
    -RequireCadence:(-not $SkipCadence) | Out-Null
  if ((Get-WorkerTreeSha256 -Path $incoming -StartProgress 75 -EndProgress 78 `
        -Message "Verifying copied runtime files.") -cne $ExpectedTreeSha256) {
    throw "Copied runtime tree SHA256 does not match the staged runtime."
  }
  if (Test-Path -LiteralPath $newRuntime -PathType Container) {
    Set-WorkerProgress -Progress 79 -Message "Existing runtime found; verifying identical content."
    Assert-HwV3RuntimeTree -Path $newRuntime -ExpectedVersion $ExpectedVersion -ExpectedRevision $ExpectedRevision `
      -RequireCadence:(-not $SkipCadence) | Out-Null
    if ((Get-WorkerTreeSha256 -Path $newRuntime -StartProgress 79 -EndProgress 80 `
          -Message "Existing runtime found; verifying identical content.") -cne $ExpectedTreeSha256) {
      throw "An existing runtime directory has the requested identity but different content."
    }
    Remove-IncomingTree
  } else {
    foreach ($attempt in 0..7) {
      try {
        [System.IO.Directory]::Move($incoming, $newRuntime)
        $script:runtimeCreatedByThisWorker = $true
        break
      } catch [System.IO.IOException] {
        if ($attempt -eq 7) { throw }
        Start-Sleep -Milliseconds (50 * ($attempt + 1))
      } catch [System.UnauthorizedAccessException] {
        if ($attempt -eq 7) { throw }
        Start-Sleep -Milliseconds (50 * ($attempt + 1))
      }
    }
  }
  Set-WorkerProgress -Progress 80 -Message "Candidate runtime files copied and verified."
}

function Write-ProtectedTransactionSnapshot {
  param([ValidateSet("pending", "completed")][string]$Outcome = "pending")
  Write-HwV3JsonAtomic -Path $protectedTransactionSnapshot -Value ([ordered]@{
    schema = 3
    product = "Insta360_HW"
    job_id = $JobId
    install_root = $InstallRoot
    state_root = $StateRoot
    old_relative = $oldRelative
    new_relative = $newRelative
    runtime_created = [bool]$runtimeCreatedByThisWorker
    skip_cadence = [bool]$SkipCadence
    armed_boot_id = $armedBootId
    outcome = $Outcome
  })
}

function Initialize-ProtectedRecovery {
  if (Test-Path -LiteralPath $protectedRecoveryRoot) {
    throw "Protected recovery directory already exists for this job."
  }
  New-Item -ItemType Directory -Force -Path $protectedRecoveryRoot | Out-Null
  $resumeSource = Join-Path $PSScriptRoot "Resume.ps1"
  if (-not (Test-Path -LiteralPath $resumeSource -PathType Leaf)) {
    throw "Trusted lifecycle recovery bootstrap is missing."
  }
  Copy-Item -LiteralPath $resumeSource -Destination $protectedRecoveryBootstrap -Force
  Write-HwV3JsonAtomic -Path $protectedInstallationSnapshot -Value $originalMetadata
  Write-ProtectedTransactionSnapshot -Outcome "pending"
}

function Initialize-CadenceSnapshot {
  if ($SkipCadence) { return }
  . (Join-Path $oldRuntime "scripts\lib\Paths.ps1")
  . (Join-Path $oldRuntime "scripts\lib\Cadence.ps1")
  . (Join-Path $oldRuntime "scripts\lib\TclScripts.ps1")
  if (Test-HwAgentCadenceIntegrationEnabled) {
    $script:cadenceEnabled = $true
    $recordedDirs = @(Get-HwAgentRecordedCadenceAutoLoadDirs)
    $script:cadenceDirs = @(Get-HwAgentCadenceCleanupAutoLoadDirs -AdditionalPaths $recordedDirs -SkipDiscovery)
    if ($cadenceDirs.Count -eq 0) {
      throw "Cadence integration is enabled but no managed loader directory is recorded."
    }
    $temporarySnapshot = Start-HwAgentCadenceDeploymentTransaction -AutoLoadDirs $cadenceDirs
    Move-Item -LiteralPath $temporarySnapshot -Destination $protectedCadenceSnapshot
    $script:cadenceSnapshot = $protectedCadenceSnapshot
  }
}

function Deploy-NewCadenceIntegration {
  if ($SkipCadence -or -not $cadenceEnabled) { return }
  . (Join-Path $newRuntime "scripts\lib\Paths.ps1")
  . (Join-Path $newRuntime "scripts\lib\Cadence.ps1")
  . (Join-Path $newRuntime "scripts\lib\TclScripts.ps1")
  $python = Find-Python -Root $newRuntime
  $pluginStatePath = Join-Path $StateRoot "config\plugin_state.json"
  $loaders = @(Install-CadenceLoader -ToolRoot $newRuntime -PythonPath $python -AutoLoadDirs $cadenceDirs `
    -PluginStatePath $pluginStatePath)
  Update-HwAgentCadenceOwnershipManifest -LoaderPaths $loaders | Out-Null
  Set-HwAgentCadenceIntegrationState -Enabled:$true -LoaderPaths $cadenceDirs | Out-Null
}

function Restore-CadenceIntegration {
  if ($SkipCadence -or [string]::IsNullOrWhiteSpace($cadenceSnapshot)) { return }
  . (Join-Path $oldRuntime "scripts\lib\Paths.ps1")
  . (Join-Path $oldRuntime "scripts\lib\Cadence.ps1")
  . (Join-Path $oldRuntime "scripts\lib\TclScripts.ps1")
  Restore-HwAgentCadenceDeploymentTransaction -SnapshotRoot $cadenceSnapshot
}

function Complete-ProtectedRecovery {
  if (-not $SkipCadence -and -not [string]::IsNullOrWhiteSpace($cadenceSnapshot)) {
    Complete-HwAgentCadenceDeploymentTransaction -SnapshotRoot $cadenceSnapshot
  }
  Remove-Item -LiteralPath $protectedInstallationSnapshot -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $protectedTransactionSnapshot -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $protectedRecoveryBootstrap -Force -ErrorAction SilentlyContinue
  if ((Test-Path -LiteralPath $protectedRecoveryRoot -PathType Container) -and
      (@(Get-ChildItem -LiteralPath $protectedRecoveryRoot -Force -ErrorAction SilentlyContinue).Count -eq 0)) {
    Remove-Item -LiteralPath $protectedRecoveryRoot -Force
  }
}

function Set-RecoveryRegistration {
  if ($SkipRecoveryRegistration) { return }
  Register-HwV3RecoveryTask -TaskName $recoveryTaskName `
    -PowerShellPath (Get-HwV3PowerShellPath) -ScriptPath $protectedRecoveryBootstrap | Out-Null
}

function Clear-RecoveryRegistration {
  if ($SkipRecoveryRegistration) { return $true }
  return Remove-HwV3RecoveryTask -TaskName $recoveryTaskName
}

function Commit-RuntimePointer {
  $next = [ordered]@{
    schema_version = 3
    product = "Insta360_HW"
    layout = "versioned-runtime-v3"
    active_runtime = $newRelative
    previous_runtime = $oldRelative
    generation = [int]$metadata.generation + 1
    updated_at = (Get-Date).ToUniversalTime().ToString("o")
  }
  Write-HwV3JsonAtomic -Path $installationPath -Value $next
  $script:pointerCommitted = $true
}

function Restore-RuntimePointer {
  Write-HwV3JsonAtomic -Path $installationPath -Value $originalMetadata
  $script:pointerCommitted = $false
}

$mutex = $null
try {
  $mutex = Enter-HwV3LifecycleMutex -TimeoutMilliseconds 0
  if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot "Insta360_HW.exe") -PathType Leaf)) {
    throw "Stable launcher is missing from the installation root."
  }
  Write-WorkerJournal -Phase "preparing_runtime"
  Copy-StagedRuntime
  Write-WorkerJournal -Phase "runtime_ready"
  Invoke-HwV3Fault -FaultAt $FaultAt -Point "runtime_ready"

  Set-WorkerProgress -Progress 81 -Message "Preparing rollback protection and checking Cadence integration."
  Initialize-ProtectedRecovery
  Initialize-CadenceSnapshot
  Write-WorkerJournal -Phase "recovery_armed"
  Set-WorkerProgress -Progress 83 -Message "Rollback protection is ready; stopping the previous backend."
  Set-RecoveryRegistration
  if (-not $NoRestart) {
    Stop-HwV3Service -RuntimeRoot $oldRuntime -StateRoot $StateRoot
    $script:serviceStopped = $true
  }
  Invoke-HwV3Fault -FaultAt $FaultAt -Point "service_stopped"

  Set-HwV3JobPhase -StateRoot $StateRoot -JobId $JobId -Phase "switching" -Progress 86 `
    -Message "Activating the verified runtime pointer." -Additional @{ cancellable = $false; detail_current = 0; detail_total = 0; detail_unit = "" } | Out-Null
  Commit-RuntimePointer
  Write-WorkerJournal -Phase "pointer_committed"
  Invoke-HwV3Fault -FaultAt $FaultAt -Point "pointer_committed"

  Set-HwV3JobPhase -StateRoot $StateRoot -JobId $JobId -Phase "integrating" -Progress 91 `
    -Message "Deploying Cadence integration from the active runtime." -Additional @{ cancellable = $false; detail_current = 0; detail_total = 0; detail_unit = "" } | Out-Null
  Deploy-NewCadenceIntegration
  Write-WorkerJournal -Phase "integration_deployed"
  Invoke-HwV3Fault -FaultAt $FaultAt -Point "integration_deployed"

  Set-HwV3JobPhase -StateRoot $StateRoot -JobId $JobId -Phase "verifying_runtime" -Progress 96 `
    -Message "Starting and verifying the activated backend." -Additional @{ cancellable = $false; detail_current = 0; detail_total = 0; detail_unit = "" } | Out-Null
  if (-not $NoRestart) { Start-HwV3Service -RuntimeRoot $newRuntime -StateRoot $StateRoot }
  Invoke-HwV3Fault -FaultAt $FaultAt -Point "runtime_verified"
  Write-ProtectedTransactionSnapshot -Outcome "completed"
  Write-WorkerJournal -Phase "completed"
  Set-HwV3JobPhase -StateRoot $StateRoot -JobId $JobId -Phase "completed" -Progress 100 `
    -Message "Update completed and the new runtime passed verification." `
    -Additional @{ version = $ExpectedVersion; revision = $ExpectedRevision; active_runtime = $newRelative; rolled_back = $false; cancellable = $false } | Out-Null
  $script:transactionCompleted = $true
  $cleanupWarnings = @()
  $registrationCleared = $false
  try { $registrationCleared = [bool](Clear-RecoveryRegistration) }
  catch { $cleanupWarnings += $_.Exception.Message }
  if ($registrationCleared) {
    try { Complete-ProtectedRecovery } catch { $cleanupWarnings += $_.Exception.Message }
  }
  if ($cleanupWarnings.Count -gt 0) {
    try {
      Set-HwV3JobPhase -StateRoot $StateRoot -JobId $JobId -Phase "completed" -Progress 100 `
        -Message "Update completed; deferred cleanup will be retried later." `
        -Additional @{ version = $ExpectedVersion; revision = $ExpectedRevision; active_runtime = $newRelative; rolled_back = $false; cleanup_pending = $true; cleanup_warning = ($cleanupWarnings -join " | "); cancellable = $false } | Out-Null
    } catch {}
  }
} catch {
  $failure = $_.Exception.Message
  if ($transactionCompleted) { return }
  $rollbackError = ""
  $cleanupWarning = ""
  $rolledBack = -not $pointerCommitted
  if ($pointerCommitted) {
    try {
      if (-not $NoRestart) { Stop-HwV3Service -RuntimeRoot $newRuntime -StateRoot $StateRoot }
      Restore-RuntimePointer
      Restore-CadenceIntegration
      if (-not $NoRestart) { Start-HwV3Service -RuntimeRoot $oldRuntime -StateRoot $StateRoot }
      if ($runtimeCreatedByThisWorker -and [string]$originalMetadata.previous_runtime -cne $newRelative -and
          (Test-Path -LiteralPath $newRuntime)) {
        try { Remove-Item -LiteralPath $newRuntime -Recurse -Force }
        catch { $cleanupWarning = $_.Exception.Message }
      }
      $rolledBack = $true
      $registrationCleared = $false
      try { $registrationCleared = [bool](Clear-RecoveryRegistration) }
      catch {
        if (-not [string]::IsNullOrWhiteSpace($cleanupWarning)) { $cleanupWarning += " | " }
        $cleanupWarning += $_.Exception.Message
      }
      if ($registrationCleared) {
        try { Complete-ProtectedRecovery }
        catch {
          if (-not [string]::IsNullOrWhiteSpace($cleanupWarning)) { $cleanupWarning += " | " }
          $cleanupWarning += $_.Exception.Message
        }
      }
      Write-WorkerJournal -Phase "rolled_back" -Additional @{ error = $failure; rolled_back = $true; cleanup_warning = $cleanupWarning }
    } catch {
      $rollbackError = $_.Exception.Message
      $rolledBack = $false
      try { Write-WorkerJournal -Phase "rollback_failed" -Additional @{ error = $failure; rollback_error = $rollbackError } } catch {}
    }
  } else {
    try { Remove-IncomingTree } catch {}
    if ($runtimeCreatedByThisWorker -and [string]$originalMetadata.previous_runtime -cne $newRelative -and
        (Test-Path -LiteralPath $newRuntime)) {
      try { Remove-Item -LiteralPath $newRuntime -Recurse -Force }
      catch { $cleanupWarning = $_.Exception.Message }
    }
    if ($serviceStopped -and -not $NoRestart) {
      try { Start-HwV3Service -RuntimeRoot $oldRuntime -StateRoot $StateRoot }
      catch {
        $rollbackError = $_.Exception.Message
        $rolledBack = $false
      }
    }
    if ($rolledBack) {
      $registrationCleared = $false
      try { $registrationCleared = [bool](Clear-RecoveryRegistration) }
      catch {
        if (-not [string]::IsNullOrWhiteSpace($cleanupWarning)) { $cleanupWarning += " | " }
        $cleanupWarning += $_.Exception.Message
      }
      if ($registrationCleared) {
        try { Complete-ProtectedRecovery }
        catch {
          if (-not [string]::IsNullOrWhiteSpace($cleanupWarning)) { $cleanupWarning += " | " }
          $cleanupWarning += $_.Exception.Message
        }
      }
    }
    try { Write-WorkerJournal -Phase "failed" -Additional @{ error = $failure; rolled_back = $rolledBack; rollback_error = $rollbackError; cleanup_warning = $cleanupWarning } } catch {}
  }
  $message = if ($rolledBack) { "Update failed and the previous runtime was restored: $failure" }
             else { "Update failed and rollback also failed: $failure / $rollbackError" }
  try {
    Set-HwV3JobPhase -StateRoot $StateRoot -JobId $JobId -Phase "failed" -Progress 100 -Message $message `
      -Additional @{ rolled_back = $rolledBack; rollback_error = $rollbackError; recovery_required = (-not $rolledBack); cleanup_pending = (-not [string]::IsNullOrWhiteSpace($cleanupWarning)); cleanup_warning = $cleanupWarning; cancellable = $false } | Out-Null
  } catch {}
  throw
} finally {
  if ($null -ne $mutex) { Exit-HwV3LifecycleMutex -Mutex $mutex }
}
