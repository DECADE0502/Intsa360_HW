param(
  [Parameter(Mandatory=$true)][string]$NewVersion,
  [string]$Root = "",
  [string]$Revision = ""
)

# bump_version.ps1 stamps VERSION / REVISION / HWAgent_Setup.iss / UPDATE_NOTICE.json
# with a single new version + revision so pre_release_check can trust these files
# as a coherent set.
#
# IMPORTANT: REVISION captures the CURRENT HEAD, i.e. the PARENT of the release
# commit that is about to be created after this script runs. It is NOT expected
# to equal the release commit itself - that commit's SHA is unknowable until
# it exists. The consistency invariant (see test_version_metadata_is_consistent)
# is therefore "REVISION is an ancestor of HEAD", not equality. Do not "fix"
# this by trying to rewrite REVISION after the commit is made - it would
# only push the same off-by-one one step forward.

$ErrorActionPreference = "Stop"

if ($NewVersion -notmatch '^\d+\.\d+\.\d+(-[A-Za-z0-9.-]+)?$') {
  throw "invalid semver: $NewVersion"
}

if (-not $Root) {
  $Root = Split-Path -Parent $PSScriptRoot
}
$Root = (Resolve-Path -LiteralPath $Root).Path

if (-not $Revision) {
  try {
    $Revision = (& git -C $Root rev-parse HEAD 2>$null).Trim()
  } catch {
    $Revision = ""
  }
}

function Write-HwAgentUtf8NoBom {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$Value
  )
  $encoding = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Value, $encoding)
}

Set-Content -Encoding ASCII -NoNewline -LiteralPath (Join-Path $Root "VERSION") -Value $NewVersion
Set-Content -Encoding ASCII -NoNewline -LiteralPath (Join-Path $Root "REVISION") -Value $Revision

$issPath = Join-Path $Root "HWAgent_Setup.iss"
if (-not (Test-Path -LiteralPath $issPath)) { throw "HWAgent_Setup.iss not found: $issPath" }
$iss = Get-Content -Raw -LiteralPath $issPath -Encoding UTF8
$iss = $iss -replace '#define MyAppVersion ".*"', "#define MyAppVersion `"$NewVersion`""
Write-HwAgentUtf8NoBom -Path $issPath -Value $iss

$noticePath = Join-Path $Root "UPDATE_NOTICE.json"
if (-not (Test-Path -LiteralPath $noticePath)) { throw "UPDATE_NOTICE.json not found: $noticePath" }
$notice = Get-Content -Raw -LiteralPath $noticePath -Encoding UTF8 | ConvertFrom-Json
$notice.version = $NewVersion
$notice.revision = $Revision
$notice.date = (Get-Date -Format "yyyy-MM-dd")
Write-HwAgentUtf8NoBom -Path $noticePath -Value (($notice | ConvertTo-Json -Depth 10) + "`r`n")

Write-Host "Bumped to $NewVersion @ $Revision"
