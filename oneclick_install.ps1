param([switch]$Silent, [switch]$NoStart)
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $Root "install.ps1") -InstallRoot $Root -NoStart:$NoStart
if (-not $?) { exit 1 }
exit 0
