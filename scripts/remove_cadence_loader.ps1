param(
  [string]$InstallDir = "",
  [AllowEmptyCollection()][string[]]$AutoLoadDirs = @(),
  [switch]$SkipDiscovery
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Root = Split-Path -Parent $scriptDir
if ([string]::IsNullOrWhiteSpace($InstallDir)) { $InstallDir = $Root }
. (Join-Path $scriptDir "lib\Paths.ps1")
. (Join-Path $scriptDir "lib\Cadence.ps1")
. (Join-Path $scriptDir "lib\TclScripts.ps1")

Write-Host "__HWAGENT_CADENCE_REMOVE_STARTED__"

$autoLoadDirs = @(Get-HwAgentCadenceCleanupAutoLoadDirs -AdditionalPaths $AutoLoadDirs -SkipDiscovery:$SkipDiscovery)

$snapshot = Start-HwAgentCadenceDeploymentTransaction -AutoLoadDirs $autoLoadDirs
$removed = 0
$restored = 0
try {
  foreach ($dir in $autoLoadDirs) {
    if (-not (Test-Path -LiteralPath $dir -PathType Container)) { continue }
    $loader = Join-Path $dir "iac_bom_tool.tcl"
    if (Test-Path -LiteralPath $loader -PathType Leaf) {
      if (Remove-HwAgentOwnedCadenceLoader -AutoLoadDir $dir) {
        Write-Host ("Removed owned loader: " + $loader)
        $removed++
      } else {
        Write-Warning ("Preserving unowned loader: " + $loader)
      }
    }
    $restoredHere = Restore-HwAgentAutoLoadBackupDirs -Dir $dir
    if ($restoredHere) { $restored += $restoredHere }
  }
  Set-HwAgentCadenceIntegrationState -Enabled:$false -LoaderPaths @() | Out-Null
  Clear-HwAgentCadenceOwnershipManifest
  Complete-HwAgentCadenceDeploymentTransaction -SnapshotRoot $snapshot
} catch {
  try { Restore-HwAgentCadenceDeploymentTransaction -SnapshotRoot $snapshot } catch {}
  throw
}

Write-Host ("Removed {0} owned loaders, restored {1} archived vendor scripts" -f $removed, $restored)
Write-Host "__HWAGENT_CADENCE_REMOVE_DONE__"
