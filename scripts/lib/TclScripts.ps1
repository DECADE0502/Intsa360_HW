function Disable-HwAgentVendorAutoLoadScripts {
  param([Parameter(Mandatory=$true)][string]$VendorAutoLoadDir)
  if (-not (Test-Path -LiteralPath $VendorAutoLoadDir)) { return @() }

  $backup = Join-Path $VendorAutoLoadDir ("_disabled_custom_scripts_" + (Get-Date -Format yyyyMMdd))
  New-Item -ItemType Directory -Force -Path $backup | Out-Null

  $moved = @()
  Get-ChildItem -Path $VendorAutoLoadDir -File -Filter "orCAD_Enhanced_Tools_V*.tcl*" -ErrorAction SilentlyContinue |
    ForEach-Object {
      $dest = Join-Path $backup $_.Name
      Move-Item -LiteralPath $_.FullName -Destination $dest -Force
      $moved += $dest
    }
  return $moved
}

function Move-HwAgentAutoLoadBackupDirs {
  param([Parameter(Mandatory=$true)][string]$AutoLoadDir)
  if (-not (Test-Path -LiteralPath $AutoLoadDir)) { return @() }

  $parent = Split-Path -Parent $AutoLoadDir
  $archiveRoot = Join-Path $parent "_hwagent_disabled_autoload_backups"
  $stamp = Get-Date -Format yyyyMMdd_HHmmss
  $archive = Join-Path $archiveRoot $stamp
  $moved = @()

  Get-ChildItem -LiteralPath $AutoLoadDir -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "_disabled_hwagent_loader_*" -or $_.Name -like "_disabled_custom_scripts_*" } |
    ForEach-Object {
      New-Item -ItemType Directory -Force -Path $archive | Out-Null
      $dest = Join-Path $archive $_.Name
      Move-Item -LiteralPath $_.FullName -Destination $dest -Force
      $moved += $dest
    }
  return $moved
}

function Restore-HwAgentAutoLoadBackupDirs {
  # Reverse of Disable-HwAgentVendorAutoLoadScripts / the loader-backup dirs
  # created by install.ps1. When the user asks the platform to detach Cadence,
  # any vendor scripts that install had stashed under _disabled_*_* should be
  # moved back into place so the user's Cadence keeps working after detach.
  # Returns the count of files restored.
  param([Parameter(Mandatory=$true)][string]$Dir)
  if (-not (Test-Path -LiteralPath $Dir)) { return 0 }
  $count = 0
  $backupDirs = Get-ChildItem -LiteralPath $Dir -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -like "_disabled_hwagent_loader_*" -or $_.Name -like "_disabled_custom_scripts_*" }
  foreach ($backup in $backupDirs) {
    foreach ($f in Get-ChildItem -LiteralPath $backup.FullName -File -ErrorAction SilentlyContinue) {
      $target = Join-Path $Dir $f.Name
      if (-not (Test-Path -LiteralPath $target)) {
        Move-Item -Force -LiteralPath $f.FullName -Destination $target
        $count++
      }
    }
    # Remove the (now-empty or leftover) backup dir so it does not clutter
    # the autoload directory across future installs.
    Remove-Item -Force -Recurse -LiteralPath $backup.FullName -ErrorAction SilentlyContinue
  }
  return $count
}
