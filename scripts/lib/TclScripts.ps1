$script:HwAgentCadenceLoaderName = "iac_bom_tool.tcl"
$script:HwAgentCadenceLoaderMarker = "# Insta360_HW Cadence Loader | schema=2 | managed=true"

function Test-HwAgentOwnedCadenceLoader {
  param([Parameter(Mandatory=$true)][string]$LoaderPath)
  if (-not (Test-Path -LiteralPath $LoaderPath -PathType Leaf)) { return $false }
  if ((Split-Path -Leaf $LoaderPath) -ine $script:HwAgentCadenceLoaderName) { return $false }
  try {
    $text = [System.IO.File]::ReadAllText($LoaderPath)
    return $text.IndexOf($script:HwAgentCadenceLoaderMarker, [System.StringComparison]::Ordinal) -ge 0
  } catch { return $false }
}

function Remove-HwAgentOwnedCadenceLoader {
  param([Parameter(Mandatory=$true)][string]$AutoLoadDir)
  $loader = Join-Path $AutoLoadDir $script:HwAgentCadenceLoaderName
  if (-not (Test-HwAgentOwnedCadenceLoader -LoaderPath $loader)) { return $false }
  Remove-Item -LiteralPath $loader -Force
  return $true
}

function Get-HwAgentCadenceStatePath {
  if (-not [string]::IsNullOrWhiteSpace($env:INSTA360_HW_STATE_ROOT)) {
    return (Join-Path ([System.IO.Path]::GetFullPath($env:INSTA360_HW_STATE_ROOT).TrimEnd("\")) "cadence_integration.json")
  }
  $localAppData = $env:LOCALAPPDATA
  if ([string]::IsNullOrWhiteSpace($localAppData)) {
    $localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
  }
  if ([string]::IsNullOrWhiteSpace($localAppData)) {
    throw "LOCALAPPDATA is required to persist Cadence integration state."
  }
  return (Join-Path $localAppData "Insta360_HW\cadence_integration.json")
}

function Test-HwAgentCadenceAutoLoadDirectoryPath {
  param([Parameter(Mandatory=$true)][string]$Path)
  try {
    $full = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
    $suffix = "\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad"
    return $full.EndsWith($suffix, [System.StringComparison]::OrdinalIgnoreCase)
  } catch { return $false }
}

function Get-HwAgentCadenceIntegrationState {
  $statePath = Get-HwAgentCadenceStatePath
  if (-not (Test-Path -LiteralPath $statePath)) {
    return [pscustomobject]@{ schema_version = 2; enabled = $true; loader_paths = @() }
  }
  try {
    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $state.PSObject.Properties["enabled"]) {
      throw "Cadence integration state has no enabled value."
    }
    $paths = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($path in @($state.loader_paths)) {
      if ([string]::IsNullOrWhiteSpace([string]$path) -or
          -not (Test-HwAgentCadenceAutoLoadDirectoryPath -Path ([string]$path))) { continue }
      $full = [System.IO.Path]::GetFullPath([string]$path).TrimEnd("\")
      if (-not $seen.ContainsKey($full)) {
        $seen[$full] = $true
        $paths.Add($full) | Out-Null
      }
    }
    return [pscustomobject]@{ schema_version = 2; enabled = [bool]$state.enabled; loader_paths = $paths.ToArray() }
  } catch {
    # A corrupt state file must not silently re-enable an integration the user
    # intentionally removed. Explicit repair can overwrite this state.
    return [pscustomobject]@{ schema_version = 2; enabled = $false; loader_paths = @() }
  }
}

function Test-HwAgentCadenceIntegrationEnabled {
  return [bool](Get-HwAgentCadenceIntegrationState).enabled
}

function Get-HwAgentRecordedCadenceAutoLoadDirs {
  return @((Get-HwAgentCadenceIntegrationState).loader_paths)
}

function Get-HwAgentManagedCadenceAutoLoadDirs {
  $candidates = @()
  $candidates += @(Find-CadenceLoaderInstallDirs)
  $candidates += @(Get-HwAgentRecordedCadenceAutoLoadDirs)

  $paths = New-Object System.Collections.Generic.List[string]
  $seen = @{}
  foreach ($candidate in $candidates) {
    $path = [string]$candidate
    if ([string]::IsNullOrWhiteSpace($path) -or
        -not (Test-HwAgentCadenceAutoLoadDirectoryPath -Path $path)) { continue }
    $full = [System.IO.Path]::GetFullPath($path).TrimEnd("\")
    if ($seen.ContainsKey($full)) { continue }
    $seen[$full] = $true
    $paths.Add($full) | Out-Null
  }
  return $paths.ToArray()
}

function Test-HwAgentCadenceVendorAutoLoadDirectoryPath {
  param([Parameter(Mandatory=$true)][string]$Path)
  try {
    $full = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
    $suffix = "\tools\capture\tclscripts\capAutoLoad"
    return $full.EndsWith($suffix, [System.StringComparison]::OrdinalIgnoreCase)
  } catch { return $false }
}

function Get-HwAgentCadenceCleanupAutoLoadDirs {
  $candidates = @()
  $candidates += @(Get-HwAgentManagedCadenceAutoLoadDirs)
  $candidates += @(Find-CadenceVendorAutoLoadDirs)

  $paths = New-Object System.Collections.Generic.List[string]
  $seen = @{}
  foreach ($candidate in $candidates) {
    $path = [string]$candidate
    if ([string]::IsNullOrWhiteSpace($path)) { continue }
    if (-not (Test-HwAgentCadenceAutoLoadDirectoryPath -Path $path) -and
        -not (Test-HwAgentCadenceVendorAutoLoadDirectoryPath -Path $path)) { continue }
    $full = [System.IO.Path]::GetFullPath($path).TrimEnd("\")
    if ($seen.ContainsKey($full)) { continue }
    $seen[$full] = $true
    $paths.Add($full) | Out-Null
  }
  return $paths.ToArray()
}

function Set-HwAgentCadenceIntegrationState {
  param(
    [Parameter(Mandatory=$true)][bool]$Enabled,
    [AllowEmptyCollection()][string[]]$LoaderPaths = @()
  )
  $statePath = Get-HwAgentCadenceStatePath
  $stateDir = Split-Path -Parent $statePath
  New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
  $paths = New-Object System.Collections.Generic.List[string]
  $seen = @{}
  foreach ($path in $LoaderPaths) {
    if ([string]::IsNullOrWhiteSpace($path) -or -not (Test-HwAgentCadenceAutoLoadDirectoryPath -Path $path)) { continue }
    $full = [System.IO.Path]::GetFullPath($path).TrimEnd("\")
    if (-not $seen.ContainsKey($full)) {
      $seen[$full] = $true
      $paths.Add($full) | Out-Null
    }
  }
  $temp = Join-Path $stateDir ("cadence_integration." + [guid]::NewGuid().ToString("N") + ".tmp")
  [pscustomobject]@{
    schema_version = 2
    enabled = $Enabled
    loader_paths = $paths.ToArray()
    updated_at = (Get-Date).ToString("o")
  } | ConvertTo-Json | Set-Content -LiteralPath $temp -Encoding UTF8
  Move-Item -LiteralPath $temp -Destination $statePath -Force
  return $statePath
}

function Disable-HwAgentVendorAutoLoadScripts {
  param([Parameter(Mandatory=$true)][string]$VendorAutoLoadDir)
  # Lifecycle V2 never mutates vendor autoload scripts. The no-op remains as a
  # compatibility API for older callers while making ownership explicit.
  return @()
}

function Get-HwAgentAutoLoadArchiveRoot {
  param([Parameter(Mandatory=$true)][string]$AutoLoadDir)
  return (Join-Path (Split-Path -Parent $AutoLoadDir) "_hwagent_disabled_autoload_backups")
}

function Get-HwAgentAutoLoadBackupDirs {
  param([Parameter(Mandatory=$true)][string]$Dir)
  $backupDirs = New-Object System.Collections.Generic.List[System.IO.DirectoryInfo]
  if (Test-Path -LiteralPath $Dir) {
    foreach ($backup in Get-ChildItem -LiteralPath $Dir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "_disabled_hwagent_loader_*" -or $_.Name -like "_disabled_custom_scripts_*" }) {
      $backupDirs.Add($backup) | Out-Null
    }
  }

  $archiveRoot = Get-HwAgentAutoLoadArchiveRoot -AutoLoadDir $Dir
  if (Test-Path -LiteralPath $archiveRoot) {
    foreach ($backup in Get-ChildItem -LiteralPath $archiveRoot -Directory -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "_disabled_hwagent_loader_*" -or $_.Name -like "_disabled_custom_scripts_*" }) {
      $backupDirs.Add($backup) | Out-Null
    }
  }
  return $backupDirs.ToArray()
}

function Remove-HwAgentDirectoryIfEmpty {
  param([Parameter(Mandatory=$true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return $false }
  if (@(Get-ChildItem -LiteralPath $Path -Force -ErrorAction SilentlyContinue).Count -ne 0) { return $false }
  Remove-Item -LiteralPath $Path -Force
  return $true
}

function Move-HwAgentAutoLoadBackupDirs {
  param([Parameter(Mandatory=$true)][string]$AutoLoadDir)
  if (-not (Test-Path -LiteralPath $AutoLoadDir)) { return @() }

  $archiveRoot = Get-HwAgentAutoLoadArchiveRoot -AutoLoadDir $AutoLoadDir
  $archive = Join-Path $archiveRoot (Get-Date -Format yyyyMMdd_HHmmss)
  $moved = @()

  Get-ChildItem -LiteralPath $AutoLoadDir -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "_disabled_hwagent_loader_*" -or $_.Name -like "_disabled_custom_scripts_*" } |
    ForEach-Object {
      New-Item -ItemType Directory -Force -Path $archive | Out-Null
      $dest = Join-Path $archive $_.Name
      if (Test-Path -LiteralPath $dest) {
        $dest = Join-Path $archive ($_.Name + "_" + [System.Guid]::NewGuid().ToString("N"))
      }
      Move-Item -LiteralPath $_.FullName -Destination $dest -Force
      $moved += $dest
    }
  return $moved
}

function Restore-HwAgentAutoLoadBackupDirs {
  # Restore direct and archived backups. A target collision is left in its
  # backup directory so third-party content is never discarded during detach.
  param([Parameter(Mandatory=$true)][string]$Dir)
  if (-not (Test-Path -LiteralPath $Dir)) { return 0 }
  $count = 0
  $archiveRoot = Get-HwAgentAutoLoadArchiveRoot -AutoLoadDir $Dir
  $backupDirs = @(Get-HwAgentAutoLoadBackupDirs -Dir $Dir)
  foreach ($backup in $backupDirs) {
    if (-not (Test-Path -LiteralPath $backup.FullName)) { continue }
    foreach ($f in Get-ChildItem -LiteralPath $backup.FullName -File -Recurse -ErrorAction SilentlyContinue) {
      $relativePath = $f.FullName.Substring($backup.FullName.Length).TrimStart("\\")
      # Never remove an unknown loader just because it shares the legacy name.
      if ($relativePath -ieq "iac_bom_tool.tcl") {
        if (Test-HwAgentOwnedCadenceLoader -LoaderPath $f.FullName) {
          Remove-Item -LiteralPath $f.FullName -Force
        } else {
          Write-Warning ("Preserving unowned loader backup: " + $f.FullName)
        }
        continue
      }
      $target = Join-Path $Dir $relativePath
      if (Test-Path -LiteralPath $target) {
        Write-Warning ("Keeping archived third-party script because target already exists: " + $target)
        continue
      }
      $targetParent = Split-Path -Parent $target
      New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
      Move-Item -Force -LiteralPath $f.FullName -Destination $target
      $count++
    }
    Remove-HwAgentDirectoryIfEmpty -Path $backup.FullName | Out-Null
  }

  # Archive folders are HWAgent-owned. Remove only empty hierarchy nodes after
  # every eligible third-party file has moved back to the user's autoload dir.
  if (Test-Path -LiteralPath $archiveRoot) {
    Get-ChildItem -LiteralPath $archiveRoot -Directory -Recurse -ErrorAction SilentlyContinue |
      Sort-Object { $_.FullName.Length } -Descending |
      ForEach-Object { Remove-HwAgentDirectoryIfEmpty -Path $_.FullName | Out-Null }
    Remove-HwAgentDirectoryIfEmpty -Path $archiveRoot | Out-Null
  }
  return $count
}

function Get-HwAgentCadenceArtifactItems {
  param([Parameter(Mandatory=$true)][string]$AutoLoadDir)
  if (-not (Test-Path -LiteralPath $AutoLoadDir)) { return @() }
  $loader = Join-Path $AutoLoadDir $script:HwAgentCadenceLoaderName
  if (Test-HwAgentOwnedCadenceLoader -LoaderPath $loader) {
    return @(Get-Item -LiteralPath $loader -Force)
  }
  return @()
}

function Copy-HwAgentCadenceArtifacts {
  param(
    [Parameter(Mandatory=$true)][string]$AutoLoadDir,
    [Parameter(Mandatory=$true)][string]$Destination
  )
  New-Item -ItemType Directory -Force -Path $Destination | Out-Null
  foreach ($item in Get-HwAgentCadenceArtifactItems -AutoLoadDir $AutoLoadDir) {
    Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $Destination $item.Name) -Recurse -Force
  }
}

function Remove-HwAgentCadenceArtifacts {
  param([Parameter(Mandatory=$true)][string]$AutoLoadDir)
  foreach ($item in Get-HwAgentCadenceArtifactItems -AutoLoadDir $AutoLoadDir) {
    Remove-Item -LiteralPath $item.FullName -Recurse -Force
  }
}

function Start-HwAgentCadenceDeploymentTransaction {
  param([Parameter(Mandatory=$true)][AllowEmptyCollection()][string[]]$AutoLoadDirs)
  $snapshotRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("insta360_hw_cadence_" + [System.Guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path $snapshotRoot | Out-Null
  $entries = @()
  $seen = @{}
  $index = 0

  foreach ($dir in $AutoLoadDirs) {
    if ([string]::IsNullOrWhiteSpace($dir)) { continue }
    $fullDir = if (Test-Path -LiteralPath $dir) { (Resolve-Path -LiteralPath $dir).Path } else { $dir.TrimEnd("\\") }
    if ($seen.ContainsKey($fullDir)) { continue }
    $seen[$fullDir] = $true

    $entryRoot = Join-Path $snapshotRoot ("entry_" + $index)
    $artifactRoot = Join-Path $entryRoot "artifacts"
    $archiveRoot = Get-HwAgentAutoLoadArchiveRoot -AutoLoadDir $fullDir
    $dirExisted = Test-Path -LiteralPath $fullDir
    $archiveExisted = Test-Path -LiteralPath $archiveRoot
    if ($dirExisted) {
      Copy-HwAgentCadenceArtifacts -AutoLoadDir $fullDir -Destination $artifactRoot
    } else {
      New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
    }
    if ($archiveExisted) {
      $archiveSnapshot = Join-Path $entryRoot "archive"
      New-Item -ItemType Directory -Force -Path $archiveSnapshot | Out-Null
      Get-ChildItem -LiteralPath $archiveRoot -Force -ErrorAction SilentlyContinue |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $archiveSnapshot $_.Name) -Recurse -Force }
    }
    $entries += [pscustomobject]@{
      directory = $fullDir
      directory_existed = [bool]$dirExisted
      archive_root = $archiveRoot
      archive_existed = [bool]$archiveExisted
      entry_root = $entryRoot
    }
    $index++
  }
  $statePath = Get-HwAgentCadenceStatePath
  $stateExisted = Test-Path -LiteralPath $statePath -PathType Leaf
  if ($stateExisted) {
    Copy-Item -LiteralPath $statePath -Destination (Join-Path $snapshotRoot "cadence_integration.json") -Force
  }
  [ordered]@{
    schema = 2
    state_path = $statePath
    state_existed = [bool]$stateExisted
    entries = @($entries)
  } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $snapshotRoot "manifest.json") -Encoding UTF8
  return $snapshotRoot
}

function Restore-HwAgentCadenceDeploymentTransaction {
  param([Parameter(Mandatory=$true)][string]$SnapshotRoot)
  $manifestPath = Join-Path $SnapshotRoot "manifest.json"
  if (-not (Test-Path -LiteralPath $manifestPath)) { throw "Cadence rollback manifest is missing: $manifestPath" }
  $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $isSchemaTwo = $null -ne $manifest.PSObject.Properties["entries"]
  $entries = if ($isSchemaTwo) { @($manifest.entries) } else { @($manifest) }
  foreach ($entry in $entries) {
    $dir = [string]$entry.directory
    Remove-HwAgentCadenceArtifacts -AutoLoadDir $dir
    $artifactRoot = Join-Path ([string]$entry.entry_root) "artifacts"
    if (Test-Path -LiteralPath $artifactRoot) {
      New-Item -ItemType Directory -Force -Path $dir | Out-Null
      Get-ChildItem -LiteralPath $artifactRoot -Force -ErrorAction SilentlyContinue |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $dir $_.Name) -Recurse -Force }
    }
    if (-not [bool]$entry.directory_existed) {
      Remove-HwAgentDirectoryIfEmpty -Path $dir | Out-Null
    }

    $archiveRoot = [string]$entry.archive_root
    if (Test-Path -LiteralPath $archiveRoot) {
      Remove-Item -LiteralPath $archiveRoot -Recurse -Force
    }
    $archiveSnapshot = Join-Path ([string]$entry.entry_root) "archive"
    if ([bool]$entry.archive_existed -and (Test-Path -LiteralPath $archiveSnapshot)) {
      New-Item -ItemType Directory -Force -Path $archiveRoot | Out-Null
      Get-ChildItem -LiteralPath $archiveSnapshot -Force -ErrorAction SilentlyContinue |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $archiveRoot $_.Name) -Recurse -Force }
    }
  }
  if ($isSchemaTwo) {
    $statePath = Get-HwAgentCadenceStatePath
    if (-not [string]::IsNullOrWhiteSpace([string]$manifest.state_path)) {
      $recordedStatePath = [System.IO.Path]::GetFullPath([string]$manifest.state_path).TrimEnd("\")
      $expectedStatePath = [System.IO.Path]::GetFullPath($statePath).TrimEnd("\")
      if ($recordedStatePath -ine $expectedStatePath) {
        throw "Cadence rollback state path does not match the current user state."
      }
    }
    $stateSnapshot = Join-Path $SnapshotRoot "cadence_integration.json"
    if ([bool]$manifest.state_existed) {
      if (-not (Test-Path -LiteralPath $stateSnapshot -PathType Leaf)) {
        throw "Cadence rollback state snapshot is missing."
      }
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $statePath) | Out-Null
      Copy-Item -LiteralPath $stateSnapshot -Destination $statePath -Force
    } else {
      Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
    }
  }
}

function Complete-HwAgentCadenceDeploymentTransaction {
  param([Parameter(Mandatory=$true)][string]$SnapshotRoot)
  if (Test-Path -LiteralPath $SnapshotRoot) {
    Remove-Item -LiteralPath $SnapshotRoot -Recurse -Force
  }
}
