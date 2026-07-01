param(
  [string]$InstallDir = "",
  [string]$CaptureAutoLoadDir = "",
  [ValidateSet("Detach", "Full")]
  [string]$Mode = "Full",
  [switch]$Force,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Assert-SafeInstallRoot {
  param([Parameter(Mandatory=$true)][string]$Path)
  $resolved = (Resolve-Path -LiteralPath $Path).Path.TrimEnd("\")
  $unsafe = @(
    [System.IO.Path]::GetPathRoot($resolved).TrimEnd("\"),
    $env:USERPROFILE.TrimEnd("\"),
    $env:SystemDrive.TrimEnd("\"),
    (Join-Path $env:SystemDrive "Windows").TrimEnd("\"),
    (Join-Path $env:SystemDrive "Program Files").TrimEnd("\"),
    (Join-Path $env:SystemDrive "Program Files (x86)").TrimEnd("\")
  ) | Where-Object { $_ }
  if ($unsafe -contains $resolved) {
    throw "Refusing to remove unsafe install root: $resolved"
  }
  return $resolved
}

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

function Remove-CadenceLoader {
  param([string[]]$AutoLoadDirs)
  $removed = @()
  foreach ($dir in $AutoLoadDirs) {
    if (-not $dir -or -not (Test-Path -LiteralPath $dir)) { continue }

    $loader = Join-Path $dir "iac_bom_tool.tcl"
    if (Test-Path -LiteralPath $loader) {
      Remove-IfExists -Path $loader
      $removed += $loader
    }

    $legacyBackup = Join-Path $dir "iac_bom_tool_backup"
    if (Test-Path -LiteralPath $legacyBackup) {
      Remove-IfExists -Path $legacyBackup -Recurse
      $removed += $legacyBackup
    }

    Get-ChildItem -LiteralPath $dir -Directory -Filter "_disabled_hwagent_loader_*" -ErrorAction SilentlyContinue |
      ForEach-Object {
        Remove-IfExists -Path $_.FullName -Recurse
        $removed += $_.FullName
      }
  }
  return $removed
}

function Mark-UninstallProgress {
  param(
    [Parameter(Mandatory=$true)][int]$Percent,
    [Parameter(Mandatory=$true)][string]$Step
  )
  Write-Host ("__HWAGENT_UNINSTALL_PROGRESS__ " + $Percent + " " + $Step)
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptRoot "scripts\lib\Paths.ps1")
. (Join-Path $ScriptRoot "scripts\lib\Service.ps1")

Write-Host "__HWAGENT_UNINSTALL_PROGRESS__ 10 Resolving install directory"
$Root = if ($InstallDir) { $InstallDir } else { Get-HwAgentRoot -StartPath $ScriptRoot }
if (-not (Test-Path -LiteralPath $Root)) {
  Write-Host ("Install directory does not exist: " + $Root)
  Write-Host "__HWAGENT_UNINSTALL_PROGRESS__ 100 Install directory already removed"
  Write-Host "__HWAGENT_UNINSTALL_DONE__"
  exit 0
}
$Root = Assert-SafeInstallRoot -Path $Root

if (-not $Force -and -not $DryRun) {
  throw "Add -Force to uninstall, or -DryRun to preview."
}

Write-Host ("Uninstall mode: " + $Mode)

Mark-UninstallProgress 25 "Stopping platform services"
$stopped = Stop-HwAgentServicesByPort -DryRun:$DryRun
if ($stopped.Count -gt 0) {
  Write-Host ("Stopped HWAgent service processes: " + ($stopped -join ", "))
}

$autoLoadDirs = @()
if ($CaptureAutoLoadDir) {
  $autoLoadDirs += $CaptureAutoLoadDir
} else {
  $autoLoadDirs += Find-CadenceLoaderInstallDirs
}

Write-Host "__HWAGENT_UNINSTALL_PROGRESS__ 40 Removing Cadence integration"
$removedLoaders = Remove-CadenceLoader -AutoLoadDirs $autoLoadDirs
if ($removedLoaders.Count -gt 0) {
  Write-Host ("Removed Cadence loader artifacts: " + ($removedLoaders -join ", "))
}

if ($Mode -eq "Detach") {
  Write-Host "__HWAGENT_UNINSTALL_PROGRESS__ 100 Cadence integration removed"
  Write-Host "Detach complete. Platform files and user scripts were kept."
  Write-Host "__HWAGENT_UNINSTALL_DONE__"
  exit 0
}

if (-not $DryRun) {
  Set-Location -LiteralPath ([System.IO.Path]::GetTempPath())
}
Mark-UninstallProgress 75 "Removing platform files"
Remove-IfExists -Path $Root -Recurse
Write-Host "__HWAGENT_UNINSTALL_PROGRESS__ 100 Platform files removed"
Write-Host "Full uninstall complete. Platform directory was removed."
Write-Host "__HWAGENT_UNINSTALL_DONE__"
