param([string]$Source = "", [string]$Name = "", [switch]$Restart, [switch]$NoOpen)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Root "scripts\lib\Paths.ps1")
. (Join-Path $Root "scripts\lib\Update.ps1")
$Root = Get-HwAgentRoot -StartPath $Root
$Python = Find-Python -Root $Root
$LogDir = Join-Path $Root "data\reports\runtime"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "tool_suite_server_$Stamp.log"
$ErrorLogFile = Join-Path $LogDir "tool_suite_server_error_$Stamp.log"
$LauncherLogFile = Join-Path $LogDir "launcher_latest.log"
$PortRange = 8765..8775
$Required = @("bom_process", "bom_compare", "bom_risk_check", "netlist_compare", "smt_package_check", "single_network_check")
$BackendScript = Join-Path $Root "app\backend\suite_app.py"
$BackendScriptResolved = (Resolve-Path -LiteralPath $BackendScript).Path

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Location $Root

function Write-LauncherLog {
  param([string]$Message)
  "[$(Get-Date -Format s)] $Message" | Out-File -FilePath $LauncherLogFile -Encoding utf8 -Append
}

# Pure .NET TCP probe, avoids Get-NetTCPConnection module startup cost.
function Test-PortOpen {
  param([int]$Port)
  try {
    $client = [System.Net.Sockets.TcpClient]::new()
    $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
    $ok = $async.AsyncWaitHandle.WaitOne(300)
    if ($ok) { $client.EndConnect($async) }
    $client.Close()
    return $ok
  } catch {
    return $false
  }
}

# Pure .NET HttpWebRequest, avoids Invoke-WebRequest first-call overhead.
function Test-HttpReady {
  param([int]$Port)
  try {
    $request = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$Port/api/tools")
    $request.Timeout = 2000
    $response = $request.GetResponse()
    $reader = [System.IO.StreamReader]::new($response.GetResponseStream())
    $content = $reader.ReadToEnd()
    $reader.Close()
    $response.Close()
    $tools = ($content | ConvertFrom-Json).tools
    foreach ($toolId in $Required) {
      $tool = $tools | Where-Object { $_.id -eq $toolId } | Select-Object -First 1
      if ($null -eq $tool -or $tool.status -ne "available") { return $false }
    }
    $pluginRequest = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$Port/api/plugins")
    $pluginRequest.Timeout = 2000
    $pluginResponse = $pluginRequest.GetResponse()
    $pluginReader = [System.IO.StreamReader]::new($pluginResponse.GetResponseStream())
    $pluginContent = $pluginReader.ReadToEnd()
    $pluginReader.Close()
    $pluginResponse.Close()
    $pluginPayload = $pluginContent | ConvertFrom-Json
    if ($null -eq $pluginPayload.groups -or $null -eq $pluginPayload.groups.system) { return $false }
    return $true
  } catch {
    return $false
  }
}

function Open-Suite {
  param([int]$Port)
  $url = "http://127.0.0.1:$Port"
  $params = @()
  if ($Source -ne "") { $params += "source=$([uri]::EscapeDataString($Source))" }
  if ($Name   -ne "") { $params += "name=$([uri]::EscapeDataString($Name))"   }
  if ($params.Count -gt 0) { $url = "$url/?tool=bom_process&$($params -join '&')" }
  Write-LauncherLog "Opening URL: $url"
  Write-Host "Insta360 HW platform is ready: $url" -ForegroundColor Green
  Start-Process -FilePath "rundll32.exe" -ArgumentList "url.dll,FileProtocolHandler", $url | Out-Null
}

function Open-WaitingPage {
  param([int]$Port)
  $url = "http://127.0.0.1:$Port"
  $params = @()
  if ($Source -ne "") { $params += "source=$([uri]::EscapeDataString($Source))" }
  if ($Name   -ne "") { $params += "name=$([uri]::EscapeDataString($Name))"   }
  if ($params.Count -gt 0) { $url = "$url/?tool=bom_process&$($params -join '&')" }
  $target = [uri]::EscapeDataString($url)
  $waitFile = Join-Path $Root "app\frontend\waiting.html"
  $waitUrl = "file:///$($waitFile.Replace('\', '/'))?target=$target"
  Write-LauncherLog "Opening waiting page for: $url"
  Start-Process $waitUrl | Out-Null
}

Write-LauncherLog "Launch requested Source='$Source' Name='$Name' Restart='$Restart' NoOpen='$NoOpen'"

try {
  if (Restore-HwAgentInterruptedUpdate -Root $Root) {
    Write-LauncherLog "Recovered interrupted update before launch."
  }
} catch {
  Write-LauncherLog ("Interrupted update recovery failed: " + $_.Exception.Message)
}

# 0) Reuse a healthy service unless restart is requested.
if (-not $Restart) {
  foreach ($candidate in $PortRange) {
    if ((Test-PortOpen -Port $candidate) -and (Test-HttpReady -Port $candidate)) {
      Write-LauncherLog "Reusing healthy service on port $candidate"
      if (-not $NoOpen) {
        Open-Suite -Port $candidate
      } else {
        Write-LauncherLog "NoOpen requested; leaving existing browser page to reconnect"
      }
      exit 0
    }
  }
}

# 1) Restart or unavailable service: stop old backend processes and start fresh.
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "python*" -and $_.CommandLine -and ($_.CommandLine -like "*$BackendScriptResolved*") } |
  ForEach-Object {
    if ($_.ProcessId -ne $PID) {
      Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
  }

# 2) Pick the first free port.
$Port = $null
foreach ($candidate in $PortRange) {
  if (-not (Test-PortOpen -Port $candidate)) {
    $Port = $candidate
    break
  }
}
if ($null -eq $Port) {
  Write-LauncherLog "No available port in 8765-8775"
  throw "8765-8775 ports are all in use; cannot start."
}

# 3) Start a fresh backend in the background.
"[$(Get-Date -Format s)] Starting hardware tool suite on port $Port" | Out-File -FilePath $LogFile -Encoding utf8 -Append
Write-LauncherLog "Starting service on port $Port"
if (-not $NoOpen) {
  Open-WaitingPage -Port $Port
} else {
  Write-LauncherLog "NoOpen requested; suppressing waiting page"
}
Start-Process -FilePath $Python `
  -ArgumentList "app\backend\suite_app.py --port $Port" `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -RedirectStandardOutput $LogFile `
  -RedirectStandardError $ErrorLogFile | Out-Null

# 4) Poll readiness quickly, up to about 8 seconds.
$ready = $false
foreach ($i in 1..40) {
  if (Test-HttpReady -Port $Port) {
    $ready = $true
    break
  }
  Start-Sleep -Milliseconds 200
}

if (-not $ready) {
  Write-LauncherLog "Startup failed on port $Port; error log: $ErrorLogFile"
  Write-Host "Platform startup failed. See log: $ErrorLogFile" -ForegroundColor Red
  exit 1
}

Write-LauncherLog "Service ready on port $Port"
if (-not $NoOpen) {
  Open-Suite -Port $Port
} else {
  Write-LauncherLog "NoOpen requested; service is ready without opening browser"
}
