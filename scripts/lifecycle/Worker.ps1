param(
  [ValidateSet("Update", "Recover")]
  [string]$Action = "Update",
  [Parameter(Mandatory=$true)][string]$InstallRoot,
  [Parameter(Mandatory=$true)][string]$StateRoot,
  [Parameter(Mandatory=$true)][string]$JobId,
  [string]$StageRoot = "",
  [string]$ExpectedVersion = "",
  [string]$ExpectedTreeSha256 = "",
  [string]$FaultAt = "",
  [switch]$NoRestart,
  [switch]$SkipCadence,
  [switch]$SkipRecoveryRegistration
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "Contract.ps1")
. (Join-Path $ScriptDir "Runtime.ps1")

Assert-HwLifecycleJobId -JobId $JobId | Out-Null
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot).TrimEnd("\")
$StateRoot = [System.IO.Path]::GetFullPath($StateRoot).TrimEnd("\")
$env:INSTA360_HW_STATE_ROOT = $StateRoot
New-Item -ItemType Directory -Force -Path $StateRoot | Out-Null
[System.IO.Directory]::SetCurrentDirectory($StateRoot)
Set-Location -LiteralPath $StateRoot

$transactionRoot = Join-Path $StateRoot ("lifecycle\transactions\" + $JobId)
$journalPath = Join-Path $transactionRoot "journal.json"
$parent = Split-Path -Parent $InstallRoot
$leaf = Split-Path -Leaf $InstallRoot
$candidate = Join-Path $parent ("." + $leaf + "." + $JobId + ".candidate")
$backup = Join-Path $parent ("." + $leaf + "." + $JobId + ".backup")
$failedRoot = Join-Path $parent ("." + $leaf + "." + $JobId + ".failed")
$runOnceName = "Insta360_HW_Recovery_" + $JobId
$cadenceSnapshot = ""
$cadenceLibraryLoaded = $false
$cadenceIntegrationActive = $false
$cadenceInstallDirs = @()
$cadenceInstalledDirs = @()
$commitStarted = $false
$transactionCommitted = $false

New-Item -ItemType Directory -Force -Path $transactionRoot | Out-Null

foreach ($libraryRoot in @($InstallRoot, $backup, $candidate)) {
  $pathsLibrary = Join-Path $libraryRoot "scripts\lib\Paths.ps1"
  $cadenceLibrary = Join-Path $libraryRoot "scripts\lib\Cadence.ps1"
  $tclLibrary = Join-Path $libraryRoot "scripts\lib\TclScripts.ps1"
  if (-not $SkipCadence -and
      (Test-Path -LiteralPath $pathsLibrary -PathType Leaf) -and
      (Test-Path -LiteralPath $cadenceLibrary -PathType Leaf) -and
      (Test-Path -LiteralPath $tclLibrary -PathType Leaf)) {
    . $pathsLibrary
    . $cadenceLibrary
    . $tclLibrary
    $cadenceLibraryLoaded = $true
    break
  }
}

function Test-SameLifecyclePath {
  param([string]$Left, [string]$Right)
  if ([string]::IsNullOrWhiteSpace($Left) -or [string]::IsNullOrWhiteSpace($Right)) { return $false }
  try {
    return [System.IO.Path]::GetFullPath($Left).TrimEnd("\") -ieq [System.IO.Path]::GetFullPath($Right).TrimEnd("\")
  } catch { return $false }
}

function Write-Journal {
  param([Parameter(Mandatory=$true)][string]$Phase, [hashtable]$Additional = @{})
  $value = [ordered]@{
    schema = 2
    product = "Insta360_HW"
    job_id = $JobId
    phase = $Phase
    install_root = $InstallRoot
    state_root = $StateRoot
    stage_root = $StageRoot
    candidate_root = $candidate
    backup_root = $backup
    failed_root = $failedRoot
    expected_version = $ExpectedVersion
    expected_tree_sha256 = $ExpectedTreeSha256
    cadence_snapshot = $cadenceSnapshot
    worker_path = $PSCommandPath
    run_once_name = $runOnceName
    updated_at = (Get-Date).ToUniversalTime().ToString("o")
  }
  foreach ($key in $Additional.Keys) { $value[$key] = $Additional[$key] }
  Write-HwLifecycleJsonAtomic -Path $journalPath -Value $value
}

function Assert-Candidate {
  param([Parameter(Mandatory=$true)][string]$Path)
  Assert-HwLifecycleRuntimeRoot -Path $Path | Out-Null
  $version = (Get-Content -LiteralPath (Join-Path $Path "VERSION") -Raw -Encoding UTF8).Trim()
  if ([string]::IsNullOrWhiteSpace($ExpectedVersion) -or $version -ne $ExpectedVersion) {
    throw "Candidate version mismatch: expected $ExpectedVersion, got $version"
  }
  try {
    $manifest = Get-Content -LiteralPath (Join-Path $Path "install_manifest.json") -Raw -Encoding UTF8 | ConvertFrom-Json
  } catch {
    throw "Candidate install manifest is not valid JSON."
  }
  if ([int]$manifest.schema -ne 2) { throw "Candidate install manifest schema must be 2." }
  if ([string]$manifest.product -ne "Insta360_HW") { throw "Candidate product identity is invalid." }
  if ([string]$manifest.layout -ne "runtime-v2") { throw "Candidate layout must be runtime-v2." }
  if ([string]$manifest.version -ne $ExpectedVersion) { throw "Candidate manifest version does not match the requested version." }
}

function Assert-JournalIdentity {
  param([Parameter(Mandatory=$true)]$Journal)
  if ([int]$Journal.schema -ne 2 -or [string]$Journal.product -ne "Insta360_HW") {
    throw "Lifecycle journal identity is invalid."
  }
  if ([string]$Journal.job_id -ne $JobId) { throw "Lifecycle journal job ID does not match the request." }
  foreach ($pair in @(
    @([string]$Journal.install_root, $InstallRoot),
    @([string]$Journal.state_root, $StateRoot),
    @([string]$Journal.candidate_root, $candidate),
    @([string]$Journal.backup_root, $backup)
  )) {
    if (-not (Test-SameLifecyclePath -Left $pair[0] -Right $pair[1])) {
      throw "Lifecycle journal contains a path outside this transaction."
    }
  }
}

function Remove-TransactionTree {
  param([Parameter(Mandatory=$true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return }
  $full = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
  $fullParent = [System.IO.Path]::GetFullPath((Split-Path -Parent $full)).TrimEnd("\")
  if ($fullParent -ine [System.IO.Path]::GetFullPath($parent).TrimEnd("\")) {
    throw "Refusing to remove a lifecycle tree outside the install parent: $full"
  }
  $name = Split-Path -Leaf $full
  if (-not $name.StartsWith("." + $leaf + "." + $JobId + ".", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove an unrelated lifecycle tree: $full"
  }
  Remove-Item -LiteralPath $full -Recurse -Force
}

function Copy-CompleteCandidate {
  Remove-TransactionTree -Path $candidate
  New-Item -ItemType Directory -Force -Path $candidate | Out-Null
  & robocopy.exe $StageRoot $candidate /MIR /COPY:DAT /DCOPY:DAT /R:2 /W:1 /XJ /NFL /NDL /NJH /NJS | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "Candidate copy failed (robocopy $LASTEXITCODE)." }
  Assert-Candidate -Path $candidate
  $actualTreeSha256 = Get-HwLifecycleTreeSha256 -Path $candidate
  if ($actualTreeSha256 -cne $ExpectedTreeSha256) {
    throw "Candidate integrity tree SHA256 mismatch after the elevated copy."
  }
  foreach ($uninstaller in Get-ChildItem -LiteralPath $InstallRoot -File -Filter "unins*" -ErrorAction SilentlyContinue) {
    Copy-Item -LiteralPath $uninstaller.FullName -Destination (Join-Path $candidate $uninstaller.Name) -Force
  }
}

function Set-RecoveryRegistration {
  if ($SkipRecoveryRegistration) { return }
  $recoveryScript = Join-Path $backup "scripts\lifecycle\Recover.ps1"
  $command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -InstallRoot "{1}" -StateRoot "{2}"' -f `
    $recoveryScript, $InstallRoot, $StateRoot
  if ($NoRestart) { $command += " -NoRestart" }
  if ($SkipCadence) { $command += " -SkipCadence" }
  $key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce"
  New-Item -Path $key -Force | Out-Null
  Set-ItemProperty -Path $key -Name $runOnceName -Value $command -Type String
}

function Clear-RecoveryRegistration {
  if ($SkipRecoveryRegistration) { return }
  Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce" -Name $runOnceName -ErrorAction SilentlyContinue
}

function Restore-CadenceSnapshot {
  if ([string]::IsNullOrWhiteSpace($cadenceSnapshot) -or -not (Test-Path -LiteralPath $cadenceSnapshot)) { return }
  if (-not $cadenceLibraryLoaded) { throw "Cadence rollback snapshot exists but the rollback library is unavailable." }
  Restore-HwAgentCadenceDeploymentTransaction -SnapshotRoot $cadenceSnapshot
}

function Restore-PreviousRuntime {
  try { Stop-HwLifecycleService -RuntimeRoot $InstallRoot -StateRoot $StateRoot } catch {}

  if (Test-Path -LiteralPath $backup -PathType Container) {
    Assert-HwLifecycleRuntimeRoot -Path $backup | Out-Null
    if (Test-Path -LiteralPath $InstallRoot) {
      Remove-TransactionTree -Path $failedRoot
      Move-Item -LiteralPath $InstallRoot -Destination $failedRoot
    }
    Move-Item -LiteralPath $backup -Destination $InstallRoot
  } elseif (Test-Path -LiteralPath $InstallRoot -PathType Container) {
    Assert-HwLifecycleRuntimeRoot -Path $InstallRoot | Out-Null
    $activeVersion = (Get-Content -LiteralPath (Join-Path $InstallRoot "VERSION") -Raw -Encoding UTF8).Trim()
    if ($activeVersion -eq $ExpectedVersion) {
      throw "The previous runtime backup is missing while the candidate version is still active."
    }
  } else {
    throw "Neither the previous runtime nor its backup is available for rollback."
  }

  Remove-TransactionTree -Path $candidate
  Initialize-HwLifecycleState -RuntimeRoot $InstallRoot -StateRoot $StateRoot | Out-Null
  Restore-CadenceSnapshot
  if (-not $NoRestart) { Start-HwLifecycleService -RuntimeRoot $InstallRoot -StateRoot $StateRoot }
}

function Invoke-Recovery {
  $journal = Read-HwLifecycleJson -Path $journalPath
  if ($null -eq $journal) { return }
  Assert-JournalIdentity -Journal $journal
  if ([string]$journal.phase -in @("completed", "rolled_back")) {
    Clear-RecoveryRegistration
    return
  }

  $script:StageRoot = [string]$journal.stage_root
  $script:ExpectedVersion = [string]$journal.expected_version
  $script:cadenceSnapshot = [string]$journal.cadence_snapshot
  try {
    Restore-PreviousRuntime
    Write-Journal -Phase "rolled_back" -Additional @{ recovered = $true; interrupted_phase = [string]$journal.phase }
    Set-HwLifecycleJobPhase -StateRoot $StateRoot -JobId $JobId -Phase "failed" -Progress 100 `
      -Message "检测到中断的更新，已恢复到更新前版本。" `
      -Additional @{ rolled_back = $true; rollback_error = ""; recovery_required = $false } | Out-Null
    Clear-RecoveryRegistration
  } catch {
    $rollbackError = $_.Exception.Message
    try { Write-Journal -Phase "rollback_failed" -Additional @{ rollback_error = $rollbackError } } catch {}
    try {
      Set-HwLifecycleJobPhase -StateRoot $StateRoot -JobId $JobId -Phase "failed" -Progress 100 `
        -Message ("中断更新的自动恢复失败：" + $rollbackError) `
        -Additional @{ rolled_back = $false; rollback_error = $rollbackError; recovery_required = $true } | Out-Null
    } catch {}
    throw
  }
}

function Invoke-Update {
  Assert-HwLifecycleRuntimeRoot -Path $InstallRoot | Out-Null
  Remove-HwLifecycleTerminalRuntimeTrees -RuntimeRoot $InstallRoot -StateRoot $StateRoot
  if ([string]::IsNullOrWhiteSpace($StageRoot)) { throw "StageRoot is required for update." }
  $script:StageRoot = [System.IO.Path]::GetFullPath($StageRoot).TrimEnd("\")
  if ($ExpectedTreeSha256 -notmatch '^[0-9a-f]{64}$') {
    throw "ExpectedTreeSha256 must be a lowercase 64-character SHA256."
  }
  Assert-HwLifecycleWorkerHandoff -InstallRoot $InstallRoot -StateRoot $StateRoot -StageRoot $StageRoot `
    -JobId $JobId -ExpectedVersion $ExpectedVersion
  Assert-Candidate -Path $StageRoot

  try {
    Set-HwLifecycleJobPhase -StateRoot $StateRoot -JobId $JobId -Phase "committing" -Progress 72 `
      -Message "正在准备完整的新版本运行目录。" `
      -Additional @{ cancellable = $false; worker_pid = $PID } | Out-Null
    Write-Journal -Phase "preparing_candidate"
    Copy-CompleteCandidate
    Write-Journal -Phase "candidate_ready"
    Invoke-HwLifecycleFault -FaultAt $FaultAt -Point "candidate_ready"

    if ($cadenceLibraryLoaded -and (Test-HwAgentCadenceIntegrationEnabled)) {
      $script:cadenceIntegrationActive = $true
      $script:cadenceInstallDirs = @(Get-HwAgentManagedCadenceAutoLoadDirs)
      $script:cadenceSnapshot = Start-HwAgentCadenceDeploymentTransaction -AutoLoadDirs $cadenceInstallDirs
    }

    Set-RecoveryRegistration
    $script:commitStarted = $true
    Write-Journal -Phase "recovery_armed"

    Stop-HwLifecycleService -RuntimeRoot $InstallRoot -StateRoot $StateRoot
    Initialize-HwLifecycleState -RuntimeRoot $InstallRoot -StateRoot $StateRoot | Out-Null
    Write-Journal -Phase "state_externalized"
    Invoke-HwLifecycleFault -FaultAt $FaultAt -Point "service_stopped"

    Remove-TransactionTree -Path $backup
    Move-Item -LiteralPath $InstallRoot -Destination $backup
    Write-Journal -Phase "old_runtime_backed_up"
    Invoke-HwLifecycleFault -FaultAt $FaultAt -Point "old_runtime_backed_up"

    Move-Item -LiteralPath $candidate -Destination $InstallRoot
    Write-Journal -Phase "new_runtime_activated"
    Set-HwLifecycleJobPhase -StateRoot $StateRoot -JobId $JobId -Phase "switching" -Progress 82 `
      -Message "新版本运行目录已切换生效。" -Additional @{ cancellable = $false } | Out-Null
    Invoke-HwLifecycleFault -FaultAt $FaultAt -Point "new_runtime_activated"

    Initialize-HwLifecycleState -RuntimeRoot $InstallRoot -StateRoot $StateRoot | Out-Null
    Set-HwLifecycleJobPhase -StateRoot $StateRoot -JobId $JobId -Phase "integrating" -Progress 88 `
      -Message "正在恢复并验证 Cadence 集成。" -Additional @{ cancellable = $false } | Out-Null
    if ($cadenceIntegrationActive) {
      $activePathsLibrary = Join-Path $InstallRoot "scripts\lib\Paths.ps1"
      $activeCadenceLibrary = Join-Path $InstallRoot "scripts\lib\Cadence.ps1"
      $activeTclLibrary = Join-Path $InstallRoot "scripts\lib\TclScripts.ps1"
      foreach ($library in @($activePathsLibrary, $activeCadenceLibrary, $activeTclLibrary)) {
        if (-not (Test-Path -LiteralPath $library -PathType Leaf)) {
          throw "Activated runtime is missing Cadence integration library: $library"
        }
      }
      . $activePathsLibrary
      . $activeCadenceLibrary
      . $activeTclLibrary
      $python = Find-Python -Root $InstallRoot
      $installedLoaders = @(Install-CadenceLoader -ToolRoot $InstallRoot -PythonPath $python -AutoLoadDirs $cadenceInstallDirs)
      $script:cadenceInstalledDirs = @($installedLoaders | ForEach-Object { Split-Path -Parent $_ })
      Update-HwAgentCadenceOwnershipManifest -LoaderPaths $installedLoaders | Out-Null
    }
    Write-Journal -Phase "integration_deployed"
    Invoke-HwLifecycleFault -FaultAt $FaultAt -Point "integration_deployed"

    Set-HwLifecycleJobPhase -StateRoot $StateRoot -JobId $JobId -Phase "verifying_runtime" -Progress 94 `
      -Message "正在启动并验证新版本后端服务。" -Additional @{ cancellable = $false } | Out-Null
    if (-not $NoRestart) { Start-HwLifecycleService -RuntimeRoot $InstallRoot -StateRoot $StateRoot }
    if ($cadenceIntegrationActive) {
      Set-HwAgentCadenceIntegrationState -Enabled:$true -LoaderPaths $cadenceInstalledDirs | Out-Null
    }
    Write-Journal -Phase "runtime_verified"
    Invoke-HwLifecycleFault -FaultAt $FaultAt -Point "runtime_verified"

    Write-Journal -Phase "completed"
    Set-HwLifecycleJobPhase -StateRoot $StateRoot -JobId $JobId -Phase "completed" -Progress 100 `
      -Message "更新完成，新版本后端服务运行正常。" `
      -Additional @{ version = $ExpectedVersion; cleanup_pending = $false; cancellable = $false } | Out-Null
    $script:transactionCommitted = $true
    Clear-RecoveryRegistration

    $cleanupWarnings = @()
    try {
      Invoke-HwLifecycleFault -FaultAt $FaultAt -Point "cleanup_backup"
      Remove-TransactionTree -Path $backup
    } catch { $cleanupWarnings += $_.Exception.Message }
    try { Remove-TransactionTree -Path $failedRoot } catch { $cleanupWarnings += $_.Exception.Message }
    if ($cadenceLibraryLoaded -and -not [string]::IsNullOrWhiteSpace($cadenceSnapshot) -and (Test-Path -LiteralPath $cadenceSnapshot)) {
      try { Complete-HwAgentCadenceDeploymentTransaction -SnapshotRoot $cadenceSnapshot } catch { $cleanupWarnings += $_.Exception.Message }
    }
    if ($cleanupWarnings.Count -gt 0) {
      $warning = $cleanupWarnings -join " | "
      Write-Journal -Phase "completed" -Additional @{ cleanup_pending = $true; cleanup_warning = $warning }
      Set-HwLifecycleJobPhase -StateRoot $StateRoot -JobId $JobId -Phase "completed" -Progress 100 `
        -Message "新版本已生效，旧版本文件将在下次更新、修复安装或卸载时重试清理。" `
        -Additional @{ version = $ExpectedVersion; cleanup_pending = $true; cleanup_warning = $warning; cancellable = $false } | Out-Null
    }
  } catch {
    $message = $_.Exception.Message
    if ($transactionCommitted) { throw }
    $rollbackError = ""
    if ($commitStarted -or (Test-Path -LiteralPath $backup)) {
      try {
        Restore-PreviousRuntime
        Write-Journal -Phase "rolled_back" -Additional @{ error = $message }
        Clear-RecoveryRegistration
      } catch {
        $rollbackError = $_.Exception.Message
        try { Write-Journal -Phase "rollback_failed" -Additional @{ error = $message; rollback_error = $rollbackError } } catch {}
      }
    } else {
      try { Remove-TransactionTree -Path $candidate } catch {}
    }
    $rolledBack = [string]::IsNullOrWhiteSpace($rollbackError)
    $finalMessage = if ($rolledBack) {
      "更新失败，已恢复到更新前版本：$message"
    } else {
      "更新失败且自动回滚失败：$message / $rollbackError"
    }
    try {
      Set-HwLifecycleJobPhase -StateRoot $StateRoot -JobId $JobId -Phase "failed" -Progress 100 `
        -Message $finalMessage `
        -Additional @{ rolled_back = $rolledBack; rollback_error = $rollbackError; recovery_required = (-not $rolledBack); cancellable = $false } | Out-Null
    } catch {}
    throw
  }
}

$mutex = $null
try {
  $mutex = Enter-HwLifecycleMutex -TimeoutMilliseconds 0
  if ($Action -eq "Recover") { Invoke-Recovery } else { Invoke-Update }
} finally {
  if ($null -ne $mutex) { Exit-HwLifecycleMutex -Mutex $mutex }
}
