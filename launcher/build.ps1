param(
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Platform root is two levels up from this script (launcher\ -> root).
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$Source = Join-Path $ScriptDir "Insta360_HW.cs"
$Icon = Join-Path $Root "app\frontend\assets\insta360_icon.ico"
$Output = Join-Path $Root "Insta360_HW.exe"
$AssemblyInfoTemplate = Join-Path $ScriptDir "AssemblyInfo.cs.template"
$AssemblyInfo = Join-Path $ScriptDir "AssemblyInfo.cs"
$VersionFile = Join-Path $Root "VERSION"

if (-not (Test-Path -LiteralPath $Source)) { throw "Missing source: $Source" }
if (-not (Test-Path -LiteralPath $Icon)) { throw "Missing icon: $Icon" }
if (-not (Test-Path -LiteralPath $AssemblyInfoTemplate)) { throw "Missing template: $AssemblyInfoTemplate" }
if (-not (Test-Path -LiteralPath $VersionFile)) { throw "Missing version file: $VersionFile" }

# Read VERSION and normalize to 4-part numeric (e.g. "0.2.17-rc1" -> "0.2.17.0").
# AssemblyVersion / AssemblyFileVersion reject non-numeric pre-release tags, so
# we strip them before padding to a 4-part tuple that Windows FileVersion accepts.
$rawVersion = (Get-Content -LiteralPath $VersionFile -Raw -Encoding UTF8).Trim()
$cleanVersion = ($rawVersion -replace '-[a-zA-Z0-9.-]+', '')
$parts = $cleanVersion.Split('.')
while ($parts.Length -lt 4) { $parts += '0' }
$fourPartVersion = ($parts[0..3] -join '.')
if ($fourPartVersion -notmatch '^\d+\.\d+\.\d+\.\d+$') {
  throw "VERSION '$rawVersion' cannot be normalized to 4-part numeric: got '$fourPartVersion'"
}

# Materialize AssemblyInfo.cs from template. UTF-8 no BOM keeps csc happy on pure
# ASCII content — non-ASCII strings are intentionally excluded from the template.
$templateText = Get-Content -LiteralPath $AssemblyInfoTemplate -Raw -Encoding UTF8
$assemblyInfoText = $templateText -replace '\{\{VERSION\}\}', $fourPartVersion
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($AssemblyInfo, $assemblyInfoText, $utf8NoBom)

# Locate a usable C# compiler. Prefer .NET Framework csc.exe (always present on
# Windows), then the .NET SDK csc as a fallback. We only need the language and
# the framework libraries for this single-file no-dependency launcher.
$candidates = @()
$fwRoot = Join-Path $env:SystemDrive "Windows\Microsoft.NET\Framework64"
if (Test-Path -LiteralPath $fwRoot) {
  $candidates += Get-ChildItem -Path $fwRoot -Filter "csc.exe" -Recurse -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    ForEach-Object { $_.FullName }
}
$fwRoot32 = Join-Path $env:SystemDrive "Windows\Microsoft.NET\Framework"
if (Test-Path -LiteralPath $fwRoot32) {
  $candidates += Get-ChildItem -Path $fwRoot32 -Filter "csc.exe" -Recurse -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    ForEach-Object { $_.FullName }
}
$csc = $candidates | Select-Object -First 1
if (-not $csc) { throw "No csc.exe found under .NET Framework. Install .NET Framework or .NET SDK." }

Write-Host ("Building Insta360_HW.exe with: " + $csc)
Write-Host ("  source:       " + $Source)
Write-Host ("  assemblyinfo: " + $AssemblyInfo)
Write-Host ("  icon:         " + $Icon)
Write-Host ("  output:       " + $Output)
Write-Host ("  version:      " + $fourPartVersion)

if ($DryRun) {
  Write-Host "DRYRUN — no compile performed."
  exit 0
}

# /target:winexe -> GUI subsystem, no console window on launch.
& $csc /nologo /target:winexe /optimize+ /reference:System.Windows.Forms.dll /reference:System.Runtime.Serialization.dll /win32icon:"$Icon" /out:"$Output" "$Source" "$AssemblyInfo"
if ($LASTEXITCODE -ne 0) { throw "csc failed with exit code $LASTEXITCODE" }

if (-not (Test-Path -LiteralPath $Output)) { throw "Build did not produce $Output" }
$size = (Get-Item -LiteralPath $Output).Length
Write-Host ("OK — Insta360_HW.exe ({0:N0} bytes)" -f $size) -ForegroundColor Green
