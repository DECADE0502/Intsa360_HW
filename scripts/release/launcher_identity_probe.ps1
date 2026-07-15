param(
  [Parameter(Mandatory=$true)][string]$LauncherPath,
  [Parameter(Mandatory=$true)][string]$RuntimeRoot,
  [Parameter(Mandatory=$true)][string]$Version,
  [Parameter(Mandatory=$true)][string]$Revision
)

$ErrorActionPreference = "Stop"
$LauncherPath = [System.IO.Path]::GetFullPath($LauncherPath)
$RuntimeRoot = [System.IO.Path]::GetFullPath($RuntimeRoot)
if (-not (Test-Path -LiteralPath $LauncherPath -PathType Leaf)) { throw "Launcher is missing: $LauncherPath" }
if (-not (Test-Path -LiteralPath $RuntimeRoot -PathType Container)) { throw "Runtime is missing: $RuntimeRoot" }
if ($Version -notmatch '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?$') {
  throw "Runtime version is invalid: $Version"
}
if ($Revision -notmatch '^[a-f0-9]{40}$') { throw "Runtime revision is invalid: $Revision" }

$identityNames = @("VERSION", "REVISION", "install_manifest.json")
foreach ($name in $identityNames) {
  $path = Join-Path $RuntimeRoot $name
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Runtime identity file is missing: $path" }
  $bytes = [System.IO.File]::ReadAllBytes($path)
  if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    throw "Runtime identity must be UTF-8 without BOM: $path"
  }
}

$probeRoot = Join-Path ([System.IO.Path]::GetTempPath()) `
  ("insta360_launcher_identity_" + [guid]::NewGuid().ToString("N"))
$installRoot = Join-Path $probeRoot "installed app"
$relative = "runtime/$Version+$Revision"
$runtimeProbe = Join-Path $installRoot ($relative.Replace('/', '\'))
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

try {
  New-Item -ItemType Directory -Force -Path $runtimeProbe | Out-Null
  foreach ($name in $identityNames) {
    Copy-Item -LiteralPath (Join-Path $RuntimeRoot $name) -Destination (Join-Path $runtimeProbe $name) -Force
  }
  $metadata = [ordered]@{
    schema_version = 3
    product = "Insta360_HW"
    layout = "versioned-runtime-v3"
    active_runtime = $relative
  } | ConvertTo-Json -Depth 4
  [System.IO.File]::WriteAllText((Join-Path $installRoot "installation.json"), `
    $metadata + [Environment]::NewLine, $utf8NoBom)

  $assembly = [System.Reflection.Assembly]::Load([System.IO.File]::ReadAllBytes($LauncherPath))
  $program = $assembly.GetType("Program", $true)
  $method = $program.GetMethod("ResolveActiveRuntime", `
    [System.Reflection.BindingFlags]::NonPublic -bor [System.Reflection.BindingFlags]::Static)
  if ($null -eq $method) { throw "Launcher runtime resolver is missing." }
  $invokeArguments = New-Object 'object[]' 1
  $invokeArguments[0] = [string]$installRoot
  try {
    $resolved = [string]$method.Invoke($null, $invokeArguments)
  } catch {
    $failure = if ($null -ne $_.Exception.InnerException) { $_.Exception.InnerException } else { $_.Exception }
    throw $failure
  }
  $expected = [System.IO.Path]::GetFullPath($runtimeProbe).TrimEnd('\')
  if (-not [string]::Equals($resolved.TrimEnd('\'), $expected, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Launcher resolved the wrong runtime: $resolved"
  }
} finally {
  if (Test-Path -LiteralPath $probeRoot) {
    Remove-Item -LiteralPath $probeRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
}

Write-Host "Launcher runtime identity verified: $Version+$Revision"
