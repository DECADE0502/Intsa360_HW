param([switch]$Silent)

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "HWAgent 一键安装"

if (-not $Silent) {
  Write-Host "==========================================" -ForegroundColor Cyan
  Write-Host "  Insta360 硬件效率工具集 - 一键安装" -ForegroundColor Cyan
  Write-Host "==========================================" -ForegroundColor Cyan
  Write-Host ""
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallScript = Join-Path $ScriptDir "install.ps1"

# ── 1. 检查 Python ──
if (-not $Silent) { Write-Host "[1/4] 检查 Python 环境..." -ForegroundColor White }
$pythonExe = $null

$pythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue
if ($pythonCmd) {
    $pythonExe = "python"
    if (-not $Silent) { Write-Host "  $(python --version 2>&1)" -ForegroundColor Green }
}

if (-not $pythonExe) {
    $codexPy = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $codexPy) {
        $pythonExe = $codexPy
        if (-not $Silent) { Write-Host "  [i] 找到 Codex 内置 Python: $codexPy" -ForegroundColor Yellow }
    }
}

if (-not $pythonExe) {
    $venvPy = Join-Path $ScriptDir ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPy) {
        $pythonExe = $venvPy
        if (-not $Silent) { Write-Host "  [i] 找到虚拟环境 Python: $venvPy" -ForegroundColor Yellow }
    }
}

if (-not $pythonExe) {
    if (-not $Silent) {
        Write-Host "  [X] 未找到 Python，请先安装 Python 3" -ForegroundColor Red
        Write-Host "      下载: https://www.python.org/downloads/" -ForegroundColor Gray
        Write-Host "      安装时务必勾选 Add Python to PATH" -ForegroundColor Gray
    }
    exit 1
}
if (-not $Silent) {
    Write-Host "  [OK] Python 已就绪" -ForegroundColor Green
    Write-Host ""
}

# ── 2. 检查 openpyxl ──
if (-not $Silent) { Write-Host "[2/4] 检查 openpyxl 依赖..." -ForegroundColor White }
$hasOpenpyxl = & $pythonExe -c "import openpyxl" 2>$null
if ($LASTEXITCODE -ne 0) {
    if (-not $Silent) { Write-Host "  [!] openpyxl 未安装，正在自动安装..." -ForegroundColor Yellow }
    & $pythonExe -m pip install openpyxl
    if ($LASTEXITCODE -ne 0) {
        if (-not $Silent) { Write-Host "  [X] openpyxl 安装失败，请手动执行: pip install openpyxl" -ForegroundColor Red }
        exit 1
    }
}
if (-not $Silent) {
    Write-Host "  [OK] openpyxl 已就绪" -ForegroundColor Green
    Write-Host ""
}

# ── 3. 检查 Node.js（可选） ──
if (-not $Silent) { Write-Host "[3/4] 检查 Node.js（可选）..." -ForegroundColor White }
$nodeCmd = Get-Command node.exe -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    if (-not $Silent) { Write-Host "  [i] Node.js 未安装，将跳过前端编译（使用预构建界面）" -ForegroundColor Yellow }
} else {
    if (-not $Silent) {
        Write-Host "  $(node --version 2>&1)" -ForegroundColor Green
        Write-Host "  [OK] Node.js 已就绪" -ForegroundColor Green
    }
}
if (-not $Silent) { Write-Host "" }

# ── 4. 执行安装 ──
if (-not $Silent) {
    Write-Host "[4/4] 开始安装..." -ForegroundColor White
    Write-Host "==========================================" -ForegroundColor Gray
    Write-Host ""
}

if (-not (Test-Path -LiteralPath $InstallScript)) {
    if (-not $Silent) { Write-Host "  [X] 未找到 install.ps1，请确认文件完整性" -ForegroundColor Red }
    exit 1
}

& powershell -NoProfile -ExecutionPolicy Bypass -File $InstallScript
if ($LASTEXITCODE -ne 0) {
    if (-not $Silent) {
        Write-Host ""
        Write-Host "  [X] 安装过程出错，请查看上方日志" -ForegroundColor Red
    }
    exit 1
}

if (-not $Silent) {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "  安装成功！" -ForegroundColor Green
    Write-Host ""
    Write-Host "  使用方式:" -ForegroundColor White
    Write-Host "    双击 Insta360_HW.exe 打开平台" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  如已安装 Cadence，请重启 OrCAD Capture" -ForegroundColor Yellow
    Write-Host "  以加载 insta360_HW 菜单" -ForegroundColor Yellow
    Write-Host "==========================================" -ForegroundColor Cyan
}
