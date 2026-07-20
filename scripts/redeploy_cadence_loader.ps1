param(
  [string]$CaptureAutoLoadDir = "",
  [switch]$Force,
  [switch]$RespectUserRemoval
)

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"

function Get-Text {
  param([Parameter(Mandatory=$true)][string]$Base64)
  return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Base64))
}

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
. (Join-Path $Root "scripts\lib\Paths.ps1")
. (Join-Path $Root "scripts\lib\Cadence.ps1")
. (Join-Path $Root "scripts\lib\TclScripts.ps1")

$Root = Get-HwAgentRoot -StartPath $Root
if ($RespectUserRemoval -and -not (Test-HwAgentCadenceIntegrationEnabled)) {
  Write-Host "Cadence integration remains disabled by user choice."
  exit 0
}
$Python = Find-Python -Root $Root
$AutoLoadDirs = @()
if ($CaptureAutoLoadDir) {
  $AutoLoadDirs += $CaptureAutoLoadDir
} else {
  $AutoLoadDirs += Find-CadenceLoaderInstallDirs
}
$managedDirs = New-Object System.Collections.Generic.List[string]
foreach ($dir in @($AutoLoadDirs + (Get-HwAgentRecordedCadenceAutoLoadDirs))) {
  if ([string]::IsNullOrWhiteSpace($dir)) { continue }
  $full = [System.IO.Path]::GetFullPath($dir).TrimEnd("\")
  if (-not ($managedDirs | Where-Object { $_ -ieq $full })) { $managedDirs.Add($full) | Out-Null }
}
$AutoLoadDirs = @($managedDirs.ToArray())

foreach ($autoLoadDir in $AutoLoadDirs) {
  Move-HwAgentAutoLoadBackupDirs -AutoLoadDir $autoLoadDir | Out-Null
}
$installedLoaders = @(Install-CadenceLoader -ToolRoot $Root -PythonPath $Python -AutoLoadDirs $AutoLoadDirs)
$installedDirs = @($installedLoaders | ForEach-Object { Split-Path -Parent $_ })
Update-HwAgentCadenceOwnershipManifest -LoaderPaths $installedLoaders | Out-Null
Set-HwAgentCadenceIntegrationState -Enabled:$true -LoaderPaths $installedDirs | Out-Null
foreach ($loader in $installedLoaders) { Write-Host ("__HWAGENT_CADENCE_LOADER__ " + $loader) }
Write-Host (Get-Text "Q2FkZW5jZSDoj5zljZXlt7Lph43mlrDpg6jnvbLjgII=")
