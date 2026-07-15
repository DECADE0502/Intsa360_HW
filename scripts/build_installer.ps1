param(
  [Parameter(Mandatory=$true)][string]$ReleaseDir,
  [Parameter(Mandatory=$true)][string]$OutputDir,
  [string]$InnoCompiler = "",
  [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$Iss = Join-Path $Root "HWAgent_Setup.iss"
$ReleaseDir = [System.IO.Path]::GetFullPath($ReleaseDir)
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
if ([string]::IsNullOrWhiteSpace($Version)) {
  $Version = (Get-Content -LiteralPath (Join-Path $ReleaseDir "VERSION") -Raw -Encoding UTF8).Trim()
}

function Find-InnoCompiler {
  param([string]$ExplicitPath = "")
  if ($ExplicitPath -and (Test-Path -LiteralPath $ExplicitPath -PathType Leaf)) {
    return (Resolve-Path -LiteralPath $ExplicitPath).Path
  }
  $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
  )
  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }
  throw "ISCC.exe was not found. Install Inno Setup 6 or pass -InnoCompiler <path>."
}

if (-not (Test-Path -LiteralPath $Iss -PathType Leaf)) { throw "HWAgent_Setup.iss not found: $Iss" }
$identityPath = Join-Path $ReleaseDir "install_manifest.json"
if (-not (Test-Path -LiteralPath $identityPath -PathType Leaf)) { throw "Runtime identity is missing: $identityPath" }
$identity = Get-Content -LiteralPath $identityPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([int]$identity.schema -ne 3 -or [string]$identity.layout -ne "runtime-v3" -or
    [string]$identity.product -ne "Insta360_HW" -or [string]$identity.version -cne $Version) {
  throw "Setup accepts only a matching runtime-v3 payload."
}
$icon = Join-Path $ReleaseDir "app\frontend\assets\insta360_icon.ico"
if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) { throw "Setup icon is missing: $icon" }
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$output = Join-Path $OutputDir "Insta360_HW_Setup.exe"
Remove-Item -LiteralPath $output -Force -ErrorAction SilentlyContinue
$iscc = Find-InnoCompiler -ExplicitPath $InnoCompiler

Write-Host "Compiling Setup from the already validated local runtime..." -ForegroundColor Cyan
& $iscc `
  ("/DMyAppVersion=" + $Version) `
  ("/DReleaseDir=" + $ReleaseDir) `
  ("/DIconFile=" + $icon) `
  ("/DInstallerOutputDir=" + $OutputDir) `
  $Iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed." }
if (-not (Test-Path -LiteralPath $output -PathType Leaf)) { throw "Installer was not created: $output" }
Write-Host "Setup ready: $output" -ForegroundColor Green
