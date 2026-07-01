param(
  [string]$CaptureAutoLoadDir = ""
)

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
$Python = Find-Python -Root $Root
$AutoLoadDirs = @()
if ($CaptureAutoLoadDir) {
  $AutoLoadDirs += $CaptureAutoLoadDir
} else {
  $AutoLoadDirs += Find-CadenceLoaderInstallDirs
}

foreach ($autoLoadDir in $AutoLoadDirs) {
  Move-HwAgentAutoLoadBackupDirs -AutoLoadDir $autoLoadDir | Out-Null
}
Install-CadenceLoader -ToolRoot $Root -PythonPath $Python -AutoLoadDirs $AutoLoadDirs | Out-Null
Write-Host (Get-Text "Q2FkZW5jZSDoj5zljZXlt7Lph43mlrDpg6jnvbLjgII=")
