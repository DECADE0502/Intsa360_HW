$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
  $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
  if (-not $cmd) { throw "Python not found" }
  $Python = $cmd.Source
}

Push-Location $Root
try {
  & $Python -m unittest discover -s tests -v
  if ($LASTEXITCODE -ne 0) { throw "unittest failed" }

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
