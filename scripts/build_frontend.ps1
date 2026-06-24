$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Frontend = Join-Path $Root "frontend"
$Target = Join-Path $Root "app\frontend"

Push-Location $Frontend
try {
  npm install
  npm run build
} finally {
  Pop-Location
}

$Waiting = Join-Path $Target "waiting.html"
$WaitingBackup = Join-Path $env:TEMP "hwagent_waiting.html"
if (Test-Path -LiteralPath $Waiting) { Copy-Item $Waiting $WaitingBackup -Force }
Remove-Item -LiteralPath $Target -Recurse -Force
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Copy-Item -Path (Join-Path $Frontend "dist\*") -Destination $Target -Recurse -Force
if ((Test-Path -LiteralPath $WaitingBackup) -and -not (Test-Path -LiteralPath (Join-Path $Target "waiting.html"))) {
  Copy-Item $WaitingBackup (Join-Path $Target "waiting.html") -Force
}
