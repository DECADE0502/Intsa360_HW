$ErrorActionPreference = "Stop"

function Get-HwAgentText {
  param([Parameter(Mandatory=$true)][string]$Base64)
  return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Base64))
}

function Test-HwAgentService {
  param([int]$Port = 8765)
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/tools" -TimeoutSec 2
    return ($response.StatusCode -eq 200)
  } catch {
    return $false
  }
}

function Start-HwAgentService {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [int]$Port = 8765
  )
  if (Test-HwAgentService -Port $Port) {
    Write-Host (Get-HwAgentText "5pyN5Yqh5bey5Zyo6L+Q6KGM77yM55u05o6l5aSN55So44CC")
    return $true
  }
  $script = Join-Path $Root "app\backend\suite_app.py"
  $logDir = Join-Path $Root "data\reports\runtime"
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null
  $stdout = Join-Path $logDir "tool_suite_server_latest.log"
  $stderr = Join-Path $logDir "tool_suite_server_error_latest.log"
  Start-Process -FilePath $PythonPath -ArgumentList @($script, "--port", "$Port") -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr | Out-Null
  Write-Host (Get-HwAgentText "5q2j5Zyo5ZCv5Yqo5pyN5Yqh77yM6K+356iN5YCZLi4u")
  return $false
}
