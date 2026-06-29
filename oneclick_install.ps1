param([switch]$Silent, [switch]$NoStart)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Insta360_HW Setup"

function Say {
  param(
    [Parameter(Mandatory=$true)][string]$Text,
    [ConsoleColor]$Color = [ConsoleColor]::White
  )
  if (-not $Silent) {
    Write-Host $Text -ForegroundColor $Color
  }
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallScript = Join-Path $ScriptDir "install.ps1"
$Manifest = Join-Path $ScriptDir "install_manifest.json"
$FrontendIndex = Join-Path $ScriptDir "app\frontend\index.html"

Say "==========================================" Cyan
Say "  Insta360_HW Setup" Cyan
Say "==========================================" Cyan
Say ""

Say "[1/3] Checking package files..."
if (-not (Test-Path -LiteralPath $InstallScript)) {
  Say "  [X] install.ps1 was not found. The package is incomplete." Red
  exit 1
}
if (-not (Test-Path -LiteralPath $FrontendIndex)) {
  Say "  [X] Built frontend was not found. Rebuild the release package." Red
  exit 1
}
if (-not (Test-Path -LiteralPath $Manifest)) {
  Say "  [!] install_manifest.json was not found. Continuing with legacy package." Yellow
} else {
  Say "  [OK] Runtime manifest found." Green
}
Say ""

Say "[2/3] Initializing local configuration and Cadence integration..."
$installArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $InstallScript)
if ($NoStart) { $installArgs += "-NoStart" }
& powershell @installArgs
if ($LASTEXITCODE -ne 0) {
  Say ""
  Say "  [X] Install initialization failed. Check the log above." Red
  exit 1
}

Say ""
Say "[3/3] Setup complete."
Say "==========================================" Cyan
Say "  Start from: Insta360_HW.exe" Green
Say "  Open System Status in the platform for self-check and repair." Yellow
Say "==========================================" Cyan
