$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $Root "update.ps1") -OpenPlatform
if (-not $?) { exit 1 }
exit 0
