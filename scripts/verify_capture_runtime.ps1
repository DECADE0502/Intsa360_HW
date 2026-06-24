param(
  [string]$CaptureExe = "",
  [int]$TimeoutSeconds = 45,
  [switch]$CloseStartedCapture
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
. (Join-Path $Root "scripts\lib\Paths.ps1")

$Root = Get-HwAgentRoot -StartPath $Root
$ProbeLog = Join-Path $Root "data\reports\runtime\cadence_loader_probe.log"
$StartedProcess = $null

function Find-CaptureExe {
  if ($CaptureExe -and (Test-Path -LiteralPath $CaptureExe)) { return $CaptureExe }
  $known = @(
    "D:\CADENCE\Cadence\SPB_17.4\tools\bin\Capture.exe",
    "C:\Cadence\SPB_17.4\tools\bin\Capture.exe"
  )
  foreach ($candidate in $known) {
    if (Test-Path -LiteralPath $candidate) { return $candidate }
  }
  $found = Get-ChildItem -Path "D:\CADENCE", "C:\Cadence" -Recurse -Filter "Capture.exe" -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if ($found) { return $found.FullName }
  throw "Capture.exe not found"
}

function Wait-ForProbe {
  param([datetime]$StartTime)
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $ProbeLog) {
      $lines = Get-Content -LiteralPath $ProbeLog -Encoding UTF8 -ErrorAction SilentlyContinue
      $fresh = @($lines | Where-Object {
        $_ -like "*IAC: loader probe*" -and
        $_ -like "*RegisterAction=available*" -and
        $_ -like "*InsertXMLMenu=available*" -and
        $_ -like "*AddAccessoryMenu=available*"
      })
      if ($fresh.Count -gt 0) { return $fresh[-1] }
    }
    Start-Sleep -Seconds 1
  }
  return $null
}

try {
  $capture = Find-CaptureExe
  if (Test-Path -LiteralPath $ProbeLog) { Remove-Item -LiteralPath $ProbeLog -Force }
  $start = Get-Date
  $StartedProcess = Start-Process -FilePath $capture -PassThru
  Write-Host "Started Capture.exe pid=$($StartedProcess.Id)"
  $probe = Wait-ForProbe -StartTime $start
  if (-not $probe) {
    Write-Host "FAIL cadence_loader_probe.log did not report available Capture menu APIs within $TimeoutSeconds seconds." -ForegroundColor Red
    exit 1
  }
  Write-Host "OK cadence_loader_probe.log"
  Write-Host $probe
  exit 0
} finally {
  if ($CloseStartedCapture -and $StartedProcess -and -not $StartedProcess.HasExited) {
    $StartedProcess.CloseMainWindow() | Out-Null
    Start-Sleep -Seconds 3
    if (-not $StartedProcess.HasExited) {
      Stop-Process -Id $StartedProcess.Id -Force -ErrorAction SilentlyContinue
    }
  }
}
