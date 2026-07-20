# 遗留开发脚本，不支持 v3 安装布局，日常请勿使用。
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $Root "update.ps1") -OpenPlatform
if (-not $?) { exit 1 }
exit 0
