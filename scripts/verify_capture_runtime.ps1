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
  if ($CaptureExe -and (Test-Path -LiteralPath $CaptureExe -PathType Leaf)) {
    return [System.IO.Path]::GetFullPath($CaptureExe)
  }

  $command = Get-Command Capture.exe -ErrorAction SilentlyContinue
  if ($command -and (Test-Path -LiteralPath $command.Source -PathType Leaf)) { return $command.Source }

  $candidates = New-Object System.Collections.Generic.List[string]
  foreach ($installation in @((Get-HwAgentCadenceDiscovery).vendor_installations)) {
    $candidates.Add((Join-Path ([string]$installation.root) "tools\bin\Capture.exe")) | Out-Null
  }

  foreach ($registryRoot in @(
      "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
      "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
    )) {
    if (-not (Test-Path -LiteralPath $registryRoot)) { continue }
    foreach ($entry in Get-ChildItem -LiteralPath $registryRoot -ErrorAction SilentlyContinue) {
      $properties = Get-ItemProperty -LiteralPath $entry.PSPath -ErrorAction SilentlyContinue
      if ($null -eq $properties -or [string]$properties.DisplayName -notmatch "Cadence|OrCAD|SPB") { continue }
      $location = [string]$properties.InstallLocation
      if ([string]::IsNullOrWhiteSpace($location)) { continue }
      $candidates.Add((Join-Path $location "tools\bin\Capture.exe")) | Out-Null
      $candidates.Add((Join-Path $location "Capture.exe")) | Out-Null
    }
  }

  $seen = @{}
  foreach ($candidate in $candidates) {
    try { $full = [System.IO.Path]::GetFullPath($candidate) } catch { continue }
    if ($seen.ContainsKey($full)) { continue }
    $seen[$full] = $true
    if (Test-Path -LiteralPath $full -PathType Leaf) { return $full }
  }
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
