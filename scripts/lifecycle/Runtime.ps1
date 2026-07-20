$ErrorActionPreference = "Stop"

function Get-HwLifecycleServiceStatePath {
  param([Parameter(Mandatory=$true)][string]$StateRoot)
  return Join-Path $StateRoot "runtime\service.json"
}

function Get-HwLifecycleRuntimeVersion {
  param([Parameter(Mandatory=$true)][string]$RuntimeRoot)
  try {
    return (Get-Content -LiteralPath (Join-Path $RuntimeRoot "VERSION") -Raw -Encoding UTF8).Trim()
  } catch { return "" }
}

function Test-HwLifecycleServiceIdentity {
  param(
    [Parameter(Mandatory=$true)]$Identity,
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [Parameter(Mandatory=$true)][string]$StateRoot
  )
  try {
    $required = @("schema", "product", "pid", "port", "executable", "root", "state_root", "version", "instance_token")
    foreach ($name in $required) {
      if ($null -eq $Identity.PSObject.Properties[$name] -or [string]::IsNullOrWhiteSpace([string]$Identity.$name)) { return $false }
    }
    if ([int]$Identity.schema -ne 2 -or [string]$Identity.product -ne "Insta360_HW") { return $false }
    if ([int]$Identity.pid -le 0 -or [int]$Identity.port -lt 1 -or [int]$Identity.port -gt 65535) { return $false }
    if ([string]$Identity.instance_token -notmatch '^[0-9a-fA-F]{32}$') { return $false }
    $expectedRoot = [System.IO.Path]::GetFullPath($RuntimeRoot).TrimEnd("\\")
    $expectedState = [System.IO.Path]::GetFullPath($StateRoot).TrimEnd("\\")
    $actualRoot = [System.IO.Path]::GetFullPath([string]$Identity.root).TrimEnd("\\")
    $actualState = [System.IO.Path]::GetFullPath([string]$Identity.state_root).TrimEnd("\\")
    $executable = [System.IO.Path]::GetFullPath([string]$Identity.executable).TrimEnd("\\")
    if ($actualRoot -ine $expectedRoot -or $actualState -ine $expectedState) { return $false }
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { return $false }
    $expectedVersion = Get-HwLifecycleRuntimeVersion -RuntimeRoot $expectedRoot
    return -not [string]::IsNullOrWhiteSpace($expectedVersion) -and [string]$Identity.version -eq $expectedVersion
  } catch { return $false }
}

function Test-HwLifecycleProcessIdentity {
  param(
    [Parameter(Mandatory=$true)]$Identity,
    [Parameter(Mandatory=$true)][string]$RuntimeRoot
  )
  try {
    $processInfo = Get-CimInstance Win32_Process -Filter ("ProcessId=" + [int]$Identity.pid) -ErrorAction SilentlyContinue
    if ($null -eq $processInfo -or [string]::IsNullOrWhiteSpace([string]$processInfo.CommandLine)) { return $false }
    $expectedExecutable = [System.IO.Path]::GetFullPath([string]$Identity.executable).TrimEnd("\\")
    $actualExecutable = [System.IO.Path]::GetFullPath([string]$processInfo.ExecutablePath).TrimEnd("\\")
    if ($actualExecutable -ine $expectedExecutable) { return $false }
    $backendCandidates = @(
      (Join-Path $RuntimeRoot "app\backend\suite_app.py"),
      ([System.IO.Path]::GetFullPath((Join-Path $RuntimeRoot "app\backend\suite_app.py"))),
      (Join-Path ([string]$Identity.root) "app\backend\suite_app.py")
    ) | Select-Object -Unique
    foreach ($backend in $backendCandidates) {
      if (([string]$processInfo.CommandLine).IndexOf([string]$backend, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
        return $true
      }
    }
    return $false
  } catch { return $false }
}

function Test-HwLifecycleLegacyProcessIdentity {
  param(
    [Parameter(Mandatory=$true)]$Identity,
    [Parameter(Mandatory=$true)][string]$RuntimeRoot
  )
  try {
    $pidValue = [int]$Identity.pid
    if ($pidValue -le 0) { return $false }
    $processInfo = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $pidValue) -ErrorAction SilentlyContinue
    if ($null -eq $processInfo -or [string]::IsNullOrWhiteSpace([string]$processInfo.CommandLine)) { return $false }
    $expectedRoot = [System.IO.Path]::GetFullPath($RuntimeRoot).TrimEnd("\")
    if ($null -ne $Identity.PSObject.Properties["root"] -and
        -not [string]::IsNullOrWhiteSpace([string]$Identity.root) -and
        [System.IO.Path]::GetFullPath([string]$Identity.root).TrimEnd("\") -ine $expectedRoot) { return $false }
    if ($null -ne $Identity.PSObject.Properties["executable"] -and
        -not [string]::IsNullOrWhiteSpace([string]$Identity.executable)) {
      $expectedExecutable = [System.IO.Path]::GetFullPath([string]$Identity.executable).TrimEnd("\")
      $actualExecutable = [System.IO.Path]::GetFullPath([string]$processInfo.ExecutablePath).TrimEnd("\")
      if ($actualExecutable -ine $expectedExecutable) { return $false }
    }
    $backendCandidates = @(
      (Join-Path $RuntimeRoot "app\backend\suite_app.py"),
      ([System.IO.Path]::GetFullPath((Join-Path $RuntimeRoot "app\backend\suite_app.py"))),
      (Join-Path $expectedRoot "app\backend\suite_app.py")
    ) | Select-Object -Unique
    foreach ($backend in $backendCandidates) {
      if (([string]$processInfo.CommandLine).IndexOf([string]$backend, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
        return $true
      }
    }
    return $false
  } catch { return $false }
}

function Get-HwLifecycleRuntimeBackendProcesses {
  param([Parameter(Mandatory=$true)][string]$RuntimeRoot)
  $expectedExecutable = [System.IO.Path]::GetFullPath(
    (Join-Path $RuntimeRoot "runtime\python\python.exe")
  ).TrimEnd("\")
  $expectedBackend = [System.IO.Path]::GetFullPath(
    (Join-Path $RuntimeRoot "app\backend\suite_app.py")
  )
  $matches = @()
  foreach ($processInfo in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
    try {
      if ([string]::IsNullOrWhiteSpace([string]$processInfo.ExecutablePath) -or
          [string]::IsNullOrWhiteSpace([string]$processInfo.CommandLine)) { continue }
      $actualExecutable = [System.IO.Path]::GetFullPath([string]$processInfo.ExecutablePath).TrimEnd("\")
      if ($actualExecutable -ine $expectedExecutable) { continue }
      if (([string]$processInfo.CommandLine).IndexOf(
          $expectedBackend,
          [System.StringComparison]::OrdinalIgnoreCase
        ) -lt 0) { continue }
      $matches += $processInfo
    } catch {}
  }
  return @($matches)
}

function Get-HwLifecycleHealth {
  param([Parameter(Mandatory=$true)][int]$Port, [int]$TimeoutMs = 1500)
  try {
    $request = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$Port/api/health")
    $request.Timeout = $TimeoutMs
    $request.ReadWriteTimeout = $TimeoutMs
    $response = $request.GetResponse()
    $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
    try { return ($reader.ReadToEnd() | ConvertFrom-Json) }
    finally { $reader.Dispose(); $response.Dispose() }
  } catch { return $null }
}

function Test-HwLifecycleService {
  param([Parameter(Mandatory=$true)][string]$RuntimeRoot, [Parameter(Mandatory=$true)][string]$StateRoot)
  $identity = Read-HwLifecycleJson -Path (Get-HwLifecycleServiceStatePath -StateRoot $StateRoot)
  if ($null -eq $identity -or -not (Test-HwLifecycleServiceIdentity -Identity $identity -RuntimeRoot $RuntimeRoot -StateRoot $StateRoot)) { return $false }
  if ($null -eq (Get-Process -Id ([int]$identity.pid) -ErrorAction SilentlyContinue)) { return $false }
  if (-not (Test-HwLifecycleProcessIdentity -Identity $identity -RuntimeRoot $RuntimeRoot)) { return $false }
  $health = Get-HwLifecycleHealth -Port ([int]$identity.port)
  if ($null -eq $health) { return $false }
  try {
    $expectedRoot = [System.IO.Path]::GetFullPath($RuntimeRoot).TrimEnd("\\")
    $expectedState = [System.IO.Path]::GetFullPath($StateRoot).TrimEnd("\\")
    $actualRoot = [System.IO.Path]::GetFullPath([string]$health.root).TrimEnd("\\")
    $actualState = [System.IO.Path]::GetFullPath([string]$health.state_root).TrimEnd("\\")
    # Health status means the process can serve requests; component integrity is reported separately.
    return $health.product -eq "Insta360_HW" -and $health.status -eq "ok" -and
      $actualRoot -ieq $expectedRoot -and
      $actualState -ieq $expectedState -and
      [string]$health.version -eq [string]$identity.version -and
      [string]$health.instance_token -eq [string]$identity.instance_token -and
      [int]$health.pid -eq [int]$identity.pid
  } catch { return $false }
}

function Stop-HwLifecycleService {
  param(
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [Parameter(Mandatory=$true)][string]$StateRoot,
    [switch]$AllowLegacyIdentity
  )
  $statePath = Get-HwLifecycleServiceStatePath -StateRoot $StateRoot
  $identity = Read-HwLifecycleJson -Path $statePath

  $ownedPids = New-Object 'System.Collections.Generic.HashSet[int]'
  if ($null -ne $identity) {
    $ownedProcess = $false
    if (Test-HwLifecycleServiceIdentity -Identity $identity -RuntimeRoot $RuntimeRoot -StateRoot $StateRoot) {
      $ownedProcess = Test-HwLifecycleProcessIdentity -Identity $identity -RuntimeRoot $RuntimeRoot
    } elseif ($AllowLegacyIdentity) {
      $ownedProcess = Test-HwLifecycleLegacyProcessIdentity -Identity $identity -RuntimeRoot $RuntimeRoot
    }
    if ($ownedProcess) { [void]$ownedPids.Add([int]$identity.pid) }
  }
  foreach ($processInfo in @(Get-HwLifecycleRuntimeBackendProcesses -RuntimeRoot $RuntimeRoot)) {
    [void]$ownedPids.Add([int]$processInfo.ProcessId)
  }

  foreach ($ownedPid in @($ownedPids)) {
    Stop-Process -Id $ownedPid -Force -ErrorAction SilentlyContinue
  }
  foreach ($ownedPid in @($ownedPids)) {
    try { Wait-Process -Id $ownedPid -Timeout 10 -ErrorAction SilentlyContinue } catch {}
  }
  $remaining = @(Get-HwLifecycleRuntimeBackendProcesses -RuntimeRoot $RuntimeRoot)
  if ($remaining.Count -gt 0) {
    $remainingPids = (($remaining | ForEach-Object { [string]$_.ProcessId }) -join ", ")
    throw "Unable to stop remaining owned backend process: $remainingPids"
  }
  Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
}

function Start-HwLifecycleService {
  param(
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [Parameter(Mandatory=$true)][string]$StateRoot
  )
  $launcher = Join-Path $RuntimeRoot "launch_tool_suite.ps1"
  if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw "缺少服务启动脚本：$launcher" }
  $env:INSTA360_HW_STATE_ROOT = $StateRoot
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -Restart -NoOpen -StateRoot $StateRoot
  if ($LASTEXITCODE -ne 0) { throw "后端服务启动失败，错误码：$LASTEXITCODE。" }
  foreach ($attempt in 1..30) {
    if (Test-HwLifecycleService -RuntimeRoot $RuntimeRoot -StateRoot $StateRoot) { return }
    Start-Sleep -Milliseconds 250
  }
  throw "新版本后端服务未通过实例身份与健康检查。"
}
