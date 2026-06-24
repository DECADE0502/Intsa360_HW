param([string]$CaptureAutoLoadDir = "")
# ============================================================
# 安装 insta360_HW 工具的 Capture 集成：
#   - 把工具绝对路径写进 iac_bom_tool.tcl（替换 {{TOOL_ROOT}}）
#   - 复制到 Capture 真正自动加载的 capAutoLoad 目录
#     （SPB 17.4/24.x：%HOME%\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad）
#   - 创建 data\inbox
# ============================================================
$ErrorActionPreference = "Stop"

$CadenceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ToolRoot = Split-Path -Parent $CadenceDir
$ToolRootFwd = $ToolRoot -replace "\\", "/"

New-Item -ItemType Directory -Force -Path (Join-Path $ToolRoot "data\inbox") | Out-Null

# 1) 生成已嵌入绝对路径的 tcl
$tplPath = Join-Path $CadenceDir "iac_bom_tool.tcl"
$content = (Get-Content -Raw -Encoding UTF8 $tplPath) -replace "\{\{TOOL_ROOT\}\}", $ToolRootFwd
$deployed = Join-Path $CadenceDir "iac_bom_tool.deployed.tcl"
# 关键：以 GBK(cp936) 无 BOM 写出。Capture 17.4 的 Tcl 按系统码页读取，
# GBK 才能让中文菜单与中文路径(工具集)正确，否则点击无反应/乱码。
[System.IO.File]::WriteAllText($deployed, $content, [System.Text.Encoding]::GetEncoding(936))
Write-Host "已生成(GBK): $deployed" -ForegroundColor Green

# 2) 定位 Capture 真正自动加载的 capAutoLoad 目录
$targets = @()
if ($CaptureAutoLoadDir -ne "") { $targets += $CaptureAutoLoadDir }
if ($env:HOME) { $targets += (Join-Path $env:HOME "cdssetup\OrCAD_Capture\tclscripts\capAutoLoad") }
# 跟随已存在的 PLMMenu.tcl（PartSolution）所在目录。显式指定目录时不做全盘搜索，避免安装脚本卡住。
if ($CaptureAutoLoadDir -eq "") {
  $existing = Get-ChildItem -Path C:\, D:\ -Recurse -Filter "PLMMenu.tcl" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "cdssetup" } | Select-Object -First 1
  if ($existing) { $targets += $existing.DirectoryName }
}

$installed = $false
foreach ($dir in ($targets | Select-Object -Unique)) {
  try {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Copy-Item $deployed (Join-Path $dir "iac_bom_tool.tcl") -Force
    Write-Host "已安装到: $dir\iac_bom_tool.tcl" -ForegroundColor Green
    $installed = $true
    break
  } catch {
    Write-Host "写入失败: $dir（$($_.Exception.Message)）" -ForegroundColor DarkYellow
  }
}

if ($installed) {
  Write-Host "请重启 OrCAD Capture。菜单『insta360_HW』应出现；" -ForegroundColor Cyan
  Write-Host "也可在 Capture 的 Command Window 输入 iac(打开工具) / iacx(导出并处理)。" -ForegroundColor Cyan
} else {
  Write-Host "未能自动定位 capAutoLoad。手动：把 $deployed 复制为" -ForegroundColor Yellow
  Write-Host "  %HOME%\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad\iac_bom_tool.tcl  后重启 Capture" -ForegroundColor Yellow
  Write-Host "或重跑：install_cadence_integration.ps1 -CaptureAutoLoadDir <该目录>" -ForegroundColor Yellow
}

