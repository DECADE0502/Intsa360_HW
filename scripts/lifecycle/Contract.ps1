$ErrorActionPreference = "Stop"
$script:HwLifecycleProduct = "Insta360_HW"
$script:HwLifecycleMutexName = "Global\Insta360_HW_Lifecycle_V2"
$script:HwLifecycleJobPhases = @(
  "idle", "checking", "queued", "downloading", "verifying", "staging",
  "awaiting_elevation", "committing", "switching", "integrating",
  "verifying_runtime", "completed", "failed", "cancelled"
)

function Enter-HwLifecycleMutex {
  param([ValidateRange(0, 600000)][int]$TimeoutMilliseconds = 0)
  $mutex = New-Object System.Threading.Mutex($false, $script:HwLifecycleMutexName)
  $acquired = $false
  try {
    try {
      $acquired = $mutex.WaitOne($TimeoutMilliseconds)
    } catch [System.Threading.AbandonedMutexException] {
      $acquired = $true
    }
    if (-not $acquired) {
      throw "Another install, update, recovery, or uninstall operation is already running."
    }
    return $mutex
  } catch {
    $mutex.Dispose()
    throw
  }
}

function Exit-HwLifecycleMutex {
  param([Parameter(Mandatory=$true)][System.Threading.Mutex]$Mutex)
  try {
    $Mutex.ReleaseMutex() | Out-Null
  } finally {
    $Mutex.Dispose()
  }
}

function Test-HwLifecycleJobId {
  param([Parameter(Mandatory=$true)][string]$JobId)
  return $JobId -match '^[0-9A-Za-z][0-9A-Za-z_-]{0,127}$'
}

function Assert-HwLifecycleJobId {
  param([Parameter(Mandatory=$true)][string]$JobId)
  if (-not (Test-HwLifecycleJobId -JobId $JobId)) {
    throw "Lifecycle job ID is invalid."
  }
  return $JobId
}

function Test-HwLifecycleWorkerHandoff {
  param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$StateRoot,
    [Parameter(Mandatory=$true)][string]$StageRoot,
    [Parameter(Mandatory=$true)][string]$JobId,
    [Parameter(Mandatory=$true)][string]$ExpectedVersion
  )
  try {
    if (-not (Test-HwLifecycleJobId -JobId $JobId)) { return $false }
    if ([string]::IsNullOrWhiteSpace($ExpectedVersion) -or $ExpectedVersion -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$') { return $false }
    $install = [System.IO.Path]::GetFullPath($InstallRoot).TrimEnd("\\")
    $state = [System.IO.Path]::GetFullPath($StateRoot).TrimEnd("\\")
    $stage = [System.IO.Path]::GetFullPath($StageRoot).TrimEnd("\\")
    if ([string]::IsNullOrWhiteSpace($install) -or [string]::IsNullOrWhiteSpace($state) -or [string]::IsNullOrWhiteSpace($stage)) { return $false }
    if ($install -ieq $state -or $install -ieq $stage -or $state -ieq $stage) { return $false }
    $comparison = [System.StringComparison]::OrdinalIgnoreCase
    $separator = [System.IO.Path]::DirectorySeparatorChar
    if ($state.StartsWith($install + $separator, $comparison) -or $install.StartsWith($state + $separator, $comparison)) { return $false }
    if (-not $stage.StartsWith($state + $separator, $comparison)) { return $false }
    foreach ($path in @($install, $state, $stage)) {
      if ($path -ieq [System.IO.Path]::GetPathRoot($path).TrimEnd("\\")) { return $false }
    }
    return $true
  } catch { return $false }
}

function Assert-HwLifecycleWorkerHandoff {
  param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$StateRoot,
    [Parameter(Mandatory=$true)][string]$StageRoot,
    [Parameter(Mandatory=$true)][string]$JobId,
    [Parameter(Mandatory=$true)][string]$ExpectedVersion
  )
  if (-not (Test-HwLifecycleWorkerHandoff -InstallRoot $InstallRoot -StateRoot $StateRoot -StageRoot $StageRoot -JobId $JobId -ExpectedVersion $ExpectedVersion)) {
    throw "Lifecycle worker handoff is malformed or unsafe."
  }
}

function Get-HwLifecycleStateRoot {
  param([Parameter(Mandatory=$true)][string]$RuntimeRoot)
  if (-not [string]::IsNullOrWhiteSpace($env:INSTA360_HW_STATE_ROOT)) {
    return [System.IO.Path]::GetFullPath($env:INSTA360_HW_STATE_ROOT).TrimEnd("\")
  }
  if ((Test-Path -LiteralPath (Join-Path $RuntimeRoot "install_manifest.json")) -and
      -not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    return [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Insta360_HW")).TrimEnd("\")
  }
  return [System.IO.Path]::GetFullPath($RuntimeRoot).TrimEnd("\")
}

function Assert-HwLifecycleRuntimeRoot {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [switch]$AllowMissing
  )
  $full = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
  if ([string]::IsNullOrWhiteSpace($full)) { throw "Runtime root is empty." }
  $driveRoot = [System.IO.Path]::GetPathRoot($full).TrimEnd("\")
  if ($full -ieq $driveRoot) { throw "Refusing to use a drive root as runtime root: $full" }
  foreach ($unsafe in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:USERPROFILE, $env:LOCALAPPDATA)) {
    if (-not [string]::IsNullOrWhiteSpace($unsafe) -and $full -ieq ([System.IO.Path]::GetFullPath($unsafe).TrimEnd("\"))) {
      throw "Refusing unsafe runtime root: $full"
    }
  }
  if (-not $AllowMissing -and -not (Test-Path -LiteralPath $full -PathType Container)) {
    throw "Runtime root does not exist: $full"
  }
  if (-not $AllowMissing) {
    $required = @("Insta360_HW.exe", "app\backend\suite_app.py", "install_manifest.json")
    foreach ($relative in $required) {
      if (-not (Test-Path -LiteralPath (Join-Path $full $relative) -PathType Leaf)) {
        throw "Runtime root is not a complete Insta360_HW installation; missing $relative"
      }
    }
  }
  return $full
}

function Write-HwLifecycleJsonAtomic {
  param([Parameter(Mandatory=$true)][string]$Path, [Parameter(Mandatory=$true)]$Value)
  $target = [System.IO.Path]::GetFullPath($Path)
  $parent = Split-Path -Parent $target
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  $temp = Join-Path $parent (([System.IO.Path]::GetFileName($target)) + "." + [guid]::NewGuid().ToString("N") + ".tmp")
  $backup = Join-Path $parent (([System.IO.Path]::GetFileName($target)) + "." + [guid]::NewGuid().ToString("N") + ".bak")
  try {
    $json = ($Value | ConvertTo-Json -Depth 16) + "`n"
    $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes($json)
    $stream = [System.IO.File]::Open(
      $temp,
      [System.IO.FileMode]::CreateNew,
      [System.IO.FileAccess]::Write,
      [System.IO.FileShare]::None
    )
    try {
      $stream.Write($bytes, 0, $bytes.Length)
      $stream.Flush($true)
    } finally {
      $stream.Dispose()
    }
    foreach ($attempt in 0..9) {
      try {
        if (Test-Path -LiteralPath $target -PathType Leaf) {
          [System.IO.File]::Replace($temp, $target, $backup, $true)
        } else {
          [System.IO.File]::Move($temp, $target)
        }
        break
      } catch [System.IO.IOException] {
        if ($attempt -eq 9) { throw }
        Start-Sleep -Milliseconds (50 * ($attempt + 1))
      } catch [System.UnauthorizedAccessException] {
        if ($attempt -eq 9) { throw }
        Start-Sleep -Milliseconds (50 * ($attempt + 1))
      }
    }
  } finally {
    Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
  }
}

function Read-HwLifecycleJson {
  param([Parameter(Mandatory=$true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
  return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Get-HwLifecycleTreeSha256 {
  param([Parameter(Mandatory=$true)][string]$Path)
  $root = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
  if (-not (Test-Path -LiteralPath $root -PathType Container)) {
    throw "Runtime tree does not exist: $root"
  }
  $records = New-Object System.Collections.Generic.List[string]
  foreach ($file in Get-ChildItem -LiteralPath $root -Recurse -Force -File) {
    if (($file.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw "Runtime tree contains a reparse point: $($file.FullName)"
    }
    $relative = $file.FullName.Substring($root.Length).TrimStart([char[]]"\/").Replace("\", "/")
    $fileHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $records.Add($relative + "`t" + [string]$file.Length + "`t" + $fileHash + "`n") | Out-Null
  }
  $items = $records.ToArray()
  [Array]::Sort($items, [System.StringComparer]::Ordinal)
  $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes([string]::Concat($items))
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
  } finally {
    $sha.Dispose()
  }
}

function Test-HwLifecycleOwnedRuntimeTree {
  param([Parameter(Mandatory=$true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return $false }
  $manifestPath = Join-Path $Path "install_manifest.json"
  if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { return $false }
  try {
    $manifest = Read-HwLifecycleJson -Path $manifestPath
    return [int]$manifest.schema -eq 2 -and [string]$manifest.product -eq "Insta360_HW" -and
      [string]$manifest.layout -eq "runtime-v2"
  } catch { return $false }
}

function Remove-HwLifecycleTerminalRuntimeTrees {
  param(
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [Parameter(Mandatory=$true)][string]$StateRoot
  )
  $runtime = [System.IO.Path]::GetFullPath($RuntimeRoot).TrimEnd("\")
  $state = [System.IO.Path]::GetFullPath($StateRoot).TrimEnd("\")
  $parent = Split-Path -Parent $runtime
  $leaf = Split-Path -Leaf $runtime
  $transactions = Join-Path $state "lifecycle\transactions"
  if (-not (Test-Path -LiteralPath $transactions -PathType Container)) { return }

  foreach ($directory in Get-ChildItem -LiteralPath $transactions -Directory -ErrorAction SilentlyContinue) {
    $journal = Read-HwLifecycleJson -Path (Join-Path $directory.FullName "journal.json")
    if ($null -eq $journal -or [int]$journal.schema -ne 2 -or [string]$journal.product -ne "Insta360_HW") { continue }
    $jobId = [string]$journal.job_id
    if (-not (Test-HwLifecycleJobId -JobId $jobId)) { continue }
    if ([string]$journal.phase -notin @("completed", "rolled_back")) { continue }
    try { $journalRuntime = [System.IO.Path]::GetFullPath([string]$journal.install_root).TrimEnd("\") } catch { continue }
    if ($journalRuntime -ine $runtime) { continue }

    $safe = $true
    foreach ($spec in @(
      @("candidate_root", "candidate"),
      @("backup_root", "backup"),
      @("failed_root", "failed")
    )) {
      $property = $journal.PSObject.Properties[$spec[0]]
      if ($null -eq $property -or [string]::IsNullOrWhiteSpace([string]$property.Value)) { continue }
      $expected = Join-Path $parent ("." + $leaf + "." + $jobId + "." + $spec[1])
      try { $recorded = [System.IO.Path]::GetFullPath([string]$property.Value).TrimEnd("\") } catch { $safe = $false; continue }
      if ($recorded -ine [System.IO.Path]::GetFullPath($expected).TrimEnd("\")) { $safe = $false; continue }
      if (Test-Path -LiteralPath $recorded) {
        if (-not (Test-HwLifecycleOwnedRuntimeTree -Path $recorded)) { $safe = $false; continue }
        Remove-Item -LiteralPath $recorded -Recurse -Force
      }
    }

    $snapshotProperty = $journal.PSObject.Properties["cadence_snapshot"]
    if ($null -ne $snapshotProperty -and -not [string]::IsNullOrWhiteSpace([string]$snapshotProperty.Value)) {
      try {
        $snapshot = [System.IO.Path]::GetFullPath([string]$snapshotProperty.Value).TrimEnd("\")
        $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd("\")
        $snapshotParent = [System.IO.Path]::GetFullPath((Split-Path -Parent $snapshot)).TrimEnd("\")
        $snapshotName = Split-Path -Leaf $snapshot
        if ($snapshotParent -ine $tempRoot -or -not $snapshotName.StartsWith("insta360_hw_cadence_", [System.StringComparison]::Ordinal)) {
          $safe = $false
        } elseif (Test-Path -LiteralPath $snapshot) {
          Remove-Item -LiteralPath $snapshot -Recurse -Force
        }
      } catch { $safe = $false }
    }

    if ($safe -and (Test-Path -LiteralPath $directory.FullName)) {
      Remove-Item -LiteralPath $directory.FullName -Recurse -Force
    }
  }
}

function Assert-HwLifecycleQuiescent {
  param([Parameter(Mandatory=$true)][string]$StateRoot)
  $state = [System.IO.Path]::GetFullPath($StateRoot).TrimEnd("\")
  $jobsRoot = Join-Path $state "lifecycle\jobs"
  $latestPath = Join-Path $jobsRoot "latest.json"
  if (Test-Path -LiteralPath $latestPath -PathType Leaf) {
    $latest = Read-HwLifecycleJson -Path $latestPath
    $jobId = [string]$latest.job_id
    if (-not [string]::IsNullOrWhiteSpace($jobId)) {
      Assert-HwLifecycleJobId -JobId $jobId | Out-Null
      $jobPath = Join-Path $jobsRoot ($jobId + ".json")
      if (Test-Path -LiteralPath $jobPath -PathType Leaf) {
        $job = Read-HwLifecycleJson -Path $jobPath
        $phase = [string]$job.phase
        if ($phase -notin @("idle", "completed", "failed", "cancelled")) {
          throw "An update task is still active in phase '$phase'. Finish or cancel it before changing the installation."
        }
      }
    }
  }

  $transactionsRoot = Join-Path $state "lifecycle\transactions"
  if (-not (Test-Path -LiteralPath $transactionsRoot -PathType Container)) { return }
  foreach ($transaction in Get-ChildItem -LiteralPath $transactionsRoot -Directory -ErrorAction SilentlyContinue) {
    $journalPath = Join-Path $transaction.FullName "journal.json"
    if (-not (Test-Path -LiteralPath $journalPath -PathType Leaf)) { continue }
    $journal = Read-HwLifecycleJson -Path $journalPath
    $phase = [string]$journal.phase
    if ($phase -notin @("completed", "rolled_back")) {
      throw "An interrupted update transaction still requires recovery (phase '$phase'). Open the platform once before installing or uninstalling."
    }
  }
}

function Get-HwLifecycleJobPath {
  param([Parameter(Mandatory=$true)][string]$StateRoot, [Parameter(Mandatory=$true)][string]$JobId)
  Assert-HwLifecycleJobId -JobId $JobId | Out-Null
  return Join-Path $StateRoot ("lifecycle\jobs\" + $JobId + ".json")
}

function Set-HwLifecycleJobPhase {
  param(
    [Parameter(Mandatory=$true)][string]$StateRoot,
    [Parameter(Mandatory=$true)][string]$JobId,
    [Parameter(Mandatory=$true)]
    [ValidateSet("idle", "checking", "queued", "downloading", "verifying", "staging", "awaiting_elevation", "committing", "switching", "integrating", "verifying_runtime", "completed", "failed", "cancelled")]
    [string]$Phase,
    [Parameter(Mandatory=$true)][int]$Progress,
    [Parameter(Mandatory=$true)][string]$Message,
    [hashtable]$Additional = @{}
  )
  Assert-HwLifecycleJobId -JobId $JobId | Out-Null
  $path = Get-HwLifecycleJobPath -StateRoot $StateRoot -JobId $JobId
  $current = Read-HwLifecycleJson -Path $path
  $value = [ordered]@{}
  if ($null -ne $current) {
    foreach ($property in $current.PSObject.Properties) { $value[$property.Name] = $property.Value }
  }
  $value["schema"] = 2
  $value["job_id"] = $JobId
  $value["phase"] = $Phase
  $value["progress"] = [Math]::Max(0, [Math]::Min(100, $Progress))
  $value["message"] = $Message
  $value["updated_at"] = (Get-Date).ToUniversalTime().ToString("o")
  $value["running"] = $Phase -notin @("completed", "failed", "cancelled")
  $value["done"] = $Phase -eq "completed"
  $value["failed"] = $Phase -eq "failed"
  foreach ($key in $Additional.Keys) { $value[$key] = $Additional[$key] }
  Write-HwLifecycleJsonAtomic -Path $path -Value $value
  return $value
}

function Move-HwLifecycleTreeContents {
  param([Parameter(Mandatory=$true)][string]$Source, [Parameter(Mandatory=$true)][string]$Destination)
  if (-not (Test-Path -LiteralPath $Source -PathType Container)) { return }
  New-Item -ItemType Directory -Force -Path $Destination | Out-Null
  & robocopy.exe $Source $Destination /E /MOVE /COPY:DAT /DCOPY:DAT /R:2 /W:1 /XJ /NFL /NDL /NJH /NJS | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "Failed to migrate mutable state from $Source to $Destination (robocopy $LASTEXITCODE)." }
  if (Test-Path -LiteralPath $Source) {
    $remaining = @(Get-ChildItem -LiteralPath $Source -Force -ErrorAction SilentlyContinue)
    if ($remaining.Count -gt 0) { throw "Mutable-state migration left files behind in $Source." }
    Remove-Item -LiteralPath $Source -Force
  }
}

function Ensure-HwLifecycleJunction {
  param([Parameter(Mandatory=$true)][string]$Path, [Parameter(Mandatory=$true)][string]$Target)
  New-Item -ItemType Directory -Force -Path $Target | Out-Null
  if (Test-Path -LiteralPath $Path) {
    $item = Get-Item -LiteralPath $Path -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
      $actual = [System.IO.Path]::GetFullPath($item.Target).TrimEnd("\")
      $expected = [System.IO.Path]::GetFullPath($Target).TrimEnd("\")
      if ($actual -ieq $expected) { return }
      Remove-Item -LiteralPath $Path -Force
    } else {
      Move-HwLifecycleTreeContents -Source $Path -Destination $Target
    }
  }
  New-Item -ItemType Junction -Path $Path -Target $Target -Force | Out-Null
}

function Remove-HwLifecycleJunction {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$ExpectedTarget
  )
  if (-not (Test-Path -LiteralPath $Path)) { return }
  $item = Get-Item -LiteralPath $Path -Force
  if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0) {
    throw "Refusing to remove a real directory where a lifecycle junction was expected: $Path"
  }
  $actual = [System.IO.Path]::GetFullPath([string]$item.Target).TrimEnd("\")
  $expected = [System.IO.Path]::GetFullPath($ExpectedTarget).TrimEnd("\")
  if ($actual -ine $expected) {
    throw "Refusing to remove a junction with an unexpected target: $Path -> $actual"
  }
  [System.IO.Directory]::Delete($Path, $false)
}

function Remove-HwLifecycleRuntimeJunctions {
  param(
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [Parameter(Mandatory=$true)][string]$StateRoot
  )
  $runtime = [System.IO.Path]::GetFullPath($RuntimeRoot).TrimEnd("\")
  $state = [System.IO.Path]::GetFullPath($StateRoot).TrimEnd("\")
  if ($runtime -ieq $state) { return }
  Remove-HwLifecycleJunction -Path (Join-Path $runtime "data") -ExpectedTarget (Join-Path $state "data")
  Remove-HwLifecycleJunction -Path (Join-Path $runtime "plugins\user") -ExpectedTarget (Join-Path $state "plugins\user")
}

function Initialize-HwLifecycleState {
  param(
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [string]$StateRoot = ""
  )
  $runtime = [System.IO.Path]::GetFullPath($RuntimeRoot).TrimEnd("\")
  if ([string]::IsNullOrWhiteSpace($StateRoot)) { $StateRoot = Get-HwLifecycleStateRoot -RuntimeRoot $runtime }
  $state = [System.IO.Path]::GetFullPath($StateRoot).TrimEnd("\")
  $env:INSTA360_HW_STATE_ROOT = $state
  foreach ($relative in @(
    "data\inbox", "data\uploads", "data\outputs", "data\history", "data\reports\runtime",
    "config", "plugins\user\scripts", "lifecycle\jobs", "lifecycle\transactions", "lifecycle\cache", "runtime"
  )) {
    New-Item -ItemType Directory -Force -Path (Join-Path $state $relative) | Out-Null
  }
  if ($runtime -ieq $state) { return $state }

  $legacyConfig = Join-Path $runtime "config\local.json"
  $stateConfig = Join-Path $state "config\local.json"
  if ((Test-Path -LiteralPath $legacyConfig -PathType Leaf) -and -not (Test-Path -LiteralPath $stateConfig)) {
    Copy-Item -LiteralPath $legacyConfig -Destination $stateConfig -Force
  }
  if (Test-Path -LiteralPath $legacyConfig -PathType Leaf) { Remove-Item -LiteralPath $legacyConfig -Force }

  Ensure-HwLifecycleJunction -Path (Join-Path $runtime "data") -Target (Join-Path $state "data")
  New-Item -ItemType Directory -Force -Path (Join-Path $runtime "plugins") | Out-Null
  Ensure-HwLifecycleJunction -Path (Join-Path $runtime "plugins\user") -Target (Join-Path $state "plugins\user")
  return $state
}

function Invoke-HwLifecycleFault {
  param([string]$FaultAt, [Parameter(Mandatory=$true)][string]$Point)
  if (-not [string]::IsNullOrWhiteSpace($FaultAt) -and $FaultAt -eq $Point) {
    throw "Injected lifecycle fault at $Point"
  }
}
