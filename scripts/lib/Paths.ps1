$ErrorActionPreference = "Stop"

$cadenceDiscoveryLibrary = Join-Path $PSScriptRoot "CadenceDiscovery.ps1"
if (-not (Test-Path -LiteralPath $cadenceDiscoveryLibrary -PathType Leaf)) {
  throw "Cadence discovery library is missing: $cadenceDiscoveryLibrary"
}
. $cadenceDiscoveryLibrary

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

function Ensure-Directory {
  param([Parameter(Mandatory=$true)][string]$Path)
  New-Item -ItemType Directory -Force -Path $Path | Out-Null
  return (Resolve-Path -LiteralPath $Path).Path
}
