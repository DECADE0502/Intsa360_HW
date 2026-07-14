param(
  [string]$Source = "",
  [string]$Name = "",
  [switch]$Restart,
  [switch]$NoOpen,
  [string]$StateRoot = "",
  [int]$PreferredPort = 0
)

$ErrorActionPreference = "Stop"
$Root = (Split-Path -Parent $MyInvocation.MyCommand.Path).TrimEnd("\")
. (Join-Path $Root "scripts\lib\Paths.ps1")
$Root = Get-HwAgentRoot -StartPath $Root
. (Join-Path $Root "scripts\lifecycle\Contract.ps1")
. (Join-Path $Root "scripts\lifecycle\Runtime.ps1")

$Python = Find-Python -Root $Root
$Python = [System.IO.Path]::GetFullPath($Python)
$BackendScript = (Resolve-Path -LiteralPath (Join-Path $Root "app\backend\suite_app.py")).Path
$StateRoot = if ([string]::IsNullOrWhiteSpace($StateRoot)) {
  Get-HwLifecycleStateRoot -RuntimeRoot $Root
} else {
  [System.IO.Path]::GetFullPath($StateRoot).TrimEnd("\")
}
$env:INSTA360_HW_STATE_ROOT = $StateRoot
$RuntimeStateDir = Join-Path $StateRoot "runtime"
$LogDir = Join-Path $StateRoot "data\reports\runtime"
$ServiceStatePath = Get-HwLifecycleServiceStatePath -StateRoot $StateRoot
$LauncherLogFile = Join-Path $LogDir "launcher_latest.log"
$Version = Get-HwLifecycleRuntimeVersion -RuntimeRoot $Root
$PortRange = 8765..8775
$RequiredTools = @(
  "bom_process",
  "bom_compare",
  "bom_risk_check",
  "netlist_compare",
  "smt_package_check",
  "single_network_check"
)

if ([string]::IsNullOrWhiteSpace($Version)) { throw "Runtime VERSION is missing or empty." }
New-Item -ItemType Directory -Force -Path $RuntimeStateDir, $LogDir | Out-Null

function Rotate-LauncherLog {
  if (-not (Test-Path -LiteralPath $LauncherLogFile -PathType Leaf)) { return }
  if ((Get-Item -LiteralPath $LauncherLogFile).Length -lt 1MB) { return }
  for ($index = 4; $index -ge 1; $index--) {
    $current = $LauncherLogFile + "." + $index
    $next = $LauncherLogFile + "." + ($index + 1)
    if (Test-Path -LiteralPath $current) { Move-Item -LiteralPath $current -Destination $next -Force }
  }
  Move-Item -LiteralPath $LauncherLogFile -Destination ($LauncherLogFile + ".1") -Force
}

function Write-LauncherLog {
  param([Parameter(Mandatory=$true)][string]$Message)
  Rotate-LauncherLog
  "[$(Get-Date -Format s)] $Message" | Out-File -LiteralPath $LauncherLogFile -Encoding UTF8 -Append
}

function Test-PortOpen {
  param([Parameter(Mandatory=$true)][int]$Port)
  $client = $null
  try {
    $client = New-Object System.Net.Sockets.TcpClient
    $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
    $connected = $async.AsyncWaitHandle.WaitOne(250)
    if ($connected) { $client.EndConnect($async) }
    return $connected
  } catch {
    return $false
  } finally {
    if ($null -ne $client) { $client.Dispose() }
  }
}

function Test-ToolsReady {
  param([Parameter(Mandatory=$true)][int]$Port)
  try {
    $payload = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/tools" -TimeoutSec 2
    foreach ($toolId in $RequiredTools) {
      $tool = @($payload.tools | Where-Object { $_.id -eq $toolId }) | Select-Object -First 1
      if ($null -eq $tool -or $tool.status -ne "available") { return $false }
    }
    return $true
  } catch {
    return $false
  }
}

function Get-SuiteUrl {
  param([Parameter(Mandatory=$true)][int]$Port)
  $url = "http://127.0.0.1:$Port"
  $parameters = @()
  if (-not [string]::IsNullOrWhiteSpace($Source)) { $parameters += "source=$([uri]::EscapeDataString($Source))" }
  if (-not [string]::IsNullOrWhiteSpace($Name)) { $parameters += "name=$([uri]::EscapeDataString($Name))" }
  if ($parameters.Count -gt 0) { $url += "/?tool=bom_process&" + ($parameters -join "&") }
  return $url
}

function Open-Suite {
  param([Parameter(Mandatory=$true)][int]$Port)
  $url = Get-SuiteUrl -Port $Port
  Write-LauncherLog "Opening URL: $url"
  Start-Process -FilePath "rundll32.exe" -ArgumentList "url.dll,FileProtocolHandler", $url | Out-Null
}

function Open-WaitingPage {
  param([Parameter(Mandatory=$true)][int]$Port)
  $waitFile = Join-Path $Root "app\frontend\waiting.html"
  if (-not (Test-Path -LiteralPath $waitFile -PathType Leaf)) { return $false }
  $target = Get-SuiteUrl -Port $Port
  $waitUrl = "file:///$($waitFile.Replace('\', '/'))?target=$([uri]::EscapeDataString($target))"
  Write-LauncherLog "Opening startup wait page for: $target"
  Start-Process -FilePath $waitUrl | Out-Null
  return $true
}

$serviceMutex = New-Object System.Threading.Mutex($false, "Global\Insta360_HW_ServiceLaunch_V2")
$serviceMutexHeld = $false
try {
  try {
    $serviceMutexHeld = $serviceMutex.WaitOne(120000)
  } catch [System.Threading.AbandonedMutexException] {
    $serviceMutexHeld = $true
  }
  if (-not $serviceMutexHeld) { throw "Timed out waiting for another platform launch to finish." }

  Write-LauncherLog "Launch requested Source='$Source' Name='$Name' Restart='$Restart' NoOpen='$NoOpen' state='$StateRoot'"

  if (-not $Restart -and (Test-HwLifecycleService -RuntimeRoot $Root -StateRoot $StateRoot)) {
    $existing = Read-HwLifecycleJson -Path $ServiceStatePath
    Write-LauncherLog ("Reusing exact service PID {0} on port {1}" -f $existing.pid, $existing.port)
    if (-not $NoOpen) { Open-Suite -Port ([int]$existing.port) }
    return
  }

  Stop-HwLifecycleService -RuntimeRoot $Root -StateRoot $StateRoot -AllowLegacyIdentity

$Port = $null
if ($PreferredPort -ge 1 -and $PreferredPort -le 65535 -and -not (Test-PortOpen -Port $PreferredPort)) {
  $Port = $PreferredPort
}
if ($null -eq $Port) {
  foreach ($candidatePort in $PortRange) {
    if (-not (Test-PortOpen -Port $candidatePort)) {
      $Port = $candidatePort
      break
    }
  }
}
if ($null -eq $Port) { throw "No free service port is available in 8765-8775." }

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "tool_suite_server_$Stamp.log"
$ErrorLogFile = Join-Path $LogDir "tool_suite_server_error_$Stamp.log"
$Token = [guid]::NewGuid().ToString("N")
$env:INSTA360_HW_INSTANCE_TOKEN = $Token
$waitingPageOpened = $false
if (-not $NoOpen) { $waitingPageOpened = Open-WaitingPage -Port $Port }

Write-LauncherLog "Starting exact service on port $Port"
$backendArgument = '"' + $BackendScript + '"'
$process = Start-Process -FilePath $Python `
  -ArgumentList @($backendArgument, "--port", [string]$Port) `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -RedirectStandardOutput $LogFile `
  -RedirectStandardError $ErrorLogFile `
  -PassThru

$identity = [ordered]@{
  schema = 2
  product = "Insta360_HW"
  pid = $process.Id
  port = $Port
  executable = $Python
  root = $Root
  state_root = $StateRoot
  version = $Version
  instance_token = $Token
  started_at = (Get-Date).ToUniversalTime().ToString("o")
}
Write-HwLifecycleJsonAtomic -Path $ServiceStatePath -Value $identity

$ready = $false
foreach ($attempt in 1..75) {
  $process.Refresh()
  if ($process.HasExited) { break }
  if ((Test-HwLifecycleService -RuntimeRoot $Root -StateRoot $StateRoot) -and (Test-ToolsReady -Port $Port)) {
    $ready = $true
    break
  }
  Start-Sleep -Milliseconds 200
}

if (-not $ready) {
  if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
  Remove-Item -LiteralPath $ServiceStatePath -Force -ErrorAction SilentlyContinue
  Write-LauncherLog "Startup failed for PID $($process.Id); error log: $ErrorLogFile"
  throw "Platform backend failed exact-instance health verification. See $ErrorLogFile"
}

  Write-LauncherLog "Service verified PID $($process.Id) port $Port token $Token version $Version"
  if (-not $NoOpen -and -not $waitingPageOpened) { Open-Suite -Port $Port }
} finally {
  if ($serviceMutexHeld) { $serviceMutex.ReleaseMutex() | Out-Null }
  $serviceMutex.Dispose()
}
