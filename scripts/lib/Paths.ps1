$ErrorActionPreference = "Stop"

function Get-HwAgentText {
  param([Parameter(Mandatory=$true)][string]$Base64)
  return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Base64))
}

function Get-HwAgentRoot {
  param([string]$StartPath = $PSScriptRoot)
  $path = Resolve-Path -LiteralPath $StartPath
  $item = Get-Item -LiteralPath $path
  if (-not $item.PSIsContainer) { $item = $item.Directory }
  while ($item) {
    if ((Test-Path -LiteralPath (Join-Path $item.FullName "app\backend\suite_app.py")) -and
        (Test-Path -LiteralPath (Join-Path $item.FullName "launch_tool_suite.ps1"))) {
      return $item.FullName
    }
    $item = $item.Parent
  }
  throw (Get-HwAgentText "5pyq5om+5Yiw56Gs5Lu25pWI546H5bel5YW36ZuG5qC555uu5b2V")
}

function Find-Python {
  param([string]$Root = (Get-HwAgentRoot))
  $candidates = @(
    (Join-Path $Root "runtime\python\python.exe"),
    (Join-Path $Root ".venv\Scripts\python.exe"),
    (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")
  )
  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
  }
  $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  throw (Get-HwAgentText "5pyq5om+5YiwIFB5dGhvbu+8jOivt+WFiOWuieijhSBQeXRob24gMyDmiJbphY3nva4gY29uZmlnL2xvY2FsLmpzb24=")
}

function Find-Git {
  $cmd = Get-Command git.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

function Find-CadenceAutoLoadDirs {
  $known = @(
    "D:\CADENCE\Cadence\SPB_Data",
    "C:\Cadence\Cadence\SPB_Data",
    "C:\Cadence\SPB_Data",
    "D:\Cadence\SPB_Data"
  )
  $candidates = New-Object System.Collections.Generic.List[string]
  $seen = @{}
  foreach ($candidate in @($env:SPB_DATA, $env:CDS_DATA, $env:HOME) + $known) {
    if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
    try { $full = [System.IO.Path]::GetFullPath($candidate).TrimEnd("\") } catch { continue }
    if (-not $seen.ContainsKey($full)) {
      $seen[$full] = $true
      $candidates.Add($full) | Out-Null
    }
  }

  $base = ""
  foreach ($candidate in $candidates) {
    $captureConfig = Join-Path $candidate "cdssetup\OrCAD_Capture"
    if (Test-Path -LiteralPath $captureConfig -PathType Container) {
      $base = $candidate
      break
    }
  }
  if ([string]::IsNullOrWhiteSpace($base) -and $candidates.Count -gt 0) {
    $base = $candidates[0]
  }
  if ([string]::IsNullOrWhiteSpace($base) -and -not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
    $base = [System.IO.Path]::GetFullPath($env:USERPROFILE).TrimEnd("\")
  }
  if ([string]::IsNullOrWhiteSpace($base)) { return @() }
  return @([System.IO.Path]::GetFullPath((Join-Path $base "cdssetup\OrCAD_Capture\tclscripts\capAutoLoad")))
}

function Find-CadenceVendorAutoLoadDirs {
  $dirs = New-Object System.Collections.Generic.List[string]
  $roots = @(
    "C:\Cadence",
    "D:\Cadence",
    "D:\CADENCE",
    "C:\Cadence\Cadence",
    "D:\Cadence\Cadence",
    "D:\CADENCE\Cadence"
  )
  foreach ($root in $roots) {
    if (-not $root -or -not (Test-Path -LiteralPath $root)) { continue }
    foreach ($spb in Get-ChildItem -LiteralPath $root -Directory -Filter "SPB_*" -ErrorAction SilentlyContinue) {
      $dir = Join-Path $spb.FullName "tools\capture\tclscripts\capAutoLoad"
      if ($dir -and (Test-Path -LiteralPath $dir) -and -not $dirs.Contains($dir)) {
        $dirs.Add($dir) | Out-Null
      }
    }
  }
  return $dirs.ToArray()
}

function Find-CadenceLoaderInstallDirs {
  return @(Find-CadenceAutoLoadDirs)
}

function Ensure-Directory {
  param([Parameter(Mandatory=$true)][string]$Path)
  New-Item -ItemType Directory -Force -Path $Path | Out-Null
  return (Resolve-Path -LiteralPath $Path).Path
}
