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
    "scripts\lifecycle_v3\Runtime.ps1", "scripts\lifecycle\Contract.ps1",
    "scripts\lifecycle\Runtime.ps1",
    "scripts\lib\Paths.ps1", "config\update_public_key.pem"
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

function Get-HwV3TreeSha256 {
  param([Parameter(Mandatory=$true)][string]$Path)
  $root = Get-HwV3FullPath -Path $Path -Label "TreeRoot"
  $records = New-Object System.Collections.Generic.List[string]
  foreach ($file in Get-ChildItem -LiteralPath $root -Recurse -Force -File) {
    $relative = $file.FullName.Substring($root.Length).TrimStart([char[]]"\/").Replace("\", "/")
    $digest = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
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
