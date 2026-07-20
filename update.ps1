# 遗留开发脚本，不支持 v3 安装布局，日常请勿使用。
param([switch]$OpenPlatform)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Lifecycle V2 performs verified updates from the platform UI."
Write-Host "Opening Insta360_HW so you can check and install the release."
Start-Process -FilePath (Join-Path $Root "Insta360_HW.exe") | Out-Null
