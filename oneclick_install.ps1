param([switch]$Silent, [switch]$NoStart)

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "HWAgent Installer"

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

Say "==========================================" Cyan
Say "  Insta360_HW Installer" Cyan
Say "==========================================" Cyan
Say ""

Say "[1/4] Checking Python..."
$pythonExe = $null

$pythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue
if ($pythonCmd) {
  $pythonExe = "python"
  Say ("  " + (& python --version 2>&1)) Green
}

if (-not $pythonExe) {
  $codexPy = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  if (Test-Path -LiteralPath $codexPy) {
    $pythonExe = $codexPy
    Say ("  Found bundled Python: " + $codexPy) Yellow
  }
}

if (-not $pythonExe) {
  $venvPy = Join-Path $ScriptDir ".venv\Scripts\python.exe"
  if (Test-Path -LiteralPath $venvPy) {
    $pythonExe = $venvPy
    Say ("  Found virtualenv Python: " + $venvPy) Yellow
  }
}

if (-not $pythonExe) {
  Say "  [X] Python was not found. Please install Python 3 first." Red
  Say "      Download: https://www.python.org/downloads/" Gray
  Say "      Enable: Add Python to PATH" Gray
  exit 1
}
Say "  [OK] Python is ready." Green
Say ""

Say "[2/4] Checking openpyxl..."
& $pythonExe -c "import openpyxl" 2>$null
if ($LASTEXITCODE -ne 0) {
  Say "  [!] openpyxl is missing. Installing..." Yellow
  & $pythonExe -m pip install openpyxl
  if ($LASTEXITCODE -ne 0) {
    Say "  [X] Failed to install openpyxl. Run manually: pip install openpyxl" Red
    exit 1
  }
}
Say "  [OK] openpyxl is ready." Green
Say ""

Say "[3/4] Checking Node.js (optional)..."
$nodeCmd = Get-Command node.exe -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
  Say "  [i] Node.js was not found. Prebuilt frontend will be used." Yellow
} else {
  Say ("  " + (& node --version 2>&1)) Green
  Say "  [OK] Node.js is ready." Green
}
Say ""

Say "[4/4] Running installer..."
Say "==========================================" Gray
Say ""

if (-not (Test-Path -LiteralPath $InstallScript)) {
  Say "  [X] install.ps1 was not found. The package is incomplete." Red
  exit 1
}

$installArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $InstallScript)
if ($NoStart) { $installArgs += "-NoStart" }
& powershell @installArgs
if ($LASTEXITCODE -ne 0) {
  Say ""
  Say "  [X] Install failed. Check the log above." Red
  exit 1
}

Say ""
Say "==========================================" Cyan
Say "  Install complete." Green
Say ""
Say "  Start from: Insta360_HW.exe" Gray
Say "  Restart OrCAD Capture to load the insta360_HW menu." Yellow
Say "==========================================" Cyan
