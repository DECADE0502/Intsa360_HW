param([switch]$OpenPlatform)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Lifecycle V2 performs verified updates from the platform UI."
Write-Host "Opening Insta360_HW so you can check and install the release."
Start-Process -FilePath (Join-Path $Root "Insta360_HW.exe") | Out-Null
