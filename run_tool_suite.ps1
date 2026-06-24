$ErrorActionPreference = "Stop"

$Python = "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Port = if ($args.Count -gt 0) { $args[0] } else { "8765" }

Set-Location $Root
& $Python app\backend\suite_app.py --port $Port
