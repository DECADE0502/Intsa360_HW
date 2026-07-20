# 遗留开发脚本，不支持 v3 安装布局，日常请勿使用。
param([switch]$Silent, [switch]$NoStart)
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $Root "install.ps1") -InstallRoot $Root -NoStart:$NoStart
if (-not $?) { exit 1 }
exit 0
