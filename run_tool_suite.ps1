param(
  [switch]$DevOnly,
  [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

if (-not $DevOnly) {
  Write-Error "该脚本仅供开发调试。请使用 launch_tool_suite.ps1 启动平台；如确需裸启动，请显式传入 -DevOnly。"
  exit 2
}
Write-Warning "开发专用入口：不写服务身份，不做健康校验。"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Root "scripts\lib\Paths.ps1")
$Root = Get-HwAgentRoot -StartPath $Root
$Python = Find-Python -Root $Root
Set-Location $Root
& $Python app\backend\suite_app.py --port $Port
