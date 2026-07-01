param(
  [Parameter(Mandatory=$true)][string]$InstallDir
)
# Standalone Cadence-loader removal script. Unlike uninstall.ps1 -Mode Detach,
# this script MUST NOT touch platform services on port 8765 — it is invoked
# from the web UI by the running platform, so killing python on 8765 would
# kill the very process that spawned this script. Keep the scope tight:
# remove iac_bom_tool.tcl from every autoload dir and restore any vendor
# scripts install.ps1 had stashed under _disabled_*_*.
$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
. (Join-Path $scriptDir 'lib\Paths.ps1')
. (Join-Path $scriptDir 'lib\Cadence.ps1')
. (Join-Path $scriptDir 'lib\TclScripts.ps1')

Write-Host "__HWAGENT_CADENCE_REMOVE_STARTED__"

$autoLoadDirs = Find-CadenceLoaderInstallDirs
$removed = 0
$restored = 0

foreach ($dir in $autoLoadDirs) {
  if (-not $dir -or -not (Test-Path -LiteralPath $dir)) { continue }

  $loader = Join-Path $dir 'iac_bom_tool.tcl'
  if (Test-Path -LiteralPath $loader) {
    Remove-Item -Force -LiteralPath $loader
    Write-Host ("Removed: " + $loader)
    $removed++
  }

  $legacyBackup = Join-Path $dir 'iac_bom_tool_backup'
  if (Test-Path -LiteralPath $legacyBackup) {
    Remove-Item -Force -Recurse -LiteralPath $legacyBackup
    Write-Host ("Removed legacy backup: " + $legacyBackup)
  }

  # Restore vendor scripts that install.ps1 had disabled so the user's
  # Cadence environment matches its pre-install state after detach.
  $restoredHere = Restore-HwAgentAutoLoadBackupDirs -Dir $dir
  if ($restoredHere) { $restored += $restoredHere }
}

Write-Host ("Removed {0} loaders, restored {1} vendor scripts" -f $removed, $restored)
Write-Host "__HWAGENT_CADENCE_REMOVE_DONE__"
