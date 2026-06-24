param(
  [switch]$FixVendorAutoLoad,
  [int[]]$Ports = @(8765, 8766, 8767, 8768, 8769, 8770, 8771, 8772, 8773, 8774, 8775)
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
. (Join-Path $Root "scripts\lib\Paths.ps1")
. (Join-Path $Root "scripts\lib\TclScripts.ps1")

$Root = Get-HwAgentRoot -StartPath $Root
$Utf8 = [System.Text.Encoding]::UTF8
$Gbk = [System.Text.Encoding]::GetEncoding(936)
$Failures = New-Object System.Collections.Generic.List[string]

function U {
  param([int[]]$Bytes)
  return $script:Utf8.GetString([byte[]]$Bytes)
}

# Loader checks include AddAccessoryMenu entries for the two default Chinese menu items.
$S = @{
  PlatformDiag = U @(73,110,115,116,97,51,54,48,231,161,172,228,187,182,230,143,144,230,149,136,229,185,179,229,143,176,232,175,138,230,150,173)
  Root = U @(230,160,185,231,155,174,229,189,149,239,188,154)
  NoLoader = U @(230,156,170,230,137,190,229,136,176,32,67,97,100,101,110,99,101,32,108,111,97,100,101,114,239,188,154)
  AutoLoadBackupClean = U @(67,97,100,101,110,99,101,32,97,117,116,111,108,111,97,100,32,228,184,139,230,178,161,230,156,137,231,166,129,231,148,168,229,164,135,228,187,189,231,155,174,229,189,149,239,188,154)
  AutoLoadBackupMoved = U @(229,183,178,231,167,187,229,135,186,32,97,117,116,111,108,111,97,100,32,231,166,129,231,148,168,229,164,135,228,187,189,231,155,174,229,189,149,32)
  AutoLoadBackupDirty = U @(67,97,100,101,110,99,101,32,97,117,116,111,108,111,97,100,32,228,184,139,228,187,141,230,156,137,231,166,129,231,148,168,229,164,135,228,187,189,231,155,174,229,189,149,239,188,154)
  MenuOpen = U @(229,140,133,229,144,171,232,143,156,229,141,149,239,188,154,232,191,155,229,133,165,229,185,179,229,143,176)
  MenuExport = U @(229,140,133,229,144,171,232,143,156,229,141,149,239,188,154,229,175,188,229,135,186,229,185,182,229,164,132,231,144,134,66,79,77)
  NoLegacy = U @(228,184,141,229,138,160,232,189,189,230,151,167,229,162,158,229,188,186,232,132,154,230,156,172,32,111,114,99,97,100,95,101,110,104,97,110,99,101,100,95,116,111,111,108,115,46,116,99,108)
  NoRename = U @(228,184,141,230,148,185,229,134,153,32,114,101,110,97,109,101,32,82,101,103,105,115,116,101,114,65,99,116,105,111,110)
  NoOther = U @(228,184,141,230,152,190,231,164,186,229,133,182,228,187,150,232,132,154,230,156,172,229,141,160,228,189,141,232,143,156,229,141,149)
  OpenLine = U @(65,100,100,65,99,99,101,115,115,111,114,121,77,101,110,117,32,34,105,110,115,116,97,51,54,48,95,72,87,34,32,34,232,191,155,229,133,165,229,185,179,229,143,176,34)
  ExportLine = U @(65,100,100,65,99,99,101,115,115,111,114,121,77,101,110,117,32,34,105,110,115,116,97,51,54,48,95,72,87,34,32,34,229,175,188,229,135,186,229,185,182,229,164,132,231,144,134,66,79,77,34)
  OtherScripts = U @(229,133,182,228,187,150,232,132,154,230,156,172)
  VendorClean = U @(67,97,100,101,110,99,101,32,229,174,152,230,150,185,32,97,117,116,111,108,111,97,100,32,230,160,185,231,155,174,229,189,149,230,178,161,230,156,137,230,151,167,229,162,158,229,188,186,232,132,154,230,156,172,239,188,154)
  MovedOld = U @(229,183,178,231,167,187,229,138,168,230,151,167,229,162,158,229,188,186,232,132,154,230,156,172,32)
  CountSuffix = U @(32,228,184,170,239,188,154)
  VendorDirty = U @(67,97,100,101,110,99,101,32,229,174,152,230,150,185,32,97,117,116,111,108,111,97,100,32,230,160,185,231,155,174,229,189,149,228,187,141,230,156,137,230,151,167,229,162,158,229,188,186,232,132,154,230,156,172,239,188,154)
  FoundLog = U @(230,137,190,229,136,176,229,144,175,229,138,168,230,151,165,229,191,151,32,108,97,117,110,99,104,101,114,95,108,97,116,101,115,116,46,108,111,103,239,188,154)
  NoLog = U @(230,156,170,230,137,190,229,136,176,229,144,175,229,138,168,230,151,165,229,191,151,32,108,97,117,110,99,104,101,114,95,108,97,116,101,115,116,46,108,111,103,239,188,154)
  ApiOk = U @(229,185,179,229,143,176,32,65,80,73,32,230,173,163,229,184,184,239,188,154)
  ApiBad = U @(229,185,179,229,143,176,32,65,80,73,32,232,191,148,229,155,158,229,188,130,229,184,184,239,188,154)
  ApiMissing = U @(56,55,54,53,45,56,55,55,53,32,230,156,170,229,143,145,231,142,176,229,143,175,231,148,168,229,185,179,229,143,176,230,156,141,229,138,161,239,188,140,232,175,183,229,133,136,232,191,144,232,161,140,32,229,144,175,229,138,168,231,161,172,228,187,182,230,149,136,231,142,135,229,183,165,229,133,183,233,155,134,46,98,97,116,32,230,136,150,32,108,97,117,110,99,104,95,116,111,111,108,95,115,117,105,116,101,46,112,115,49)
  Failures = U @(232,175,138,230,150,173,229,164,177,232,180,165,233,161,185,239,188,154)
  Passed = U @(232,175,138,230,150,173,233,128,154,232,191,135,227,128,130,232,175,183,233,135,141,229,144,175,32,79,114,67,65,68,32,67,97,112,116,117,114,101,32,229,144,142,230,163,128,230,159,165,32,105,110,115,116,97,51,54,48,95,72,87,32,232,143,156,229,141,149,227,128,130)
}

function Add-Failure {
  param([string]$Message)
  $Failures.Add($Message) | Out-Null
  Write-Host "FAIL $Message" -ForegroundColor Red
}

function Add-Ok {
  param([string]$Message)
  Write-Host "OK   $Message" -ForegroundColor Green
}

function Test-Loader {
  param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) {
    Add-Failure "$($S.NoLoader)$Path"
    return
  }
  $decoded = $Gbk.GetString([System.IO.File]::ReadAllBytes($Path))
  $checks = @(
    @($S.MenuOpen, $decoded.Contains($S.OpenLine)),
    @($S.MenuExport, $decoded.Contains($S.ExportLine)),
    @($S.NoLegacy, -not $decoded.Contains("orcad_enhanced_tools.tcl")),
    @($S.NoRename, -not $decoded.Contains("rename RegisterAction")),
    @($S.NoOther, -not $decoded.Contains($S.OtherScripts))
  )
  foreach ($check in $checks) {
    if ($check[1]) { Add-Ok "$($check[0]) $Path" } else { Add-Failure "$($check[0]) $Path" }
  }
}

function Test-PlatformApi {
  param([int]$Port)
  try {
    $request = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$Port/api/platform/status")
    $request.Timeout = 1500
    $response = $request.GetResponse()
    $reader = [System.IO.StreamReader]::new($response.GetResponseStream())
    $content = $reader.ReadToEnd()
    $reader.Close()
    $response.Close()
    $payload = $content | ConvertFrom-Json
    if ($payload.status -eq "ok" -and $payload.tools -eq 6) {
      Add-Ok "$($S.ApiOk)http://127.0.0.1:$Port/api/platform/status"
      Write-Host $content
      return $true
    }
    Add-Failure "$($S.ApiBad)http://127.0.0.1:$Port/api/platform/status"
  } catch {
    return $false
  }
  return $false
}

Write-Host $S.PlatformDiag -ForegroundColor Cyan
Write-Host "$($S.Root)$Root"

foreach ($dir in Find-CadenceAutoLoadDirs) {
  $backups = @(Get-ChildItem -LiteralPath $dir -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "_disabled_hwagent_loader_*" -or $_.Name -like "_disabled_custom_scripts_*" })
  if ($backups.Count -eq 0) {
    Add-Ok "$($S.AutoLoadBackupClean)$dir"
  } elseif ($FixVendorAutoLoad) {
    $moved = Move-HwAgentAutoLoadBackupDirs -AutoLoadDir $dir
    Add-Ok "$($S.AutoLoadBackupMoved)$($moved.Count)$($S.CountSuffix)$dir"
  } else {
    Add-Failure "$($S.AutoLoadBackupDirty)$dir"
  }
  Test-Loader -Path (Join-Path $dir "iac_bom_tool.tcl")
}

foreach ($dir in Find-CadenceVendorAutoLoadDirs) {
  $custom = @(Get-ChildItem -Path $dir -File -Filter "orCAD_Enhanced_Tools_V*.tcl*" -ErrorAction SilentlyContinue)
  if ($custom.Count -eq 0) {
    Add-Ok "$($S.VendorClean)$dir"
  } elseif ($FixVendorAutoLoad) {
    $moved = Disable-HwAgentVendorAutoLoadScripts -VendorAutoLoadDir $dir
    Add-Ok "$($S.MovedOld)$($moved.Count)$($S.CountSuffix)$dir"
  } else {
    Add-Failure "$($S.VendorDirty)$dir"
  }
}

$runtimeLog = Join-Path $Root "data\reports\runtime\launcher_latest.log"
if (Test-Path -LiteralPath $runtimeLog) {
  Add-Ok "$($S.FoundLog)$runtimeLog"
  Get-Content -LiteralPath $runtimeLog -Tail 8 -Encoding UTF8
} else {
  Add-Failure "$($S.NoLog)$runtimeLog"
}

$probeLog = Join-Path $Root "data\reports\runtime\cadence_loader_probe.log"
if (Test-Path -LiteralPath $probeLog) {
  Add-Ok "Capture loader probe log cadence_loader_probe.log: $probeLog"
  Get-Content -LiteralPath $probeLog -Tail 8 -Encoding UTF8
} else {
  Write-Host "INFO cadence_loader_probe.log not found; restart OrCAD Capture to generate it." -ForegroundColor Yellow
}

$apiOk = $false
foreach ($port in $Ports) {
  if (Test-PlatformApi -Port $port) {
    $apiOk = $true
    break
  }
}
if (-not $apiOk) {
  Add-Failure $S.ApiMissing
}

if ($Failures.Count -gt 0) {
  Write-Host ""
  Write-Host "$($S.Failures)$($Failures.Count)" -ForegroundColor Red
  foreach ($failure in $Failures) { Write-Host "- $failure" -ForegroundColor Red }
  exit 1
}

Write-Host ""
Write-Host $S.Passed -ForegroundColor Green
