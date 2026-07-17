$ErrorActionPreference = "Stop"

$script:HwV3Product = "Insta360_HW"
$script:HwV3MutexName = "Global\Insta360_HW_Lifecycle_V2"

function Get-HwV3SystemTool {
  param([Parameter(Mandatory=$true)][string]$RelativePath)
  $windows = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Windows)
  if ([string]::IsNullOrWhiteSpace($windows)) { throw "Windows system directory is unavailable." }
  $path = Join-Path $windows $RelativePath
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required Windows system tool is missing: $path" }
  return [System.IO.Path]::GetFullPath($path)
}

function Get-HwV3PowerShellPath {
  return Get-HwV3SystemTool -RelativePath "System32\WindowsPowerShell\v1.0\powershell.exe"
}

function Get-HwV3RobocopyPath {
  return Get-HwV3SystemTool -RelativePath "System32\robocopy.exe"
}

function Get-HwV3TaskSchedulerPath {
  return Get-HwV3SystemTool -RelativePath "System32\schtasks.exe"
}

function Get-HwV3BootIdentity {
  try {
    $bootTime = (Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop).LastBootUpTime
    if ($null -eq $bootTime) { throw "Windows did not return a boot timestamp." }
    return ([DateTime]$bootTime).ToUniversalTime().ToString("o")
  } catch {
    throw "Unable to identify the current Windows boot session: $($_.Exception.Message)"
  }
}

function Release-HwV3ComObjects {
  param([object[]]$Objects)
  foreach ($item in $Objects) {
    if ($null -ne $item -and [Runtime.InteropServices.Marshal]::IsComObject($item)) {
      try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($item) } catch {}
    }
  }
}

function Register-HwV3RecoveryTask {
  param(
    [Parameter(Mandatory=$true)][string]$TaskName,
    [Parameter(Mandatory=$true)][string]$PowerShellPath,
    [Parameter(Mandatory=$true)][string]$ScriptPath
  )
  if ([string]::IsNullOrWhiteSpace($TaskName) -or $TaskName.Length -gt 200 -or
      $TaskName.Contains("\") -or $TaskName.Contains("/")) {
    throw "Lifecycle recovery task name is invalid."
  }
  $powershell = [System.IO.Path]::GetFullPath($PowerShellPath)
  $script = [System.IO.Path]::GetFullPath($ScriptPath)
  if (-not (Test-Path -LiteralPath $powershell -PathType Leaf)) {
    throw "Lifecycle recovery PowerShell executable is missing: $powershell"
  }
  if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Lifecycle recovery script is missing: $script"
  }
  $arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $script
  $service = $null
  $folder = $null
  $definition = $null
  $trigger = $null
  $action = $null
  $registered = $null
  try {
    $service = New-Object -ComObject "Schedule.Service"
    $service.Connect()
    $folder = $service.GetFolder("\")
    $definition = $service.NewTask(0)
    $definition.RegistrationInfo.Description = "Insta360_HW protected lifecycle recovery"
    $definition.Principal.UserId = "SYSTEM"
    $definition.Principal.LogonType = 5
    $definition.Principal.RunLevel = 1
    $definition.Settings.Enabled = $true
    # A recovery task must run only after the next boot. Catching up a missed
    # boot trigger would start recovery concurrently with the active update.
    $definition.Settings.StartWhenAvailable = $false
    $definition.Settings.DisallowStartIfOnBatteries = $false
    $definition.Settings.StopIfGoingOnBatteries = $false
    $trigger = $definition.Triggers.Create(8)
    $trigger.Delay = "PT30S"
    $action = $definition.Actions.Create(0)
    $action.Path = $powershell
    $action.Arguments = $arguments
    $registered = $folder.RegisterTaskDefinition($TaskName, $definition, 6, "SYSTEM", $null, 5)
    return [string]$registered.Name
  } catch {
    throw "Failed to register the protected lifecycle recovery task: $($_.Exception.Message)"
  } finally {
    Release-HwV3ComObjects -Objects @($registered, $action, $trigger, $definition, $folder, $service)
  }
}

function Remove-HwV3RecoveryTask {
  param([Parameter(Mandatory=$true)][string]$TaskName)
  $service = $null
  $folder = $null
  $task = $null
  try {
    $service = New-Object -ComObject "Schedule.Service"
    $service.Connect()
    $folder = $service.GetFolder("\")
    try {
      $task = $folder.GetTask($TaskName)
    } catch {
      if ([int]$_.Exception.HResult -eq -2147024894) { return $true }
      throw
    }
    $folder.DeleteTask($TaskName, 0)
    return $true
  } catch {
    throw "Failed to remove the protected lifecycle recovery task: $($_.Exception.Message)"
  } finally {
    Release-HwV3ComObjects -Objects @($task, $folder, $service)
  }
}

function Enter-HwV3LifecycleMutex {
  param([ValidateRange(0, 600000)][int]$TimeoutMilliseconds = 0)
  $mutex = New-Object System.Threading.Mutex($false, $script:HwV3MutexName)
  try {
    try { $acquired = $mutex.WaitOne($TimeoutMilliseconds) }
    catch [System.Threading.AbandonedMutexException] { $acquired = $true }
    if (-not $acquired) { throw "Another platform lifecycle operation is already running." }
    return $mutex
  } catch {
    $mutex.Dispose()
    throw
  }
}

function Exit-HwV3LifecycleMutex {
  param([Parameter(Mandatory=$true)][System.Threading.Mutex]$Mutex)
  try { $Mutex.ReleaseMutex() | Out-Null }
  finally { $Mutex.Dispose() }
}

function Restore-HwV2InterruptedSetup {
  param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$StateRoot,
    [switch]$SkipRecoveryRegistration
  )
  $install = Get-HwV3FullPath -Path $InstallRoot -Label "InstallRoot"
  $state = Get-HwV3FullPath -Path $StateRoot -Label "StateRoot"
  $transactionRoot = Join-Path $state "lifecycle\setup\active"
  if (-not (Test-Path -LiteralPath $transactionRoot -PathType Container)) { return $false }

  $mutex = New-Object System.Threading.Mutex($false, "Global\Insta360_HW_SetupTransaction_V1")
  $locked = $false
  try {
    try { $locked = $mutex.WaitOne([TimeSpan]::FromSeconds(30)) }
    catch [System.Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw "Timed out waiting for the legacy setup transaction." }

    $journalPath = Join-Path $transactionRoot "journal.json"
    $journal = Read-HwV3Json -Path $journalPath -Required
    if ([int]$journal.schema -ne 1 -or [string]$journal.product -ne $script:HwV3Product) {
      throw "Legacy setup transaction identity is invalid."
    }
    if ((Get-HwV3FullPath -Path ([string]$journal.install_root) -Label "legacy install_root") -ine $install -or
        (Get-HwV3FullPath -Path ([string]$journal.state_root) -Label "legacy state_root") -ine $state) {
      throw "Legacy setup transaction roots do not match this installation."
    }

    $backupRoot = Join-Path $transactionRoot "backup"
    if ((Get-HwV3FullPath -Path ([string]$journal.backup_root) -Label "legacy backup_root") -ine
        (Get-HwV3FullPath -Path $backupRoot -Label "legacy backup root")) {
      throw "Legacy setup transaction backup path is invalid."
    }
    $phase = [string]$journal.phase
    if ($phase -notin @("backing_up", "prepared", "replacing", "rolling_back", "committed", "rolled_back")) {
      throw "Legacy setup transaction phase is unsupported: $phase"
    }

    if ($phase -in @("replacing", "rolling_back")) {
      if ([bool]$journal.had_existing_runtime) {
        if (-not (Test-Path -LiteralPath $backupRoot -PathType Container)) {
          throw "Legacy setup rollback backup is missing."
        }
        foreach ($item in Get-ChildItem -LiteralPath $backupRoot -Recurse -Force) {
          if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Legacy setup rollback backup contains a reparse point: $($item.FullName)"
          }
        }
      }

      if (Test-Path -LiteralPath $install -PathType Container) {
        foreach ($item in Get-ChildItem -LiteralPath $install -Force) {
          if ($item.Name -ieq "maintenance" -or $item.Name -match '^unins\d{3}\.(exe|dat|msg)$') { continue }
          if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            if ($item.PSIsContainer) { [System.IO.Directory]::Delete($item.FullName) }
            else { [System.IO.File]::Delete($item.FullName) }
          } else {
            Remove-Item -LiteralPath $item.FullName -Recurse -Force
          }
        }
      }

      if ([bool]$journal.had_existing_runtime) {
        New-Item -ItemType Directory -Force -Path $install | Out-Null
        & (Get-HwV3RobocopyPath) $backupRoot $install /E /COPY:DAT /DCOPY:DAT /XJ /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "Legacy setup rollback restore failed with robocopy exit code $LASTEXITCODE." }
      }
    }

    if (-not $SkipRecoveryRegistration) {
      $runOnce = "HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce"
      try {
        $command = [string](Get-ItemPropertyValue -LiteralPath $runOnce -Name "Insta360_HW_SetupRecovery" -ErrorAction Stop)
        if ($command.IndexOf($transactionRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
          Remove-ItemProperty -LiteralPath $runOnce -Name "Insta360_HW_SetupRecovery" -Force
        }
      } catch [System.Management.Automation.ItemNotFoundException] {}
      catch [System.Management.Automation.PSArgumentException] {}
    }
    Remove-Item -LiteralPath $transactionRoot -Recurse -Force
    return $true
  } finally {
    if ($locked) { try { $mutex.ReleaseMutex() | Out-Null } catch {} }
    $mutex.Dispose()
  }
}

function Restore-HwV2InterruptedUpdates {
  param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$StateRoot,
    [Parameter(Mandatory=$true)][string]$WorkerPath,
    [switch]$NoRestart,
    [switch]$SkipCadence,
    [switch]$SkipRecoveryRegistration
  )
  $install = Get-HwV3FullPath -Path $InstallRoot -Label "InstallRoot"
  $state = Get-HwV3FullPath -Path $StateRoot -Label "StateRoot"
  $worker = [System.IO.Path]::GetFullPath($WorkerPath)
  if (-not (Test-Path -LiteralPath $worker -PathType Leaf)) {
    throw "Legacy update recovery worker is missing: $worker"
  }
  $transactions = Join-Path $state "lifecycle\transactions"
  if (-not (Test-Path -LiteralPath $transactions -PathType Container)) { return 0 }

  $pending = @()
  foreach ($directory in Get-ChildItem -LiteralPath $transactions -Directory -Force -ErrorAction SilentlyContinue) {
    if ($directory.Name -cnotmatch '^[0-9a-f]{32}$') { continue }
    if (($directory.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw "Legacy update transaction must not be a reparse point."
    }
    $journal = Read-HwV3Json -Path (Join-Path $directory.FullName "journal.json") -Required
    if ([int]$journal.schema -ne 2 -or [string]$journal.product -ne "Insta360_HW" -or
        [string]$journal.job_id -cne $directory.Name -or
        (Get-HwV3FullPath -Path ([string]$journal.install_root) -Label "legacy update install_root") -ine $install -or
        (Get-HwV3FullPath -Path ([string]$journal.state_root) -Label "legacy update state_root") -ine $state) {
      throw "Legacy update transaction identity is invalid."
    }
    $pending += [pscustomobject]@{ directory = $directory; journal = $journal }
  }

  $recovered = 0
  foreach ($item in @($pending | Sort-Object { [string]$_.journal.updated_at })) {
    $jobId = [string]$item.journal.job_id
    $phase = [string]$item.journal.phase
    if ($phase -notin @("completed", "rolled_back")) {
      $arguments = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $worker,
        "-Action", "Recover", "-InstallRoot", $install, "-StateRoot", $state,
        "-JobId", $jobId
      )
      if ($NoRestart) { $arguments += "-NoRestart" }
      if ($SkipCadence) { $arguments += "-SkipCadence" }
      if ($SkipRecoveryRegistration) { $arguments += "-SkipRecoveryRegistration" }
      & (Get-HwV3PowerShellPath) @arguments
      if ($LASTEXITCODE -ne 0) {
        throw "Legacy update recovery failed for $jobId with exit code $LASTEXITCODE."
      }
      $item.journal = Read-HwV3Json -Path (Join-Path $item.directory.FullName "journal.json") -Required
      $phase = [string]$item.journal.phase
      $recovered += 1
    }
    if ($phase -notin @("completed", "rolled_back")) {
      throw "Legacy update transaction did not reach a terminal state: $jobId"
    }

    $parent = Split-Path -Parent $install
    $leaf = Split-Path -Leaf $install
    foreach ($suffix in @("candidate", "backup", "failed")) {
      $owned = Join-Path $parent ("." + $leaf + "." + $jobId + "." + $suffix)
      $journalField = $suffix + "_root"
      $journalPath = [string]$item.journal.$journalField
      if (-not [string]::IsNullOrWhiteSpace($journalPath) -and
          [System.IO.Path]::GetFullPath($journalPath).TrimEnd("\") -ine
          [System.IO.Path]::GetFullPath($owned).TrimEnd("\")) {
        throw "Legacy update transaction contains an invalid $journalField."
      }
      if (Test-Path -LiteralPath $owned) {
        $ownedItem = Get-Item -LiteralPath $owned -Force
        if (($ownedItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
          throw "Legacy update cleanup refused a reparse point: $owned"
        }
        Remove-Item -LiteralPath $owned -Recurse -Force
      }
    }
    Remove-Item -LiteralPath $item.directory.FullName -Recurse -Force
    Remove-Item -LiteralPath (Join-Path $state ("lifecycle\jobs\" + $jobId + ".json")) `
      -Force -ErrorAction SilentlyContinue
  }
  return $recovered
}

function Assert-HwV3JobId {
  param([Parameter(Mandatory=$true)][string]$JobId)
  if ($JobId -notmatch '^[0-9a-fA-F]{32}$') { throw "Lifecycle job ID must be 32 hexadecimal characters." }
  return $JobId.ToLowerInvariant()
}

function Assert-HwV3Version {
  param([Parameter(Mandatory=$true)][string]$Version)
  if ($Version -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$') {
    throw "Runtime version is invalid: $Version"
  }
  return $Version
}

function Assert-HwV3Revision {
  param([Parameter(Mandatory=$true)][string]$Revision)
  if ($Revision -notmatch '^[0-9a-fA-F]{40}$') { throw "Runtime revision must be a 40-character commit hash." }
  return $Revision.ToLowerInvariant()
}

function Get-HwV3FullPath {
  param([Parameter(Mandatory=$true)][string]$Path, [Parameter(Mandatory=$true)][string]$Label)
  $full = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
  if ([string]::IsNullOrWhiteSpace($full)) { throw "$Label is empty." }
  $root = [System.IO.Path]::GetPathRoot($full).TrimEnd("\")
  if ($full -ieq $root) { throw "$Label must not be a filesystem root." }
  return $full
}

function Test-HwV3PathWithin {
  param([Parameter(Mandatory=$true)][string]$Path, [Parameter(Mandatory=$true)][string]$Parent)
  $child = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
  $root = [System.IO.Path]::GetFullPath($Parent).TrimEnd("\")
  return $child.StartsWith($root + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)
}

function Write-HwV3JsonAtomic {
  param([Parameter(Mandatory=$true)][string]$Path, [Parameter(Mandatory=$true)]$Value)
  $target = [System.IO.Path]::GetFullPath($Path)
  $parent = Split-Path -Parent $target
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  $temporary = Join-Path $parent ((Split-Path -Leaf $target) + "." + [guid]::NewGuid().ToString("N") + ".tmp")
  $backup = Join-Path $parent ((Split-Path -Leaf $target) + "." + [guid]::NewGuid().ToString("N") + ".bak")
  try {
    $json = ($Value | ConvertTo-Json -Depth 24) + "`n"
    $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes($json)
    $stream = [System.IO.File]::Open(
      $temporary,
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
    foreach ($attempt in 0..7) {
      try {
        if (Test-Path -LiteralPath $target -PathType Leaf) {
          [System.IO.File]::Replace($temporary, $target, $backup, $true)
        } else {
          [System.IO.File]::Move($temporary, $target)
        }
        break
      } catch [System.IO.IOException] {
        if ($attempt -eq 7) { throw }
        Start-Sleep -Milliseconds (25 * ($attempt + 1))
      } catch [System.UnauthorizedAccessException] {
        if ($attempt -eq 7) { throw }
        Start-Sleep -Milliseconds (25 * ($attempt + 1))
      }
    }
  } finally {
    Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
  }
}

function Read-HwV3Json {
  param([Parameter(Mandatory=$true)][string]$Path, [switch]$Required)
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    if ($Required) { throw "Required JSON file is missing: $Path" }
    return $null
  }
  try { return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json }
  catch { throw "JSON file is invalid: $Path" }
}

function Get-HwV3RuntimeId {
  param([Parameter(Mandatory=$true)][string]$Version, [Parameter(Mandatory=$true)][string]$Revision)
  $validVersion = Assert-HwV3Version -Version $Version
  $validRevision = Assert-HwV3Revision -Revision $Revision
  return $validVersion + "+" + $validRevision
}

function Get-HwV3RuntimeRelativePath {
  param([Parameter(Mandatory=$true)][string]$Version, [Parameter(Mandatory=$true)][string]$Revision)
  return "runtime/" + (Get-HwV3RuntimeId -Version $Version -Revision $Revision)
}

function Resolve-HwV3RuntimePointer {
  param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$RelativePath,
    [Parameter(Mandatory=$true)][string]$Field
  )
  if ($RelativePath -notmatch '^runtime/((0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?\+[0-9a-fA-F]{40})$') {
    throw "$Field does not identify one versioned runtime."
  }
  $runtimeParent = [System.IO.Path]::GetFullPath((Join-Path $InstallRoot "runtime")).TrimEnd("\")
  $resolved = [System.IO.Path]::GetFullPath((Join-Path $InstallRoot $RelativePath.Replace("/", "\"))).TrimEnd("\")
  if (-not (Test-HwV3PathWithin -Path $resolved -Parent $runtimeParent)) { throw "$Field escapes the runtime directory." }
  return $resolved
}

function Read-HwV3Installation {
  param([Parameter(Mandatory=$true)][string]$InstallRoot)
  $root = Get-HwV3FullPath -Path $InstallRoot -Label "InstallRoot"
  $path = Join-Path $root "installation.json"
  $value = Read-HwV3Json -Path $path -Required
  if ([int]$value.schema_version -ne 3 -or [string]$value.product -ne $script:HwV3Product -or
      [string]$value.layout -ne "versioned-runtime-v3") {
    throw "Installation metadata identity is invalid."
  }
  if ([int]$value.generation -lt 1) { throw "Installation metadata generation is invalid." }
  Resolve-HwV3RuntimePointer -InstallRoot $root -RelativePath ([string]$value.active_runtime) -Field "active_runtime" | Out-Null
  if (-not [string]::IsNullOrWhiteSpace([string]$value.previous_runtime)) {
    Resolve-HwV3RuntimePointer -InstallRoot $root -RelativePath ([string]$value.previous_runtime) -Field "previous_runtime" | Out-Null
  }
  return $value
}

function Assert-HwV3RuntimeTree {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$ExpectedVersion,
    [Parameter(Mandatory=$true)][string]$ExpectedRevision,
    [switch]$RequireCadence
  )
  $root = Get-HwV3FullPath -Path $Path -Label "RuntimeRoot"
  if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw "Runtime directory does not exist: $root" }
  $rootItem = Get-Item -LiteralPath $root -Force
  if (($rootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "Runtime root must not be a reparse point: $root"
  }
  $required = @(
    "VERSION", "REVISION", "install_manifest.json", "launch_tool_suite.ps1",
    "app\backend\suite_app.py", "runtime\python\python.exe",
    "scripts\lifecycle_v3\Worker.ps1", "scripts\lifecycle_v3\Recover.ps1",
    "scripts\lifecycle_v3\Resume.ps1", "scripts\lifecycle_v3\Contract.ps1",
    "scripts\lifecycle_v3\Runtime.ps1", "scripts\lifecycle_v3\Install.ps1",
    "scripts\lifecycle_v3\Uninstall.ps1", "scripts\lifecycle_v3\SetupRunner.ps1",
    "scripts\lifecycle_v3\SetupRecover.ps1",
    "scripts\lifecycle\Contract.ps1",
    "scripts\lifecycle\Runtime.ps1", "scripts\lifecycle\Recover.ps1",
    "scripts\lifecycle\Worker.ps1",
    "scripts\remove_cadence_loader.ps1", "scripts\lib\Paths.ps1",
    "cadence\iac_bom_tool.tcl", "config\capabilities.json", "config\update_public_key.pem"
  )
  if ($RequireCadence) { $required += @("scripts\lib\Cadence.ps1", "scripts\lib\TclScripts.ps1") }
  foreach ($relative in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $relative) -PathType Leaf)) {
      throw "Runtime is incomplete; missing $relative"
    }
  }
  foreach ($item in Get-ChildItem -LiteralPath $root -Recurse -Force) {
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw "Runtime tree contains a reparse point: $($item.FullName)"
    }
  }
  $version = (Get-Content -LiteralPath (Join-Path $root "VERSION") -Raw -Encoding UTF8).Trim()
  $revision = (Get-Content -LiteralPath (Join-Path $root "REVISION") -Raw -Encoding UTF8).Trim().ToLowerInvariant()
  if ($version -cne $ExpectedVersion -or $revision -cne $ExpectedRevision.ToLowerInvariant()) {
    throw "Runtime VERSION or REVISION does not match the requested release."
  }
  $manifest = Read-HwV3Json -Path (Join-Path $root "install_manifest.json") -Required
  if ([int]$manifest.schema -ne 3 -or [string]$manifest.product -ne $script:HwV3Product -or
      [string]$manifest.layout -ne "runtime-v3" -or [string]$manifest.version -cne $ExpectedVersion -or
      ([string]$manifest.revision).ToLowerInvariant() -cne $ExpectedRevision.ToLowerInvariant()) {
    throw "Runtime install manifest does not match the requested release."
  }
  return $root
}

function Get-HwV3FileSha256WithRetry {
  param([Parameter(Mandatory=$true)][string]$Path)
  foreach ($attempt in 0..9) {
    try {
      return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
    } catch {
      if ($attempt -eq 9) { throw }
      Start-Sleep -Milliseconds (100 * ($attempt + 1))
    }
  }
}

function Get-HwV3TreeSha256 {
  param([Parameter(Mandatory=$true)][string]$Path)
  $root = Get-HwV3FullPath -Path $Path -Label "TreeRoot"
  $records = New-Object System.Collections.Generic.List[string]
  foreach ($file in Get-ChildItem -LiteralPath $root -Recurse -Force -File) {
    $relative = $file.FullName.Substring($root.Length).TrimStart([char[]]"\/").Replace("\", "/")
    $digest = Get-HwV3FileSha256WithRetry -Path $file.FullName
    $records.Add($relative + "`t" + [string]$file.Length + "`t" + $digest + "`n") | Out-Null
  }
  $items = $records.ToArray()
  [Array]::Sort($items, [System.StringComparer]::Ordinal)
  $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes([string]::Concat($items))
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try { return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant() }
  finally { $sha.Dispose() }
}

function Set-HwV3JobPhase {
  param(
    [Parameter(Mandatory=$true)][string]$StateRoot,
    [Parameter(Mandatory=$true)][string]$JobId,
    [Parameter(Mandatory=$true)][string]$Phase,
    [Parameter(Mandatory=$true)][int]$Progress,
    [Parameter(Mandatory=$true)][string]$Message,
    [hashtable]$Additional = @{}
  )
  $id = Assert-HwV3JobId -JobId $JobId
  $path = Join-Path $StateRoot ("lifecycle\v3\jobs\" + $id + ".json")
  $current = Read-HwV3Json -Path $path
  $value = [ordered]@{}
  if ($null -ne $current) { foreach ($property in $current.PSObject.Properties) { $value[$property.Name] = $property.Value } }
  $value["schema"] = 3
  $value["job_id"] = $id
  $value["phase"] = $Phase
  $value["progress"] = [Math]::Max(0, [Math]::Min(100, $Progress))
  $value["message"] = $Message
  $value["updated_at"] = (Get-Date).ToUniversalTime().ToString("o")
  $value["running"] = $Phase -notin @("completed", "failed", "cancelled")
  $value["done"] = $Phase -eq "completed"
  $value["failed"] = $Phase -eq "failed"
  foreach ($key in $Additional.Keys) { $value[$key] = $Additional[$key] }
  Write-HwV3JsonAtomic -Path $path -Value $value
  return $value
}

function Invoke-HwV3Fault {
  param([string]$FaultAt, [Parameter(Mandatory=$true)][string]$Point)
  if (-not [string]::IsNullOrWhiteSpace($FaultAt) -and $FaultAt -ceq $Point) {
    throw "Injected lifecycle fault at $Point"
  }
}
