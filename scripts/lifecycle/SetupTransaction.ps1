[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [ValidateSet("Begin", "PrepareReplace", "Commit", "Rollback", "Recover")]
  [string]$Action,
  [Parameter(Mandatory=$true)][string]$InstallRoot,
  [Parameter(Mandatory=$true)][string]$StateRoot,
  [switch]$SkipRunOnce
)

$ErrorActionPreference = "Stop"
$Product = "Insta360_HW"
$Schema = 1
$MutexName = "Global\Insta360_HW_SetupTransaction_V1"
$RunOnceName = "Insta360_HW_SetupRecovery"

function Get-NormalizedPath {
  param([Parameter(Mandatory=$true)][string]$Path)
  return [System.IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Path)).TrimEnd('\')
}

function Assert-SafeRoots {
  param([string]$Runtime, [string]$State)
  $runtimeRoot = [System.IO.Path]::GetPathRoot($Runtime).TrimEnd('\')
  $stateRoot = [System.IO.Path]::GetPathRoot($State).TrimEnd('\')
  if ([string]::IsNullOrWhiteSpace($Runtime) -or $Runtime.TrimEnd('\') -eq $runtimeRoot) {
    throw "Unsafe setup install root: $Runtime"
  }
  if ([string]::IsNullOrWhiteSpace($State) -or $State.TrimEnd('\') -eq $stateRoot) {
    throw "Unsafe setup state root: $State"
  }
  if ($Runtime.Equals($State, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Setup install root and state root must be different."
  }
  if ($State.StartsWith($Runtime + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Setup state root must not be inside the install root."
  }
}

$InstallRoot = Get-NormalizedPath -Path $InstallRoot
$StateRoot = Get-NormalizedPath -Path $StateRoot
Assert-SafeRoots -Runtime $InstallRoot -State $StateRoot
$SetupRoot = Join-Path $StateRoot "lifecycle\setup"
$TransactionRoot = Join-Path $SetupRoot "active"
$BackupRoot = Join-Path $TransactionRoot "backup"
$JournalPath = Join-Path $TransactionRoot "journal.json"
$RecoveryScript = Join-Path $TransactionRoot "SetupTransaction.ps1"

function Write-AtomicJson {
  param([string]$Path, [hashtable]$Value)
  $parent = Split-Path -Parent $Path
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  $temp = $Path + "." + [guid]::NewGuid().ToString("N") + ".tmp"
  try {
    $Value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temp -Encoding UTF8
    Move-Item -LiteralPath $temp -Destination $Path -Force
  } finally {
    Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
  }
}

function Read-Journal {
  if (-not (Test-Path -LiteralPath $JournalPath -PathType Leaf)) { return $null }
  $journal = Get-Content -LiteralPath $JournalPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($journal.schema -ne $Schema -or $journal.product -ne $Product) {
    throw "Setup transaction identity is invalid."
  }
  if ((Get-NormalizedPath -Path ([string]$journal.install_root)) -ne $InstallRoot) {
    throw "Setup transaction install root mismatch."
  }
  if ((Get-NormalizedPath -Path ([string]$journal.state_root)) -ne $StateRoot) {
    throw "Setup transaction state root mismatch."
  }
  return $journal
}

function New-JournalValue {
  param([string]$Phase, [bool]$HadExistingRuntime)
  return @{
    schema = $Schema
    product = $Product
    phase = $Phase
    install_root = $InstallRoot
    state_root = $StateRoot
    backup_root = $BackupRoot
    had_existing_runtime = $HadExistingRuntime
    updated_at = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
  }
}

function Invoke-RobocopyTree {
  param([string]$Source, [string]$Destination, [switch]$ExcludeUninstaller)
  New-Item -ItemType Directory -Force -Path $Destination | Out-Null
  $arguments = @(
    $Source, $Destination, "/E", "/COPY:DAT", "/DCOPY:DAT", "/XJ",
    "/R:2", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP"
  )
  if ($ExcludeUninstaller) {
    $arguments += @("/XF", "unins000.exe", "unins000.dat", "unins000.msg")
  }
  & (Join-Path $env:SystemRoot "System32\robocopy.exe") @arguments | Out-Null
  $code = $LASTEXITCODE
  if ($code -ge 8) { throw "Runtime backup copy failed with robocopy exit code $code." }
}

function Test-FilesEqual {
  param([Parameter(Mandatory=$true)][string]$Left, [Parameter(Mandatory=$true)][string]$Right)
  $leftItem = Get-Item -LiteralPath $Left -Force -ErrorAction Stop
  $rightItem = Get-Item -LiteralPath $Right -Force -ErrorAction Stop
  if ($leftItem.Length -ne $rightItem.Length) { return $false }
  $leftHash = (Get-FileHash -LiteralPath $Left -Algorithm SHA256).Hash
  $rightHash = (Get-FileHash -LiteralPath $Right -Algorithm SHA256).Hash
  return $leftHash -eq $rightHash
}

function Copy-LegacyFile {
  param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Destination,
    [Parameter(Mandatory=$true)][string]$ConflictPath
  )
  $destinationParent = Split-Path -Parent $Destination
  New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
  if (-not (Test-Path -LiteralPath $Destination)) {
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
    return
  }
  if ((Test-Path -LiteralPath $Destination -PathType Leaf) -and (Test-FilesEqual -Left $Source -Right $Destination)) {
    return
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ConflictPath) | Out-Null
  Copy-Item -LiteralPath $Source -Destination $ConflictPath -Force
}

function Merge-LegacyTree {
  param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Destination,
    [Parameter(Mandatory=$true)][string]$ConflictRoot,
    [Parameter(Mandatory=$true)][string]$Label
  )
  if (-not (Test-Path -LiteralPath $Source -PathType Container)) { return }
  $sourcePrefix = $Source.TrimEnd('\') + '\'
  foreach ($file in Get-ChildItem -LiteralPath $Source -Recurse -File -Force -ErrorAction Stop) {
    $relative = $file.FullName.Substring($sourcePrefix.Length)
    Copy-LegacyFile -Source $file.FullName `
      -Destination (Join-Path $Destination $relative) `
      -ConflictPath (Join-Path (Join-Path $ConflictRoot $Label) $relative)
  }
}

function Migrate-LegacyMutableState {
  if (-not (Test-Path -LiteralPath $BackupRoot -PathType Container)) { return }
  $conflictRoot = Join-Path $StateRoot ("recovered\setup-legacy-" + [DateTime]::UtcNow.ToString("yyyyMMdd_HHmmssfff"))
  $mappings = @(
    @("data", "data", "data"),
    @("uploads", "data\uploads", "top-level-uploads"),
    @("outputs", "data\outputs", "top-level-outputs"),
    @("history", "data\history", "top-level-history"),
    @("plugins\user", "plugins\user", "plugins-user")
  )
  foreach ($mapping in $mappings) {
    Merge-LegacyTree `
      -Source (Join-Path $BackupRoot $mapping[0]) `
      -Destination (Join-Path $StateRoot $mapping[1]) `
      -ConflictRoot $conflictRoot `
      -Label $mapping[2]
  }

  $legacyConfig = Join-Path $BackupRoot "config\local.json"
  if (Test-Path -LiteralPath $legacyConfig -PathType Leaf) {
    Copy-LegacyFile -Source $legacyConfig `
      -Destination (Join-Path $StateRoot "config\local.json") `
      -ConflictPath (Join-Path $conflictRoot "config\local.json")
  }
}

function Remove-InstallChildren {
  if (-not (Test-Path -LiteralPath $InstallRoot -PathType Container)) { return }
  foreach ($item in Get-ChildItem -LiteralPath $InstallRoot -Force -ErrorAction Stop) {
    if ($item.Name -in @("unins000.exe", "unins000.dat", "unins000.msg")) { continue }
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
      if ($item.PSIsContainer) {
        [IO.Directory]::Delete($item.FullName)
      } else {
        [IO.File]::Delete($item.FullName)
      }
      continue
    }
    Remove-Item -LiteralPath $item.FullName -Recurse -Force -ErrorAction Stop
  }
}

function Stop-OwnedService {
  $servicePath = Join-Path $StateRoot "runtime\service.json"
  if (-not (Test-Path -LiteralPath $servicePath -PathType Leaf)) { return }
  try {
    $service = Get-Content -LiteralPath $servicePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($service.schema -ne 2) { return }
    if ((Get-NormalizedPath -Path ([string]$service.root)) -ne $InstallRoot) { return }
    $pidValue = [int]$service.pid
    $expectedExe = Get-NormalizedPath -Path ([string]$service.executable)
    if (-not $expectedExe.StartsWith($InstallRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { return }
    $process = Get-Process -Id $pidValue -ErrorAction Stop
    $actualExe = Get-NormalizedPath -Path $process.Path
    if ($actualExe.Equals($expectedExe, [StringComparison]::OrdinalIgnoreCase)) {
      Stop-Process -Id $pidValue -Force -ErrorAction Stop
      try { Wait-Process -Id $pidValue -Timeout 10 -ErrorAction SilentlyContinue } catch {}
    }
  } catch {}
}

function Set-RecoveryRunOnce {
  if ($SkipRunOnce) { return }
  New-Item -ItemType Directory -Force -Path $TransactionRoot | Out-Null
  Copy-Item -LiteralPath $PSCommandPath -Destination $RecoveryScript -Force
  $command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $RecoveryScript +
    '" -Action Recover -InstallRoot "' + $InstallRoot + '" -StateRoot "' + $StateRoot + '"'
  $key = "HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce"
  New-Item -Path $key -Force | Out-Null
  New-ItemProperty -Path $key -Name $RunOnceName -Value $command -PropertyType String -Force | Out-Null
}

function Remove-RecoveryRunOnce {
  if ($SkipRunOnce) { return }
  $key = "HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce"
  try {
    $value = [string](Get-ItemPropertyValue -Path $key -Name $RunOnceName -ErrorAction Stop)
    if ($value.IndexOf($RecoveryScript, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
      Remove-ItemProperty -Path $key -Name $RunOnceName -Force -ErrorAction Stop
    }
  } catch {}
}

function Remove-TransactionTree {
  if (Test-Path -LiteralPath $TransactionRoot) {
    Remove-Item -LiteralPath $TransactionRoot -Recurse -Force -ErrorAction Stop
  }
}

function Invoke-Rollback {
  $journal = Read-Journal
  if ($null -eq $journal) {
    Remove-RecoveryRunOnce
    Remove-TransactionTree
    return
  }
  if ([string]$journal.phase -eq "backing_up") {
    Remove-RecoveryRunOnce
    Remove-TransactionTree
    return
  }
  if ([string]$journal.phase -notin @("prepared", "replacing", "rolling_back")) {
    if ([string]$journal.phase -in @("committed", "rolled_back")) {
      Remove-RecoveryRunOnce
      Remove-TransactionTree
      return
    }
    throw "Unsupported setup transaction phase: $($journal.phase)"
  }

  Write-AtomicJson -Path $JournalPath -Value (New-JournalValue -Phase "rolling_back" -HadExistingRuntime ([bool]$journal.had_existing_runtime))
  Stop-OwnedService
  Remove-InstallChildren
  if ([bool]$journal.had_existing_runtime) {
    if (-not (Test-Path -LiteralPath $BackupRoot -PathType Container)) {
      throw "Setup rollback backup is missing."
    }
    Invoke-RobocopyTree -Source $BackupRoot -Destination $InstallRoot
  }
  Write-AtomicJson -Path $JournalPath -Value (New-JournalValue -Phase "rolled_back" -HadExistingRuntime ([bool]$journal.had_existing_runtime))
  Remove-RecoveryRunOnce
  Remove-TransactionTree
}

function Invoke-Recover {
  if (-not (Test-Path -LiteralPath $TransactionRoot -PathType Container)) { return }
  $journal = Read-Journal
  if ($null -eq $journal) {
    Remove-TransactionTree
    return
  }
  if ([string]$journal.phase -in @("prepared", "rolling_back")) {
    Invoke-Rollback
    return
  }
  Remove-RecoveryRunOnce
  Remove-TransactionTree
}

function Invoke-Begin {
  Invoke-Recover
  New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
  $existing = @()
  if (Test-Path -LiteralPath $InstallRoot -PathType Container) {
    $existing = @(Get-ChildItem -LiteralPath $InstallRoot -Force | Where-Object {
      $_.Name -notin @("unins000.exe", "unins000.dat", "unins000.msg")
    })
  }
  $hadExistingRuntime = $existing.Count -gt 0
  Write-AtomicJson -Path $JournalPath -Value (New-JournalValue -Phase "backing_up" -HadExistingRuntime $hadExistingRuntime)
  if ($hadExistingRuntime) {
    Invoke-RobocopyTree -Source $InstallRoot -Destination $BackupRoot -ExcludeUninstaller
  }
  Write-AtomicJson -Path $JournalPath -Value (New-JournalValue -Phase "prepared" -HadExistingRuntime $hadExistingRuntime)
  Set-RecoveryRunOnce
}

function Invoke-PrepareReplace {
  $journal = Read-Journal
  if ($null -eq $journal) { throw "Setup transaction is missing before runtime replacement." }
  if ([string]$journal.phase -eq "replacing") { return }
  if ([string]$journal.phase -ne "prepared") {
    throw "Setup transaction is not prepared for runtime replacement."
  }
  Write-AtomicJson -Path $JournalPath -Value (New-JournalValue -Phase "replacing" -HadExistingRuntime ([bool]$journal.had_existing_runtime))
  Stop-OwnedService
  Migrate-LegacyMutableState
  Remove-InstallChildren
}

function Invoke-Commit {
  $journal = Read-Journal
  if ($null -eq $journal) { throw "Setup transaction is missing during commit." }
  if ([string]$journal.phase -ne "replacing") { throw "Setup transaction has not replaced the runtime before commit." }
  Write-AtomicJson -Path $JournalPath -Value (New-JournalValue -Phase "committed" -HadExistingRuntime ([bool]$journal.had_existing_runtime))
  Remove-RecoveryRunOnce
  try { Remove-TransactionTree } catch { Write-Warning $_.Exception.Message }
}

$mutex = $null
$locked = $false
try {
  $created = $false
  $mutex = New-Object System.Threading.Mutex($false, $MutexName, [ref]$created)
  try { $locked = $mutex.WaitOne([TimeSpan]::FromSeconds(60)) } catch [System.Threading.AbandonedMutexException] { $locked = $true }
  if (-not $locked) { throw "Timed out waiting for the setup transaction mutex." }

  switch ($Action) {
    "Begin" { Invoke-Begin }
    "PrepareReplace" { Invoke-PrepareReplace }
    "Commit" { Invoke-Commit }
    "Rollback" { Invoke-Rollback }
    "Recover" { Invoke-Recover }
  }
  exit 0
} catch {
  Write-Error $_.Exception.Message
  exit 1
} finally {
  if ($locked -and $null -ne $mutex) { try { $mutex.ReleaseMutex() } catch {} }
  if ($null -ne $mutex) { $mutex.Dispose() }
}
