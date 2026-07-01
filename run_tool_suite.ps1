$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Root "scripts\lib\Paths.ps1")
$Root = Get-HwAgentRoot -StartPath $Root
$Python = Find-Python -Root $Root
$Port = if ($args.Count -gt 0) { $args[0] } else { "8765" }

Set-Location $Root
& $Python app\backend\suite_app.py --port $Port
