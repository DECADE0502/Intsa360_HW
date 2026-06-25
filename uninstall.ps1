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

function Stop-HwAgentServices {
  param([int[]]$Ports = (8765..8775))
  $stopped = @()
  foreach ($port in $Ports) {
    $conns = netstat -ano 2>$null | Select-String ":$port\s+.*LISTENING"
    foreach ($conn in $conns) {
      $parts = $conn.ToString() -split '\s+'
      $procId = $parts[-1].Trim()
      if ($procId -notmatch '^\d+$' -or $stopped -contains $procId) { continue }
      $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
      if ($proc -and $proc.ProcessName -like 'python*') {
        if ($DryRun) {
          Write-Host ("DRYRUN stop service PID " + $procId + " on port " + $port)
        } else {
          Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
        $stopped += $procId
      }
    }
  }
  return $stopped
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

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptRoot "scripts\lib\Paths.ps1")

$Root = if ($InstallDir) { $InstallDir } else { Get-HwAgentRoot -StartPath $ScriptRoot }
if (-not (Test-Path -LiteralPath $Root)) {
  Write-Host ("Install directory does not exist: " + $Root)
  exit 0
}
$Root = Assert-SafeInstallRoot -Path $Root

if (-not $Force -and -not $DryRun) {
  throw "Add -Force to uninstall, or -DryRun to preview."
}

Write-Host ("Uninstall mode: " + $Mode)

$stopped = Stop-HwAgentServices
if ($stopped.Count -gt 0) {
  Write-Host ("Stopped HWAgent service processes: " + ($stopped -join ", "))
}

$autoLoadDirs = @()
if ($CaptureAutoLoadDir) {
  $autoLoadDirs += $CaptureAutoLoadDir
} else {
  $autoLoadDirs += Find-CadenceAutoLoadDirs
}

$removedLoaders = Remove-CadenceLoader -AutoLoadDirs $autoLoadDirs
if ($removedLoaders.Count -gt 0) {
  Write-Host ("Removed Cadence loader artifacts: " + ($removedLoaders -join ", "))
}

if ($Mode -eq "Detach") {
  Write-Host "Detach complete. Platform files and user scripts were kept."
  exit 0
}

if (-not $DryRun) {
  Set-Location -LiteralPath ([System.IO.Path]::GetTempPath())
}
Remove-IfExists -Path $Root -Recurse
Write-Host "Full uninstall complete. Platform directory was removed."
