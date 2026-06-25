param(
  [string]$Repo = "https://github.com/DECADE0502/Intsa360_HW.git",
  [string]$Branch = "main",
  [ValidateSet("zip", "git")]
  [string]$Method = "zip"
)

$ErrorActionPreference = "Stop"

function Get-Text {
  param([Parameter(Mandatory=$true)][string]$Base64)
  return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Base64))
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

. (Join-Path $Root "scripts\lib\Paths.ps1")
. (Join-Path $Root "scripts\lib\Update.ps1")
. (Join-Path $Root "scripts\lib\Cadence.ps1")
. (Join-Path $Root "scripts\lib\TclScripts.ps1")

$Root = Get-HwAgentRoot -StartPath $Root
Write-Host "__HWAGENT_PROGRESS__ 0 开始更新..."
Write-Host (Get-Text "5byA5aeL5pu05paw56Gs5Lu25pWI546H5bel5YW36ZuGLi4u")
Write-Host (Get-Text "55So5oi35pWw5o2u5L+d5oqk6IyD5Zu077yaZGF0YSwgdXBsb2Fkcywgb3V0cHV0cywgaGlzdG9yeSwgY29uZmlnL2xvY2FsLmpzb24=")

# Default to zip-based update so end users need nothing installed (no git).
# Falls back to git only when -Method git is passed explicitly.
$UpdateMethod = if ($Method) { $Method } else { "zip" }

Invoke-HwAgentUpdate -Root $Root -Repo $Repo -Branch $Branch -Method $UpdateMethod | Out-Null

$node = Get-Command node.exe -ErrorAction SilentlyContinue
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($node -and $npm -and (Test-Path -LiteralPath (Join-Path $Root "frontend\package.json"))) {
  & (Join-Path $Root "scripts\build_frontend.ps1")
}

$Python = Find-Python -Root $Root
foreach ($vendorAutoLoadDir in Find-CadenceVendorAutoLoadDirs) {
  Disable-HwAgentVendorAutoLoadScripts -VendorAutoLoadDir $vendorAutoLoadDir | Out-Null
}
$AutoLoadDirs = Find-CadenceAutoLoadDirs
foreach ($autoLoadDir in $AutoLoadDirs) {
  Move-HwAgentAutoLoadBackupDirs -AutoLoadDir $autoLoadDir | Out-Null
}
Install-CadenceLoader -ToolRoot $Root -PythonPath $Python -AutoLoadDirs $AutoLoadDirs | Out-Null

$verify = Join-Path $Root "scripts\verify_all.ps1"
# verify_all needs tests/ and frontend/ source, which only exist in the dev
# repo — installed (runtime) copies lack them. Run it only when present so
# updates on an installed copy don't hard-fail at the verification step.
if ((Test-Path -LiteralPath $verify) -and (Test-Path -LiteralPath (Join-Path $Root "tests"))) {
  Write-Host "__HWAGENT_PROGRESS__ 98 正在验证..."
  Write-Host (Get-Text "5byA5aeL6aqM6K+BLi4u")
  & $verify
  if ($LASTEXITCODE -ne 0) { throw (Get-Text "6aqM6K+B5aSx6LSl") }
} else {
  Write-Host (Get-Text "5pyq5om+5Yiw6aqM6K+B6ISa5pys77yM6Lez6L+H6aqM6K+B44CC")
}

Write-Host (Get-Text "5pu05paw5rWB56iL5a6M5oiQ44CC")
Write-Host "__HWAGENT_PROGRESS__ 100 更新完成，正在重启服务..."
Write-Host "__HWAGENT_DONE__"
