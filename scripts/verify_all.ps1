param(
  [string[]]$PythonCandidates = @(),
  [switch]$ProbeOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Test-PytestPython {
  param([Parameter(Mandatory=$true)][string]$Candidate)
  if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $false }

  $process = $null
  try {
    $process = Start-Process -FilePath $Candidate -ArgumentList '-c "import pytest"' -Wait -PassThru -WindowStyle Hidden
    return ($process.ExitCode -eq 0)
  } catch {
    return $false
  } finally {
    if ($process) { $process.Dispose() }
  }
}

function Find-PytestPython {
  param([Parameter(Mandatory=$true)][string[]]$Candidates)
  foreach ($candidate in ($Candidates | Select-Object -Unique)) {
    if (Test-PytestPython -Candidate $candidate) { return $candidate }
  }
  throw "Python with pytest not found"
}

if ($PythonCandidates.Count -eq 0) {
  $PythonCandidates = @(
    "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  )
  $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
  if ($cmd) { $PythonCandidates += $cmd.Source }
}

$Python = Find-PytestPython -Candidates $PythonCandidates
if ($ProbeOnly) {
  Write-Output $Python
  return
}

$OriginalTemp = $env:TEMP
$OriginalTmp = $env:TMP
$LocalAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
if (-not $LocalAppData) { throw "Local application data directory not found" }
$VerifyTempRoot = Join-Path $LocalAppData ("Temp\ihv\" + [Guid]::NewGuid().ToString("N").Substring(0, 12))
New-Item -ItemType Directory -Force -Path $VerifyTempRoot | Out-Null
$VerifyTempRoot = (Resolve-Path -LiteralPath $VerifyTempRoot).Path
$VerifyPytestRoot = Join-Path $VerifyTempRoot "p"

function Invoke-PytestGroup {
  param(
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)][System.IO.FileInfo[]]$Files
  )
  if ($Files.Count -eq 0) { throw "pytest group is empty: $Name" }
  $BaseTemp = Join-Path $VerifyPytestRoot $Name
  Write-Host ("Running pytest group {0} ({1} files)..." -f $Name, $Files.Count) -ForegroundColor Cyan
  & $Python -m pytest -q --basetemp $BaseTemp @($Files.FullName)
  if ($LASTEXITCODE -ne 0) { throw "pytest group failed: $Name" }
}

Push-Location $Root
try {
  $env:TEMP = $VerifyTempRoot
  $env:TMP = $VerifyTempRoot

  $AllTestFiles = @(Get-ChildItem -LiteralPath (Join-Path $Root "tests") -Filter "test_*.py" -File)
  $BomTestFiles = @($AllTestFiles | Where-Object {
    $_.BaseName -like "test_bom*" -or
    $_.BaseName -in @("test_capture_bom_fields", "test_chinese_bom_text")
  })
  $PlatformTestFiles = @($AllTestFiles | Where-Object { $_.BaseName -eq "test_platform_api" })
  $LifecycleTestFiles = @($AllTestFiles | Where-Object {
    $_.BaseName -match "(lifecycle|update_api|release_|distribution_install|embedded_python|launch_and_package|local_release_pipeline|git_ota_publisher|setup_lifecycle|windows_server_accept|subprocess_encoding|frontend_build)"
  })
  $AssignedPaths = @($BomTestFiles + $PlatformTestFiles + $LifecycleTestFiles | ForEach-Object FullName)
  if (@($AssignedPaths | Sort-Object -Unique).Count -ne $AssignedPaths.Count) {
    throw "pytest verification groups overlap"
  }
  $RemainingTestFiles = @($AllTestFiles | Where-Object { $_.FullName -notin $AssignedPaths })
  if (($AssignedPaths.Count + $RemainingTestFiles.Count) -ne $AllTestFiles.Count) {
    throw "pytest verification groups do not cover every test file"
  }

  Invoke-PytestGroup -Name "bom" -Files $BomTestFiles
  Invoke-PytestGroup -Name "runtime" -Files $RemainingTestFiles
  Invoke-PytestGroup -Name "lifecycle" -Files $LifecycleTestFiles
  Invoke-PytestGroup -Name "platform-api" -Files $PlatformTestFiles

  & $Python -m py_compile app\backend\suite_app.py app\backend\update_api.py app\backend\tools\bom_process.py tools\bom\convert_cadence_bom.py
  if ($LASTEXITCODE -ne 0) { throw "py_compile failed" }

  if (Test-Path -LiteralPath "frontend\package.json") {
    Push-Location frontend
    try {
      if (-not (Test-Path -LiteralPath "node_modules" -PathType Container)) {
        Write-Host "Restoring locked frontend dependencies..." -ForegroundColor Cyan
        npm ci --prefer-offline --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw "frontend dependency restore failed" }
      }
      npm run test:unit
      if ($LASTEXITCODE -ne 0) { throw "frontend unit tests failed" }
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
  $env:TEMP = $OriginalTemp
  $env:TMP = $OriginalTmp
  Pop-Location
  Remove-Item -LiteralPath $VerifyTempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
