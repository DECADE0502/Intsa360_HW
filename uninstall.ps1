param(
  [string]$InstallDir = "",
  [string]$CaptureAutoLoadDir = "",
  [switch]$Force,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Remove-IfExists {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [switch]$Recurse
  )
  if (-not (Test-Path -LiteralPath $Path)) { return }
  if ($DryRun) {
    Write-Host ("DRYRUN remove " + $Path)
    return
  }
  if ($Recurse) {
    Remove-Item -LiteralPath $Path -Recurse -Force
  } else {
    Remove-Item -LiteralPath $Path -Force
  }
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptRoot "scripts\lib\Paths.ps1")

$Root = if ($InstallDir) { $InstallDir } else { Get-HwAgentRoot -StartPath $ScriptRoot }
if (-not (Test-Path -LiteralPath $Root)) {
  Write-Host ("Install directory does not exist: " + $Root)
  exit 0
}

if (-not $Force -and -not $DryRun) {
  throw "Add -Force to uninstall, or -DryRun to preview."
}

$autoLoadDirs = @()
if ($CaptureAutoLoadDir) {
  $autoLoadDirs += $CaptureAutoLoadDir
} else {
  $autoLoadDirs += Find-CadenceAutoLoadDirs
}

foreach ($dir in $autoLoadDirs) {
  if (-not $dir) { continue }
  Remove-IfExists -Path (Join-Path $dir "iac_bom_tool.tcl")
}

Remove-IfExists -Path $Root -Recurse
Write-Host "Uninstall complete."
