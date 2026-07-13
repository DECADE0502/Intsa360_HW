param(
  [string]$InnoCompiler = "",
  [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $Root
$Iss = Join-Path $Root "HWAgent_Setup.iss"
$Output = Join-Path $RepoRoot "Insta360_HW_Setup.exe"
$Version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw -Encoding UTF8).Trim()

function Find-InnoCompiler {
  param([string]$ExplicitPath = "")
  if ($ExplicitPath -and (Test-Path -LiteralPath $ExplicitPath)) {
    return (Resolve-Path -LiteralPath $ExplicitPath).Path
  }

  $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }

  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 5\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 5\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 5\ISCC.exe")
  )
  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }

  throw "ISCC.exe was not found. Install Inno Setup 6 or pass -InnoCompiler <path>."
}

if (-not (Test-Path -LiteralPath $Iss)) {
  throw "HWAgent_Setup.iss not found: $Iss"
}

$releaseArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $ScriptDir "build_release.ps1"))
if ($SkipFrontend) { $releaseArgs += "-SkipFrontend" }
& powershell @releaseArgs
if ($LASTEXITCODE -ne 0) { throw "build_release.ps1 failed." }

$Iscc = Find-InnoCompiler -ExplicitPath $InnoCompiler
Write-Host "Using Inno Setup compiler: $Iscc"

if (Test-Path -LiteralPath $Output) {
  Remove-Item -LiteralPath $Output -Force
}

& $Iscc ("/DMyAppVersion=" + $Version) $Iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed." }

if (-not (Test-Path -LiteralPath $Output)) {
  throw "Installer was not created: $Output"
}

Write-Host "Installer ready: $Output"
