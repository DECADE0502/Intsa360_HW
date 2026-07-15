param(
  [string]$Target = "",
  [switch]$ForceDependencyRestore
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Frontend = Join-Path $Root "frontend"
if ([string]::IsNullOrWhiteSpace($Target)) { $Target = Join-Path $Root "app\frontend" }
$Target = [System.IO.Path]::GetFullPath($Target)
$NodeModules = Join-Path $Frontend "node_modules"

Push-Location $Frontend
try {
  if ($ForceDependencyRestore -or -not (Test-Path -LiteralPath $NodeModules -PathType Container)) {
    Write-Host "Restoring locked frontend dependencies..." -ForegroundColor Cyan
    & npm ci --prefer-offline --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
  } else {
    Write-Host "Using existing frontend node_modules; package-lock remains the dependency authority."
  }
  & npm run build
  if ($LASTEXITCODE -ne 0) { throw "frontend build failed." }
} finally {
  Pop-Location
}

$Waiting = Join-Path $Root "app\frontend\waiting.html"
[byte[]]$WaitingBytes = $null
if (Test-Path -LiteralPath $Waiting -PathType Leaf) {
  $WaitingBytes = [System.IO.File]::ReadAllBytes($Waiting)
}
if (Test-Path -LiteralPath $Target) { Remove-Item -LiteralPath $Target -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Copy-Item -Path (Join-Path $Frontend "dist\*") -Destination $Target -Recurse -Force
$WaitingTarget = Join-Path $Target "waiting.html"
if ($null -ne $WaitingBytes -and -not (Test-Path -LiteralPath $WaitingTarget -PathType Leaf)) {
  [System.IO.File]::WriteAllBytes($WaitingTarget, $WaitingBytes)
}

Write-Host "Frontend ready: $Target" -ForegroundColor Green
