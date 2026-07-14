param(
  [string]$RuntimeRoot = (Split-Path -Parent $PSScriptRoot),
  [Parameter(Mandatory=$true)][string]$OutputPath
)

$ErrorActionPreference = "Stop"
$python = Join-Path $RuntimeRoot "runtime\python\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
  $command = Get-Command python.exe -ErrorAction SilentlyContinue
  if ($null -eq $command) { throw "Python runtime not found." }
  $python = $command.Source
}

Push-Location $RuntimeRoot
try {
  & $python -m app.backend.services.diagnostics --root $RuntimeRoot --output $OutputPath
  if ($LASTEXITCODE -ne 0) { throw "Diagnostic collection failed with exit code $LASTEXITCODE." }
} finally {
  Pop-Location
}
