$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PythonCandidates = @(
  "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)
$cmd = Get-Command python.exe -ErrorAction SilentlyContinue
if ($cmd) { $PythonCandidates += $cmd.Source }

$Python = $null
foreach ($candidate in ($PythonCandidates | Select-Object -Unique)) {
  if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
  & $candidate -c "import pytest" 2>$null
  if ($LASTEXITCODE -eq 0) {
    $Python = $candidate
    break
  }
}
if (-not $Python) { throw "Python with pytest not found" }

Push-Location $Root
try {
  & $Python -m pytest -q
  if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

  & $Python -m py_compile app\backend\suite_app.py app\backend\update_api.py app\backend\tools\bom_process.py tools\bom\convert_cadence_bom.py
  if ($LASTEXITCODE -ne 0) { throw "py_compile failed" }

  if (Test-Path -LiteralPath "frontend\package.json") {
    Push-Location frontend
    try {
      npm run build
      if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
    } finally {
      Pop-Location
    }
  }

  $uiFiles = @()
  if (Test-Path -LiteralPath "frontend\src") {
    $uiFiles += Get-ChildItem -Path "frontend\src" -Include *.tsx,*.ts -Recurse
    $uiFiles += Get-Item "frontend\index.html"
  }
  $englishUiPattern = ">\s*(Upload|Download|Run|Update|Loading|Error|Settings|Tools|Cancel|Confirm|Save)\s*<"
  foreach ($file in $uiFiles) {
    $text = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8
    if ($text -match $englishUiPattern) { throw "English UI text found in $($file.FullName)" }
  }
  Write-Host "Verification passed."
} finally {
  Pop-Location
}
