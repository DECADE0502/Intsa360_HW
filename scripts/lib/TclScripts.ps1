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
