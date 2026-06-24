param(
  [Parameter(Mandatory = $true)][string]$Out
)
# ============================================================
# 驱动 OrCAD Capture 导出当前设计的 BOM 到 $Out。
# Capture 的 BOM 导出接口随版本不同，这里是“唯一的版本相关配置点”。
# 顺序尝试：1) Capture COM 自动导出  2) 复用最近一次手动导出  3) 报错（由 TCL 兜底）。
# ============================================================
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Out) | Out-Null

# ---- 方式 1：Capture COM 自动导出（按你的 Capture 版本启用/调整下面这段）----
try {
  $app = [Runtime.InteropServices.Marshal]::GetActiveObject("OrCAD.Application")
  # === 配置点（版本相关）===
  # 不同版本可能是：
  #   $app.BuildBOM($Out)              # 伪代码：直接导出 BOM 到文件
  #   或通过 $app.DesignList / 当前工程对象的导出方法
  # 请按本地 Capture 的自动化文档替换为真实调用，使其把 BOM 写入 $Out：
  throw "COM BOM 导出未配置（请在 cadence_export.ps1 方式1 中按版本填入真实调用）"
  Write-Output "COM 导出成功：$Out"
  exit 0
} catch {
  Write-Host "方式1(COM)不可用：$($_.Exception.Message)" -ForegroundColor Yellow
}

# ---- 方式 2：复用最近一次手动导出的 BOM（在常见目录里找最新的 *.xlsx）----
$candidates = @()
foreach ($dir in @("$env:USERPROFILE\Desktop", "$env:USERPROFILE\Documents")) {
  if (Test-Path $dir) {
    $candidates += Get-ChildItem -Path $dir -Filter "*.xlsx" -File -ErrorAction SilentlyContinue |
      Where-Object { $_.LastWriteTime -gt (Get-Date).AddMinutes(-10) }
  }
}
$latest = $candidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latest) {
  Copy-Item $latest.FullName $Out -Force
  Write-Output "已复用最近导出：$($latest.FullName) -> $Out"
  exit 0
}

# ---- 方式 3：都失败，报错让 TCL 兜底（仅打开工具，提示手动导出）----
throw "未能自动获取 BOM。请在 Capture 用 Tools>Bill of Materials 导出后重试，或直接在工具里上传。"
