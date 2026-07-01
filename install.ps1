param(
  [string]$InstallDir = "",
  [string]$CaptureAutoLoadDir = "",
  [switch]$NoStart
)

$ErrorActionPreference = "Stop"

function Get-Text {
  param([Parameter(Mandatory=$true)][string]$Base64)
  return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Base64))
}

$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallRoot = if ($InstallDir) { $InstallDir } else { $SourceRoot }

. (Join-Path $SourceRoot "scripts\lib\Paths.ps1")
. (Join-Path $SourceRoot "scripts\lib\Cadence.ps1")
. (Join-Path $SourceRoot "scripts\lib\Service.ps1")
. (Join-Path $SourceRoot "scripts\lib\TclScripts.ps1")

Write-Host (Get-Text "5byA5aeL5a6J6KOF56Gs5Lu25pWI546H5bel5YW36ZuGLi4u")
$SourceRoot = Get-HwAgentRoot -StartPath $SourceRoot

$sourceResolved = (Resolve-Path -LiteralPath $SourceRoot).Path
$installResolved = $null
if (Test-Path -LiteralPath $InstallRoot) {
  $installResolved = (Resolve-Path -LiteralPath $InstallRoot).Path
}

if ($installResolved -ne $sourceResolved) {
  New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
  robocopy $SourceRoot $InstallRoot /MIR /XD ".git" "frontend\node_modules" "frontend\dist" "data" /XF "config\local.json" | Out-Null
  if ($LASTEXITCODE -ge 8) {
    throw ((Get-Text "5aSN5Yi25a6J6KOF5paH5Lu25aSx6LSl77yMcm9ib2NvcHkgZXhpdCBjb2RlOiA=") + $LASTEXITCODE)
  }
}

$InstallRoot = Get-HwAgentRoot -StartPath $InstallRoot
$Python = $null
try {
  $Python = Find-Python -Root $InstallRoot
  & $Python -c "import openpyxl; print('openpyxl', openpyxl.__version__)"
  if ($LASTEXITCODE -ne 0) { throw "openpyxl import verification failed after install" }
} catch {
  Write-Host ("Python lookup failed: " + $_.Exception.Message)
  throw
}

$ConfigDir = Join-Path $InstallRoot "config"
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot "plugins\system") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot "plugins\user\scripts") | Out-Null
$LocalConfig = Join-Path $InstallRoot "config\local.json"
if (-not (Test-Path -LiteralPath $LocalConfig)) {
  $installDirJson = ConvertTo-Json -InputObject $InstallRoot -Compress
  "{`n  `"install_dir`": $installDirJson`n}" | Set-Content -LiteralPath $LocalConfig -Encoding UTF8
  Write-Host ((Get-Text "5bey5Yib5bu65pys5py66YWN572u77ya") + $LocalConfig)
} else {
  Write-Host ((Get-Text "5L+d55WZ5bey5pyJ5pys5py66YWN572u77ya") + $LocalConfig)
}

if ($Python) {
  foreach ($vendorAutoLoadDir in Find-CadenceVendorAutoLoadDirs) {
    Disable-HwAgentVendorAutoLoadScripts -VendorAutoLoadDir $vendorAutoLoadDir | Out-Null
  }

  $AutoLoadDirs = @()
  if ($CaptureAutoLoadDir) {
    $AutoLoadDirs += $CaptureAutoLoadDir
  } else {
    $AutoLoadDirs += Find-CadenceLoaderInstallDirs
  }
  foreach ($autoLoadDir in $AutoLoadDirs) {
    Move-HwAgentAutoLoadBackupDirs -AutoLoadDir $autoLoadDir | Out-Null
  }
  Install-CadenceLoader -ToolRoot $InstallRoot -PythonPath $Python -AutoLoadDirs $AutoLoadDirs | Out-Null
} else {
  Write-Host "Skipping Cadence loader deployment because Python is unavailable. Open System Status for repair guidance."
}

Write-Host (Get-Text "5a6J6KOF5a6M5oiQ44CC6K+36YeN5ZCvIE9yQ0FEIENhcHR1cmXvvIznhLblkI7miZPlvIAgQWNjZXNzb3JpZXMgLT4g56Gs5Lu25pWI546H5bel5YW36ZuG44CC")
