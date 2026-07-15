$ErrorActionPreference = "Stop"

function Get-HwV3ServiceStatePath {
  param([Parameter(Mandatory=$true)][string]$StateRoot)
  return Join-Path $StateRoot "runtime\service.json"
}

function Get-HwV3Health {
  param([Parameter(Mandatory=$true)][int]$Port, [int]$TimeoutMs = 1500)
  try {
    $request = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$Port/api/health")
    $request.Timeout = $TimeoutMs
    $request.ReadWriteTimeout = $TimeoutMs
    $response = $request.GetResponse()
    $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
    try { return $reader.ReadToEnd() | ConvertFrom-Json }
    finally { $reader.Dispose(); $response.Dispose() }
  } catch { return $null }
}

function Test-HwV3ServiceIdentity {
  param(
    [Parameter(Mandatory=$true)]$Identity,
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [Parameter(Mandatory=$true)][string]$StateRoot
  )
  try {
    foreach ($name in @("schema", "product", "pid", "port", "executable", "root", "state_root", "version", "instance_token")) {
      if ($null -eq $Identity.PSObject.Properties[$name] -or [string]::IsNullOrWhiteSpace([string]$Identity.$name)) { return $false }
    }
    if ([int]$Identity.schema -ne 2 -or [string]$Identity.product -ne "Insta360_HW" -or [int]$Identity.pid -le 0 -or
        [int]$Identity.port -lt 1 -or [int]$Identity.port -gt 65535 -or
        [string]$Identity.instance_token -notmatch '^[0-9a-fA-F]{32}$') { return $false }
    $expectedRoot = [System.IO.Path]::GetFullPath($RuntimeRoot).TrimEnd("\")
    $expectedState = [System.IO.Path]::GetFullPath($StateRoot).TrimEnd("\")
    $expectedExecutable = [System.IO.Path]::GetFullPath((Join-Path $expectedRoot "runtime\python\python.exe")).TrimEnd("\")
    $actualExecutable = [System.IO.Path]::GetFullPath([string]$Identity.executable).TrimEnd("\")
    $expectedVersion = (Get-Content -LiteralPath (Join-Path $expectedRoot "VERSION") -Raw -Encoding UTF8).Trim()
    return [System.IO.Path]::GetFullPath([string]$Identity.root).TrimEnd("\") -ieq $expectedRoot -and
      [System.IO.Path]::GetFullPath([string]$Identity.state_root).TrimEnd("\") -ieq $expectedState -and
      $actualExecutable -ieq $expectedExecutable -and (Test-Path -LiteralPath $expectedExecutable -PathType Leaf) -and
      [string]$Identity.version -ceq $expectedVersion
  } catch { return $false }
}

function Test-HwV3ProcessIdentity {
  param([Parameter(Mandatory=$true)]$Identity, [Parameter(Mandatory=$true)][string]$RuntimeRoot)
  try {
    $process = Get-CimInstance Win32_Process -Filter ("ProcessId=" + [int]$Identity.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process -or [string]::IsNullOrWhiteSpace([string]$process.CommandLine)) { return $false }
    $expectedExe = [System.IO.Path]::GetFullPath((Join-Path $RuntimeRoot "runtime\python\python.exe")).TrimEnd("\")
    $actualExe = [System.IO.Path]::GetFullPath([string]$process.ExecutablePath).TrimEnd("\")
    $backend = [System.IO.Path]::GetFullPath((Join-Path $RuntimeRoot "app\backend\suite_app.py"))
    return $actualExe -ieq $expectedExe -and
      ([string]$process.CommandLine).IndexOf($backend, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
  } catch { return $false }
}

function Get-HwV3RuntimeBackendProcesses {
  param([Parameter(Mandatory=$true)][string]$RuntimeRoot)
  $expectedExe = [System.IO.Path]::GetFullPath((Join-Path $RuntimeRoot "runtime\python\python.exe")).TrimEnd("\")
  $expectedBackend = [System.IO.Path]::GetFullPath((Join-Path $RuntimeRoot "app\backend\suite_app.py"))
  $matches = @()
  foreach ($process in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
    try {
      if ([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath) -or
          [string]::IsNullOrWhiteSpace([string]$process.CommandLine)) { continue }
      $actualExe = [System.IO.Path]::GetFullPath([string]$process.ExecutablePath).TrimEnd("\")
      if ($actualExe -ine $expectedExe) { continue }
      if (([string]$process.CommandLine).IndexOf(
          $expectedBackend,
          [System.StringComparison]::OrdinalIgnoreCase
        ) -lt 0) { continue }
      $matches += $process
    } catch {}
  }
  return @($matches)
}

function Test-HwV3Service {
  param([Parameter(Mandatory=$true)][string]$RuntimeRoot, [Parameter(Mandatory=$true)][string]$StateRoot)
  $identity = Read-HwV3Json -Path (Get-HwV3ServiceStatePath -StateRoot $StateRoot)
  if ($null -eq $identity -or -not (Test-HwV3ServiceIdentity -Identity $identity -RuntimeRoot $RuntimeRoot -StateRoot $StateRoot)) { return $false }
  if (-not (Test-HwV3ProcessIdentity -Identity $identity -RuntimeRoot $RuntimeRoot)) { return $false }
  $health = Get-HwV3Health -Port ([int]$identity.port)
  if ($null -eq $health) { return $false }
  try {
    $expectedRoot = [System.IO.Path]::GetFullPath($RuntimeRoot).TrimEnd("\")
    $expectedState = [System.IO.Path]::GetFullPath($StateRoot).TrimEnd("\")
    $expectedExecutable = [System.IO.Path]::GetFullPath((Join-Path $expectedRoot "runtime\python\python.exe")).TrimEnd("\")
    $expectedRevision = (Get-Content -LiteralPath (Join-Path $expectedRoot "REVISION") -Raw -Encoding UTF8).Trim()
    return [string]$health.product -eq "Insta360_HW" -and [string]$health.status -eq "ok" -and
      [System.IO.Path]::GetFullPath([string]$health.root).TrimEnd("\") -ieq $expectedRoot -and
      [System.IO.Path]::GetFullPath([string]$health.runtime_root).TrimEnd("\") -ieq $expectedRoot -and
      [System.IO.Path]::GetFullPath([string]$health.state_root).TrimEnd("\") -ieq $expectedState -and
      [System.IO.Path]::GetFullPath([string]$health.executable).TrimEnd("\") -ieq $expectedExecutable -and
      [string]$health.version -ceq [string]$identity.version -and [string]$health.revision -ceq $expectedRevision -and
      [string]$health.instance_token -eq [string]$identity.instance_token -and [int]$health.pid -eq [int]$identity.pid
  } catch { return $false }
}

function Stop-HwV3Service {
  param([Parameter(Mandatory=$true)][string]$RuntimeRoot, [Parameter(Mandatory=$true)][string]$StateRoot)
  $path = Get-HwV3ServiceStatePath -StateRoot $StateRoot
  $identity = Read-HwV3Json -Path $path

  $ownedPids = New-Object 'System.Collections.Generic.HashSet[int]'
  if ($null -ne $identity -and
      (Test-HwV3ServiceIdentity -Identity $identity -RuntimeRoot $RuntimeRoot -StateRoot $StateRoot) -and
      (Test-HwV3ProcessIdentity -Identity $identity -RuntimeRoot $RuntimeRoot)) {
    [void]$ownedPids.Add([int]$identity.pid)
  }
  foreach ($process in @(Get-HwV3RuntimeBackendProcesses -RuntimeRoot $RuntimeRoot)) {
    [void]$ownedPids.Add([int]$process.ProcessId)
  }
  foreach ($ownedPid in @($ownedPids)) {
    Stop-Process -Id $ownedPid -Force -ErrorAction SilentlyContinue
  }
  foreach ($ownedPid in @($ownedPids)) {
    try { Wait-Process -Id $ownedPid -Timeout 10 -ErrorAction SilentlyContinue } catch {}
  }
  $remaining = @(Get-HwV3RuntimeBackendProcesses -RuntimeRoot $RuntimeRoot)
  if ($remaining.Count -gt 0) {
    $remainingPids = (($remaining | ForEach-Object { [string]$_.ProcessId }) -join ", ")
    throw "Unable to stop remaining owned backend process: $remainingPids"
  }
  Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
}

function Start-HwV3Service {
  param([Parameter(Mandatory=$true)][string]$RuntimeRoot, [Parameter(Mandatory=$true)][string]$StateRoot)
  $launcher = Join-Path $RuntimeRoot "launch_tool_suite.ps1"
  if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw "Service launcher is missing: $launcher" }
  $env:INSTA360_HW_STATE_ROOT = $StateRoot
  $powershell = Get-HwV3PowerShellPath
  $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
  $isElevated = $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
  if ($isElevated) {
    # Shell.Application delegates process creation to the interactive shell so
    # the backend does not inherit the lifecycle worker's administrator token.
    $shell = New-Object -ComObject Shell.Application
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -StateRoot "{1}" -Restart -NoOpen' -f $launcher, $StateRoot
    $shell.ShellExecute($powershell, $arguments, $StateRoot, "open", 0)
  } else {
    & $powershell -NoProfile -ExecutionPolicy Bypass -File $launcher -StateRoot $StateRoot -Restart -NoOpen
    if ($LASTEXITCODE -ne 0) { throw "Backend service start failed with exit code $LASTEXITCODE." }
  }
  foreach ($attempt in 1..40) {
    if (Test-HwV3Service -RuntimeRoot $RuntimeRoot -StateRoot $StateRoot) { return }
    Start-Sleep -Milliseconds 250
  }
  throw "The activated backend did not pass instance and health verification."
}
