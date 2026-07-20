param(
  [Parameter(Mandatory=$true)][string]$InstallRoot,
  [Parameter(Mandatory=$true)][string]$StateRoot,
  [Parameter(Mandatory=$true)][string]$PayloadRoot,
  [ValidateSet("Install", "Upgrade", "Repair", "Reinstall")]
  [string]$Action = "Install",
  [string]$ProgressPath = "",
  [string]$FaultAt = "",
  [string]$CrashAt = "",
  [switch]$NoStart,
  [switch]$SkipCadence,
  [switch]$SkipRecoveryRegistration
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Contract.ps1")
. (Join-Path $PSScriptRoot "Runtime.ps1")

$InstallRoot = Get-HwV3FullPath -Path $InstallRoot -Label "InstallRoot"
$StateRoot = Get-HwV3FullPath -Path $StateRoot -Label "StateRoot"
$PayloadRoot = Get-HwV3FullPath -Path $PayloadRoot -Label "PayloadRoot"
$env:INSTA360_HW_STATE_ROOT = $StateRoot
if ($InstallRoot -ieq $StateRoot -or (Test-HwV3PathWithin -Path $StateRoot -Parent $InstallRoot) -or
    (Test-HwV3PathWithin -Path $InstallRoot -Parent $StateRoot)) {
  throw "Mutable lifecycle state must be outside the installation root."
}

$logPath = Join-Path $StateRoot "logs\install_latest.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $logPath) | Out-Null
if (Test-Path -LiteralPath $logPath -PathType Leaf) {
  $previousLog = Join-Path (Split-Path -Parent $logPath) `
    ("install_previous_" + (Get-Date -Format "yyyyMMdd_HHmmss_fff") + ".log")
  try { Copy-Item -LiteralPath $logPath -Destination $previousLog -Force }
  catch {}
}
Set-Content -LiteralPath $logPath -Value "" -Encoding UTF8
$script:stage = "initializing"

function Write-SetupLog {
  param([Parameter(Mandatory=$true)][string]$Message)
  try { Add-Content -LiteralPath $logPath -Encoding UTF8 -Value ((Get-Date).ToString("s") + " " + $Message) }
  catch {}
}

function Set-SetupProgress {
  param(
    [Parameter(Mandatory=$true)][string]$Stage,
    [Parameter(Mandatory=$true)][ValidateRange(0, 100)][int]$Percent,
    [Parameter(Mandatory=$true)][string]$Message
  )
  $script:stage = $Stage
  Write-SetupLog ("stage=" + $Stage + " progress=" + $Percent + " message=" + $Message)
  Write-Host ("__HWAGENT_INSTALL_PROGRESS__ {0} {1}" -f $Percent, $Stage)
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

function Split-SemanticVersion {
  param([Parameter(Mandatory=$true)][string]$Version)
  $valid = Assert-HwV3Version -Version $Version
  $withoutBuild = $valid.Split("+")[0]
  $dash = $withoutBuild.IndexOf("-")
  $core = if ($dash -lt 0) { $withoutBuild } else { $withoutBuild.Substring(0, $dash) }
  $pre = if ($dash -lt 0) { "" } else { $withoutBuild.Substring($dash + 1) }
  $numbers = $core.Split(".")
  return [pscustomobject]@{
    major = [int64]$numbers[0]
    minor = [int64]$numbers[1]
    patch = [int64]$numbers[2]
    prerelease = $pre
  }
}

function Compare-SemanticVersion {
  param([Parameter(Mandatory=$true)][string]$Left, [Parameter(Mandatory=$true)][string]$Right)
  $leftVersion = Split-SemanticVersion -Version $Left
  $rightVersion = Split-SemanticVersion -Version $Right
  foreach ($name in @("major", "minor", "patch")) {
    if ([int64]$leftVersion.$name -lt [int64]$rightVersion.$name) { return -1 }
    if ([int64]$leftVersion.$name -gt [int64]$rightVersion.$name) { return 1 }
  }
  $leftPre = [string]$leftVersion.prerelease
  $rightPre = [string]$rightVersion.prerelease
  if ([string]::IsNullOrWhiteSpace($leftPre) -and [string]::IsNullOrWhiteSpace($rightPre)) { return 0 }
  if ([string]::IsNullOrWhiteSpace($leftPre)) { return 1 }
  if ([string]::IsNullOrWhiteSpace($rightPre)) { return -1 }
  $leftParts = $leftPre.Split(".")
  $rightParts = $rightPre.Split(".")
  $count = [Math]::Max($leftParts.Count, $rightParts.Count)
  foreach ($index in 0..($count - 1)) {
    if ($index -ge $leftParts.Count) { return -1 }
    if ($index -ge $rightParts.Count) { return 1 }
    $leftNumber = 0L
    $rightNumber = 0L
    $leftNumeric = [int64]::TryParse($leftParts[$index], [ref]$leftNumber)
    $rightNumeric = [int64]::TryParse($rightParts[$index], [ref]$rightNumber)
    if ($leftNumeric -and $rightNumeric) {
      if ($leftNumber -lt $rightNumber) { return -1 }
      if ($leftNumber -gt $rightNumber) { return 1 }
    } elseif ($leftNumeric) { return -1 }
    elseif ($rightNumeric) { return 1 }
    else {
      $comparison = [string]::CompareOrdinal($leftParts[$index], $rightParts[$index])
      if ($comparison -lt 0) { return -1 }
      if ($comparison -gt 0) { return 1 }
    }
  }
  return 0
}

function Read-LegacyIdentity {
  $manifestPath = Join-Path $InstallRoot "install_manifest.json"
  if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { return $null }
  try {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([int]$manifest.schema -ne 2 -or [string]$manifest.product -ne "Insta360_HW" -or
        [string]$manifest.layout -ne "runtime-v2") { return $null }
    $version = Assert-HwV3Version -Version ([string]$manifest.version)
    $revision = Assert-HwV3Revision -Revision ([string]$manifest.revision)
    return [pscustomobject]@{ version = $version; revision = $revision }
  } catch { return $null }
}

function Read-RegisteredInstallVersion {
  $subKey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\{B7F3AC9E-2D5E-4A8C-9F6E-1A3D4E5F6B72}_is1"
  foreach ($view in @([Microsoft.Win32.RegistryView]::Registry64, [Microsoft.Win32.RegistryView]::Registry32)) {
    $baseKey = $null
    $installKey = $null
    try {
      $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
        [Microsoft.Win32.RegistryHive]::LocalMachine,
        $view
      )
      $installKey = $baseKey.OpenSubKey($subKey, $false)
      if ($null -eq $installKey) { continue }
      $registered = [string]$installKey.GetValue("DisplayVersion", "")
      if ([string]::IsNullOrWhiteSpace($registered)) { continue }
      try { return Assert-HwV3Version -Version $registered }
      catch { Write-SetupLog ("ignored invalid registered DisplayVersion: " + $registered) }
    } catch {
      Write-SetupLog ("could not read registered DisplayVersion: " + $_.Exception.Message)
    } finally {
      if ($null -ne $installKey) { $installKey.Dispose() }
      if ($null -ne $baseKey) { $baseKey.Dispose() }
    }
  }
  return ""
}

function Copy-TreeVerified {
  param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Destination,
    [Parameter(Mandatory=$true)][string]$ExpectedTreeSha256
  )
  if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $Destination | Out-Null
  $robocopy = Get-HwV3RobocopyPath
  & $robocopy $Source $Destination /MIR /COPY:DAT /DCOPY:DAT /R:2 /W:1 /XJ /NFL /NDL /NJH /NJS | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "Runtime copy failed with robocopy exit code $LASTEXITCODE." }
  if ((Get-HwV3TreeSha256 -Path $Destination) -cne $ExpectedTreeSha256) {
    throw "Copied runtime tree does not match the verified setup payload."
  }
}

function Assert-InstallDestinationCapacity {
  param(
    [Parameter(Mandatory=$true)][string]$Payload,
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$Revision
  )
  $runtimeId = Get-HwV3RuntimeId -Version $Version -Revision $Revision
  $probeJobId = "0" * 32
  $incomingRoot = Join-Path (Join-Path $InstallRoot "runtime") `
    ("." + $runtimeId + "." + $probeJobId + ".incoming")
  foreach ($item in Get-ChildItem -LiteralPath $Payload -Recurse -Force) {
    $relative = $item.FullName.Substring($Payload.Length).TrimStart([char[]]"\/")
    $destination = Join-Path $incomingRoot $relative
    $maximumSupportedPath = if ($item.PSIsContainer) { 248 } else { 260 }
    if ($destination.Length -ge $maximumSupportedPath) {
      throw "Selected installation directory is too long for this runtime. Choose a shorter installation path."
    }
  }
}

function Move-DirectoryWithRetry {
  param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Destination
  )
  foreach ($attempt in 0..7) {
    try {
      [System.IO.Directory]::Move($Source, $Destination)
      return
    } catch {
      if ($attempt -eq 7) { throw }
      Start-Sleep -Milliseconds (75 * ($attempt + 1))
    }
  }
}

function Install-StableLauncher {
  param([Parameter(Mandatory=$true)][string]$Source, [Parameter(Mandatory=$true)][string]$Target)
  $temporary = $Target + "." + $jobId + ".incoming"
  $replaceBackup = $Target + "." + $jobId + ".replace.bak"
  try {
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    if (Test-Path -LiteralPath $Target -PathType Leaf) {
      [System.IO.File]::Replace($temporary, $Target, $replaceBackup, $true)
    } else {
      [System.IO.File]::Move($temporary, $Target)
    }
  } finally {
    Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $replaceBackup -Force -ErrorAction SilentlyContinue
  }
}

function Migrate-LegacyUserState {
  if (-not $legacyInstall) { return }
  foreach ($relative in @("data", "plugins\user")) {
    $source = Join-Path $InstallRoot $relative
    if (-not (Test-Path -LiteralPath $source -PathType Container)) { continue }
    $sourceItem = Get-Item -LiteralPath $source -Force
    if (($sourceItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
    $destination = Join-Path $StateRoot $relative
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    $robocopy = Get-HwV3RobocopyPath
    & $robocopy $source $destination /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /XJ /XC /XN /XO /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Legacy user-state migration failed for $relative." }
  }
  $legacyConfig = Join-Path $InstallRoot "config\local.json"
  $currentConfig = Join-Path $StateRoot "config\local.json"
  if ((Test-Path -LiteralPath $legacyConfig -PathType Leaf) -and
      -not (Test-Path -LiteralPath $currentConfig -PathType Leaf)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $currentConfig) | Out-Null
    Copy-Item -LiteralPath $legacyConfig -Destination $currentConfig
  }
}

function Remove-LegacyRuntimeFiles {
  if (-not $legacyInstall) { return }
  foreach ($relative in @("app", "cadence", "scripts", "plugins\bundled", "runtime\python")) {
    $path = Join-Path $InstallRoot $relative
    try {
      if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
    } catch { Write-SetupLog ("legacy cleanup deferred for " + $relative + ": " + $_.Exception.Message) }
  }
  foreach ($relative in @("VERSION", "REVISION", "install_manifest.json", "launch_tool_suite.ps1")) {
    try { Remove-Item -LiteralPath (Join-Path $InstallRoot $relative) -Force -ErrorAction Stop }
    catch [System.Management.Automation.ItemNotFoundException] {}
    catch { Write-SetupLog ("legacy cleanup deferred for " + $relative + ": " + $_.Exception.Message) }
  }
}

$setupRecoveryRan = $false
$pendingV3Setup = Join-Path $StateRoot "lifecycle\v3\setup"
if ((Test-Path -LiteralPath $pendingV3Setup -PathType Container) -and
    @(Get-ChildItem -LiteralPath $pendingV3Setup -Directory -Force -ErrorAction SilentlyContinue).Count -gt 0) {
  Set-SetupProgress -Stage "recovering_interrupted_setup" -Percent 1 `
    -Message "Recovering an interrupted setup transaction before setup continues."
  & (Join-Path $PSScriptRoot "SetupRecover.ps1") -InstallRoot $InstallRoot -StateRoot $StateRoot `
    -NoRestart -SkipCadence:$SkipCadence
  $setupRecoveryRan = $true
}

$legacySetupTransaction = Join-Path $StateRoot "lifecycle\setup\active"
if (Test-Path -LiteralPath $legacySetupTransaction -PathType Container) {
  Set-SetupProgress -Stage "recovering_legacy_setup" -Percent 1 `
    -Message "Recovering an interrupted legacy setup before setup continues."
  Restore-HwV2InterruptedSetup -InstallRoot $InstallRoot -StateRoot $StateRoot `
    -SkipRecoveryRegistration:$SkipRecoveryRegistration | Out-Null
}

$legacyUpdateTransactions = Join-Path $StateRoot "lifecycle\transactions"
if ((Test-Path -LiteralPath $legacyUpdateTransactions -PathType Container) -and
    @(Get-ChildItem -LiteralPath $legacyUpdateTransactions -Directory -Force -ErrorAction SilentlyContinue).Count -gt 0) {
  Set-SetupProgress -Stage "recovering_legacy_update" -Percent 2 `
    -Message "Recovering an interrupted legacy update before setup continues."
  Restore-HwV2InterruptedUpdates -InstallRoot $InstallRoot -StateRoot $StateRoot `
    -WorkerPath (Join-Path $PayloadRoot "scripts\lifecycle\Worker.ps1") -NoRestart `
    -SkipCadence:$SkipCadence -SkipRecoveryRegistration:$SkipRecoveryRegistration | Out-Null
}

if (Test-Path -LiteralPath (Join-Path $InstallRoot ".recovery") -PathType Container) {
  Set-SetupProgress -Stage "recovering_interrupted_operation" -Percent 1 `
    -Message "Recovering an interrupted runtime switch before setup continues."
  $recoverArguments = @{
    InstallRoot = $InstallRoot
    StateRoot = $StateRoot
    NoRestart = $true
    SkipCadence = [bool]$SkipCadence
  }
  & (Join-Path $PSScriptRoot "Recover.ps1") @recoverArguments
}

Set-SetupProgress -Stage "validating_payload" -Percent 3 -Message "Validating the setup runtime payload."
$payloadManifest = Read-HwV3Json -Path (Join-Path $PayloadRoot "install_manifest.json") -Required
$payloadVersion = Assert-HwV3Version -Version ([string]$payloadManifest.version)
$payloadRevision = Assert-HwV3Revision -Revision ([string]$payloadManifest.revision)
Assert-HwV3RuntimeTree -Path $PayloadRoot -ExpectedVersion $payloadVersion -ExpectedRevision $payloadRevision `
  -RequireCadence:(-not $SkipCadence) | Out-Null
$payloadLauncher = Join-Path $PayloadRoot "Insta360_HW.exe"
if (-not (Test-Path -LiteralPath $payloadLauncher -PathType Leaf)) { throw "Setup payload has no stable launcher." }
$payloadTreeSha256 = Get-HwV3TreeSha256 -Path $PayloadRoot
Assert-InstallDestinationCapacity -Payload $PayloadRoot -Version $payloadVersion -Revision $payloadRevision

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
New-Item -ItemType Directory -Force -Path $StateRoot | Out-Null
$jobId = [guid]::NewGuid().ToString("N")
$transactionRoot = Join-Path $StateRoot ("lifecycle\v3\setup\" + $jobId)
New-Item -ItemType Directory -Force -Path $transactionRoot | Out-Null
$journalPath = Join-Path $transactionRoot "journal.json"
$installationPath = Join-Path $InstallRoot "installation.json"
$launcherPath = Join-Path $InstallRoot "Insta360_HW.exe"
$launcherBackup = Join-Path $transactionRoot "launcher-before.exe"
$runtimeParent = Join-Path $InstallRoot "runtime"
New-Item -ItemType Directory -Force -Path $runtimeParent | Out-Null
$newRelative = Get-HwV3RuntimeRelativePath -Version $payloadVersion -Revision $payloadRevision
$newRuntime = Resolve-HwV3RuntimePointer -InstallRoot $InstallRoot -RelativePath $newRelative -Field "setup runtime"
$incoming = Join-Path $runtimeParent ("." + (Get-HwV3RuntimeId -Version $payloadVersion -Revision $payloadRevision) + "." + $jobId + ".incoming")
$sameRuntimeBackup = $newRuntime + "." + $jobId + ".backup"
$metadata = $null
$originalMetadata = $null
$oldRuntime = ""
$oldRelative = ""
$oldVersion = ""
$oldManifestMissing = $false
$oldRuntimeExisted = $false
$legacyInstall = $false
$pointerCommitted = $false
$pointerCommitIntent = $false
$launcherReplaced = $false
$newRuntimeCreated = $false
$sameRuntimeMoved = $false
$sameRuntimeMoveIntent = $false
$launcherExisted = Test-Path -LiteralPath $launcherPath -PathType Leaf
$cadenceSnapshot = ""
$oldServiceWasHealthy = $false
$transactionCommitted = $false
$mutex = $null
$failed = $false

function Write-SetupTransaction {
  param(
    [Parameter(Mandatory=$true)][string]$Phase,
    [ValidateSet("pending", "completed")][string]$Outcome = "pending"
  )
  Write-HwV3JsonAtomic -Path $journalPath -Value ([ordered]@{
    schema = 3
    product = "Insta360_HW"
    kind = "setup"
    job_id = $jobId
    phase = $Phase
    outcome = $Outcome
    install_root = $InstallRoot
    state_root = $StateRoot
    old_relative = $oldRelative
    new_relative = $newRelative
    incoming = $incoming
    same_runtime_backup = $sameRuntimeBackup
    launcher_backup = $launcherBackup
    launcher_existed = [bool]$launcherExisted
    original_metadata = $originalMetadata
    new_runtime_created = [bool]$newRuntimeCreated
    same_runtime_moved = [bool]$sameRuntimeMoved
    same_runtime_move_intent = [bool]$sameRuntimeMoveIntent
    launcher_replaced = [bool]$launcherReplaced
    pointer_committed = [bool]$pointerCommitted
    pointer_commit_intent = [bool]$pointerCommitIntent
    old_service_was_healthy = [bool]$oldServiceWasHealthy
    cadence_snapshot = $cadenceSnapshot
    updated_at = (Get-Date).ToUniversalTime().ToString("o")
  })
}

function Invoke-SetupCrash {
  param([Parameter(Mandatory=$true)][string]$Point)
  if (-not [string]::IsNullOrWhiteSpace($CrashAt) -and $CrashAt -ceq $Point) {
    [System.Environment]::Exit(97)
  }
}

Write-SetupTransaction -Phase "initialized"

try {
  Set-SetupProgress -Stage "acquiring_lifecycle" -Percent 7 -Message "Waiting for other lifecycle operations."
  $mutex = Enter-HwV3LifecycleMutex -TimeoutMilliseconds 30000
  if (Test-Path -LiteralPath $installationPath -PathType Leaf) {
    $metadata = Read-HwV3Installation -InstallRoot $InstallRoot
    $originalMetadata = $metadata | ConvertTo-Json -Depth 24 | ConvertFrom-Json
    $oldRelative = [string]$metadata.active_runtime
    $oldRuntime = Resolve-HwV3RuntimePointer -InstallRoot $InstallRoot -RelativePath $oldRelative -Field "active_runtime"
    $oldRuntimeExisted = Test-Path -LiteralPath $oldRuntime -PathType Container
    try {
      $oldManifest = Read-HwV3Json -Path (Join-Path $oldRuntime "install_manifest.json") -Required
      $oldVersion = Assert-HwV3Version -Version ([string]$oldManifest.version)
    } catch {
      $oldManifestMissing = $true
      Write-SetupLog ("active runtime manifest is unavailable; maintenance may rebuild it: " + $_.Exception.Message)
      $activeVersionProperty = $metadata.PSObject.Properties["active_version"]
      if ($null -ne $activeVersionProperty -and
          -not [string]::IsNullOrWhiteSpace([string]$activeVersionProperty.Value)) {
        try { $oldVersion = Assert-HwV3Version -Version ([string]$activeVersionProperty.Value) }
        catch { Write-SetupLog ("ignored invalid installation active_version: " + [string]$activeVersionProperty.Value) }
      }
      if ([string]::IsNullOrWhiteSpace($oldVersion)) {
        $oldVersion = Read-RegisteredInstallVersion
      }
    }
  } else {
    $legacy = Read-LegacyIdentity
    if ($null -ne $legacy) {
      $legacyInstall = $true
      $oldRuntime = $InstallRoot
      $oldVersion = [string]$legacy.version
    }
  }

  $hasExisting = ($null -ne $metadata) -or $legacyInstall
  $hasKnownVersion = -not [string]::IsNullOrWhiteSpace($oldVersion)
  $versionComparison = if ($hasKnownVersion) { Compare-SemanticVersion -Left $payloadVersion -Right $oldVersion } else { 1 }
  if ($setupRecoveryRan -and $Action -in @("Repair", "Reinstall") -and $hasKnownVersion -and
      $versionComparison -gt 0) {
    Write-SetupLog ("interrupted setup recovery changed action from " + $Action + " to Upgrade")
    $Action = "Upgrade"
  }
  if ($Action -eq "Install" -and $hasExisting) { throw "Install action cannot replace an existing installation." }
  if ($Action -eq "Upgrade" -and $hasKnownVersion -and $versionComparison -lt 0) {
    throw "Implicit downgrade is refused: installed=$oldVersion setup=$payloadVersion"
  }
  if ($Action -eq "Upgrade" -and $hasKnownVersion -and $versionComparison -eq 0) {
    throw "Upgrade action requires a newer version; use Repair or Reinstall for the same version."
  }
  if ($Action -in @("Repair", "Reinstall") -and $oldManifestMissing) {
    $Action = "Reinstall"
    Write-SetupLog ("rebuilding missing active runtime with action " + $Action)
  } elseif ($Action -in @("Repair", "Reinstall") -and $hasKnownVersion -and $versionComparison -ne 0) {
    throw "$Action requires the setup package to match the installed version."
  }

  Write-SetupTransaction -Phase "prepared"

  Set-SetupProgress -Stage "migrating_user_state" -Percent 15 -Message "Preserving user data outside the program directory."
  Migrate-LegacyUserState
  if ($launcherExisted) { Copy-Item -LiteralPath $launcherPath -Destination $launcherBackup -Force }
  Write-SetupTransaction -Phase "snapshotted"

  Set-SetupProgress -Stage "copying_runtime" -Percent 25 -Message "Copying the verified versioned runtime."
  Copy-TreeVerified -Source $PayloadRoot -Destination $incoming -ExpectedTreeSha256 $payloadTreeSha256
  Assert-HwV3RuntimeTree -Path $incoming -ExpectedVersion $payloadVersion -ExpectedRevision $payloadRevision `
    -RequireCadence:(-not $SkipCadence) | Out-Null
  Write-SetupTransaction -Phase "payload_staged"

  if (Test-Path -LiteralPath $newRuntime -PathType Container) {
    $reuseHealthyRuntime = $false
    if ($Action -eq "Repair") {
      try {
        Assert-HwV3RuntimeTree -Path $newRuntime -ExpectedVersion $payloadVersion -ExpectedRevision $payloadRevision `
          -RequireCadence:(-not $SkipCadence) | Out-Null
        $reuseHealthyRuntime = (Get-HwV3TreeSha256 -Path $newRuntime) -ceq $payloadTreeSha256
      } catch { $reuseHealthyRuntime = $false }
    }
    if ($reuseHealthyRuntime) {
      Remove-Item -LiteralPath $incoming -Recurse -Force
      Write-SetupLog "repair reused the already verified runtime tree"
    } elseif ($Action -in @("Repair", "Reinstall")) {
      if (-not [string]::IsNullOrWhiteSpace($oldRuntime)) {
        $oldServiceWasHealthy = Test-HwV3Service -RuntimeRoot $oldRuntime -StateRoot $StateRoot
        Stop-HwV3Service -RuntimeRoot $oldRuntime -StateRoot $StateRoot
      }
      if (Test-Path -LiteralPath $sameRuntimeBackup) { Remove-Item -LiteralPath $sameRuntimeBackup -Recurse -Force }
      $sameRuntimeMoveIntent = $true
      Write-SetupTransaction -Phase "same_runtime_move_intent"
      Move-DirectoryWithRetry -Source $newRuntime -Destination $sameRuntimeBackup
      Invoke-SetupCrash -Point "same_runtime_moved_unjournaled"
      $sameRuntimeMoved = $true
      Write-SetupTransaction -Phase "same_runtime_moved"
      Invoke-SetupCrash -Point "same_runtime_moved"
      Move-DirectoryWithRetry -Source $incoming -Destination $newRuntime
      $newRuntimeCreated = $true
    } else {
      Assert-HwV3RuntimeTree -Path $newRuntime -ExpectedVersion $payloadVersion -ExpectedRevision $payloadRevision `
        -RequireCadence:(-not $SkipCadence) | Out-Null
      if ((Get-HwV3TreeSha256 -Path $newRuntime) -cne $payloadTreeSha256) {
        throw "An existing runtime has the requested identity but different content."
      }
      Remove-Item -LiteralPath $incoming -Recurse -Force
    }
  } else {
    Move-DirectoryWithRetry -Source $incoming -Destination $newRuntime
    $newRuntimeCreated = $true
  }
  Write-SetupTransaction -Phase "runtime_ready"
  Invoke-HwV3Fault -FaultAt $FaultAt -Point "runtime_ready"
  Invoke-SetupCrash -Point "runtime_ready"

  if (-not [string]::IsNullOrWhiteSpace($oldRuntime) -and -not $sameRuntimeMoved) {
    $oldServiceWasHealthy = Test-HwV3Service -RuntimeRoot $oldRuntime -StateRoot $StateRoot
    Stop-HwV3Service -RuntimeRoot $oldRuntime -StateRoot $StateRoot
  }
  Write-SetupTransaction -Phase "service_stopped"

  if (-not $SkipCadence) {
    Set-SetupProgress -Stage "snapshotting_integration" -Percent 55 -Message "Saving the current Cadence integration."
    . (Join-Path $newRuntime "scripts\lib\Paths.ps1")
    . (Join-Path $newRuntime "scripts\lib\Cadence.ps1")
    . (Join-Path $newRuntime "scripts\lib\TclScripts.ps1")
    $cadenceDirs = @(Get-HwAgentManagedCadenceAutoLoadDirs)
    $cadenceSnapshot = Start-HwAgentCadenceDeploymentTransaction -AutoLoadDirs $cadenceDirs
    Write-SetupTransaction -Phase "integration_snapshotted"
  }

  Set-SetupProgress -Stage "activating_runtime" -Percent 65 -Message "Activating the verified runtime pointer."
  Install-StableLauncher -Source (Join-Path $newRuntime "Insta360_HW.exe") -Target $launcherPath
  $launcherReplaced = $true
  Write-SetupTransaction -Phase "launcher_replaced"
  Invoke-SetupCrash -Point "launcher_replaced"
  $nextMetadata = [ordered]@{
    schema_version = 3
    product = "Insta360_HW"
    layout = "versioned-runtime-v3"
    active_runtime = $newRelative
    active_version = $payloadVersion
    previous_runtime = if ($null -eq $metadata) {
      ""
    } elseif ($oldRelative -ceq $newRelative) {
      [string]$metadata.previous_runtime
    } else {
      $oldRelative
    }
    generation = if ($null -eq $metadata) { 1 } else { [int]$metadata.generation + 1 }
    updated_at = (Get-Date).ToUniversalTime().ToString("o")
  }
  $pointerCommitIntent = $true
  Write-SetupTransaction -Phase "pointer_commit_intent"
  Write-HwV3JsonAtomic -Path $installationPath -Value $nextMetadata
  Invoke-SetupCrash -Point "pointer_written_unjournaled"
  $pointerCommitted = $true
  Write-SetupTransaction -Phase "pointer_committed"
  Invoke-HwV3Fault -FaultAt $FaultAt -Point "pointer_committed"
  Invoke-SetupCrash -Point "pointer_committed"

  if (-not $SkipCadence) {
    Set-SetupProgress -Stage "deploying_cadence" -Percent 78 -Message "Deploying the Cadence integration."
    $python = Find-Python -Root $newRuntime
    $loaders = @(Install-CadenceLoader -ToolRoot $newRuntime -PythonPath $python -AutoLoadDirs $cadenceDirs `
      -PluginStatePath (Join-Path $StateRoot "config\plugin_state.json"))
    Update-HwAgentCadenceOwnershipManifest -LoaderPaths $loaders | Out-Null
    Set-HwAgentCadenceIntegrationState -Enabled:$true -LoaderPaths $cadenceDirs | Out-Null
    Write-SetupTransaction -Phase "integration_deployed"
    Invoke-HwV3Fault -FaultAt $FaultAt -Point "cadence_deployed"
    Invoke-SetupCrash -Point "cadence_deployed"
  }

  if (-not $NoStart) {
    Set-SetupProgress -Stage "verifying_service" -Percent 90 -Message "Starting and verifying the platform backend."
    Start-HwV3Service -RuntimeRoot $newRuntime -StateRoot $StateRoot
  }
  Invoke-HwV3Fault -FaultAt $FaultAt -Point "runtime_verified"
  Invoke-SetupCrash -Point "runtime_verified"

  $transactionCommitted = $true
  Write-SetupTransaction -Phase "runtime_verified" -Outcome "completed"
  if (-not [string]::IsNullOrWhiteSpace($cadenceSnapshot)) {
    try { Complete-HwAgentCadenceDeploymentTransaction -SnapshotRoot $cadenceSnapshot }
    catch { Write-SetupLog ("Cadence snapshot cleanup deferred: " + $_.Exception.Message) }
    $cadenceSnapshot = ""
  }
  if ($sameRuntimeMoved -and (Test-Path -LiteralPath $sameRuntimeBackup)) {
    try { Remove-Item -LiteralPath $sameRuntimeBackup -Recurse -Force }
    catch { Write-SetupLog ("reinstall backup cleanup deferred: " + $_.Exception.Message) }
    $sameRuntimeMoved = $false
  }
  Remove-LegacyRuntimeFiles
  try { Remove-Item -LiteralPath $transactionRoot -Recurse -Force -ErrorAction Stop }
  catch { Write-SetupLog ("setup transaction cleanup deferred: " + $_.Exception.Message) }
  Set-SetupProgress -Stage "completed" -Percent 100 -Message "Installation completed and passed verification."
  Write-Host "__HWAGENT_INSTALL_DONE__"
  Write-SetupLog "install completed"
} catch {
  $failure = $_
  Write-SetupLog ("FAILED stage=" + $script:stage + " " + $failure.Exception.ToString())
  if ($transactionCommitted) {
    Write-SetupLog "post-commit cleanup failed; preserving the verified active runtime"
  } else {
    $failed = $true
  try {
    if ($pointerCommitted -and -not $NoStart) { Stop-HwV3Service -RuntimeRoot $newRuntime -StateRoot $StateRoot }
    if ($null -ne $originalMetadata) {
      Write-HwV3JsonAtomic -Path $installationPath -Value $originalMetadata
    } else {
      Remove-Item -LiteralPath $installationPath -Force -ErrorAction SilentlyContinue
    }
    if ($launcherExisted -and (Test-Path -LiteralPath $launcherBackup -PathType Leaf)) {
      Install-StableLauncher -Source $launcherBackup -Target $launcherPath
    } elseif (-not $launcherExisted) {
      Remove-Item -LiteralPath $launcherPath -Force -ErrorAction SilentlyContinue
    }
    if (-not [string]::IsNullOrWhiteSpace($cadenceSnapshot) -and (Test-Path -LiteralPath $cadenceSnapshot)) {
      Restore-HwAgentCadenceDeploymentTransaction -SnapshotRoot $cadenceSnapshot
      Complete-HwAgentCadenceDeploymentTransaction -SnapshotRoot $cadenceSnapshot
      $cadenceSnapshot = ""
    }
    if ($sameRuntimeMoved -and (Test-Path -LiteralPath $sameRuntimeBackup -PathType Container)) {
      if (Test-Path -LiteralPath $newRuntime) { Remove-Item -LiteralPath $newRuntime -Recurse -Force }
      Move-DirectoryWithRetry -Source $sameRuntimeBackup -Destination $newRuntime
      $sameRuntimeMoved = $false
      $newRuntimeCreated = $false
    } elseif ($newRuntimeCreated -and (($newRelative -cne $oldRelative) -or (-not $oldRuntimeExisted)) -and
        (Test-Path -LiteralPath $newRuntime)) {
      Remove-Item -LiteralPath $newRuntime -Recurse -Force
      $newRuntimeCreated = $false
    }
    if ($oldServiceWasHealthy -and -not $NoStart -and -not [string]::IsNullOrWhiteSpace($oldRuntime)) {
      Start-HwV3Service -RuntimeRoot $oldRuntime -StateRoot $StateRoot
    }
    Remove-Item -LiteralPath $transactionRoot -Recurse -Force -ErrorAction SilentlyContinue
  } catch {
    Write-SetupLog ("rollback failed: " + $_.Exception.ToString())
  }
  [Console]::Error.WriteLine("Install failed at stage {0}: {1}", $script:stage, $failure.Exception.Message)
  }
} finally {
  Remove-Item -LiteralPath $incoming -Recurse -Force -ErrorAction SilentlyContinue
  if ($null -ne $mutex) { Exit-HwV3LifecycleMutex -Mutex $mutex }
}

if ($failed) { exit 1 }
exit 0
