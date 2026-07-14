param(
  [string]$Token = "",
  [string]$Repo = "DECADE0502/Intsa360_HW",
  [string]$Tag = "",
  [string]$ZipPath = "",
  [string]$SetupPath = "",
  [switch]$SkipBuild,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$Workspace = Split-Path -Parent $Root
$Version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw -Encoding UTF8).Trim()
if ([string]::IsNullOrWhiteSpace($Tag)) { $Tag = "v$Version" }
if (-not $Tag.StartsWith("v")) { $Tag = "v$Tag" }
if ($Tag -cne "v$Version") { throw "Release tag $Tag must exactly match VERSION $Version." }

$Revision = (& git -C $Root rev-parse HEAD).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $Revision -notmatch '^[a-f0-9]{40}$') {
  throw "A full git revision is required for release."
}
if (-not $DryRun) {
  $dirty = @(& git -C $Root status --porcelain --untracked-files=normal)
  if ($LASTEXITCODE -ne 0) { throw "Unable to verify the git worktree." }
  if ($dirty.Count -gt 0) { throw "Production release requires a clean git worktree." }
}

function Get-HttpStatusCode {
  param([Parameter(Mandatory=$true)]$ErrorRecord)
  try {
    if ($null -ne $ErrorRecord.Exception.Response) {
      return [int]$ErrorRecord.Exception.Response.StatusCode
    }
  } catch {}
  return 0
}

function Assert-ReleaseManifest {
  param(
    [Parameter(Mandatory=$true)][string]$ReleaseRoot,
    [Parameter(Mandatory=$true)][string]$Path
  )
  $python = Join-Path $ReleaseRoot "runtime\python\python.exe"
  $validator = Join-Path $ReleaseRoot "app\backend\release_manifest.py"
  if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Embedded Python is missing from the release tree." }
  if (-not (Test-Path -LiteralPath $validator -PathType Leaf)) { throw "Release manifest validator is missing from the release tree." }
  $output = @(& $python $validator $Path 2>&1)
  if ($LASTEXITCODE -ne 0) {
    throw ("Generated release manifest failed the client contract: " + ($output -join " "))
  }
}

function Get-GitHubReleaseByTag {
  param(
    [Parameter(Mandatory=$true)][string]$Api,
    [Parameter(Mandatory=$true)][string]$ReleaseTag,
    [Parameter(Mandatory=$true)][hashtable]$Headers
  )
  $encodedTag = [uri]::EscapeDataString($ReleaseTag)
  try {
    return Invoke-RestMethod -Uri "$Api/releases/tags/$encodedTag" -Headers $Headers -Method Get
  } catch {
    if ((Get-HttpStatusCode -ErrorRecord $_) -ne 404) { throw }
  }

  for ($page = 1; $page -le 10; $page++) {
    $items = @(Invoke-RestMethod -Uri "$Api/releases?per_page=100&page=$page" -Headers $Headers -Method Get)
    foreach ($item in $items) {
      if ([string]$item.tag_name -ceq $ReleaseTag) { return $item }
    }
    if ($items.Count -lt 100) { break }
  }
  return $null
}

function Resolve-GitHubTagRevision {
  param(
    [Parameter(Mandatory=$true)][string]$Api,
    [Parameter(Mandatory=$true)][string]$ReleaseTag,
    [Parameter(Mandatory=$true)][hashtable]$Headers
  )
  $encodedTag = [uri]::EscapeDataString($ReleaseTag)
  try {
    $reference = Invoke-RestMethod -Uri "$Api/git/ref/tags/$encodedTag" -Headers $Headers -Method Get
  } catch {
    if ((Get-HttpStatusCode -ErrorRecord $_) -eq 404) { return "" }
    throw
  }

  $object = $reference.object
  for ($depth = 0; $depth -lt 8; $depth++) {
    $type = [string]$object.type
    $sha = ([string]$object.sha).ToLowerInvariant()
    if ($type -eq "commit" -and $sha -match '^[a-f0-9]{40}$') { return $sha }
    if ($type -ne "tag" -or $sha -notmatch '^[a-f0-9]{40}$') {
      throw "Git tag $ReleaseTag does not resolve to a commit."
    }
    $tagObject = Invoke-RestMethod -Uri "$Api/git/tags/$sha" -Headers $Headers -Method Get
    $object = $tagObject.object
  }
  throw "Git tag $ReleaseTag has too many annotated-tag levels."
}

function Remove-ReleaseAsset {
  param(
    [Parameter(Mandatory=$true)]$Asset,
    [Parameter(Mandatory=$true)][string]$Api,
    [Parameter(Mandatory=$true)][hashtable]$Headers
  )
  Invoke-RestMethod -Uri "$Api/releases/assets/$($Asset.id)" -Headers $Headers -Method Delete | Out-Null
}

function Publish-StagedAsset {
  param(
    [Parameter(Mandatory=$true)]$Release,
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$CanonicalName,
    [Parameter(Mandatory=$true)][string]$ContentType,
    [Parameter(Mandatory=$true)][long]$ExpectedSize,
    [Parameter(Mandatory=$true)][string]$UploadId,
    [Parameter(Mandatory=$true)][string]$Api,
    [Parameter(Mandatory=$true)][hashtable]$Headers
  )
  $prefix = $CanonicalName + ".upload-"
  foreach ($asset in @($Release.assets)) {
    if (([string]$asset.name).StartsWith($prefix, [System.StringComparison]::Ordinal)) {
      Remove-ReleaseAsset -Asset $asset -Api $Api -Headers $Headers
    }
  }
  $stagedName = $prefix + $UploadId
  $uploadBase = ([string]$Release.upload_url) -replace '\{\?name,label\}', ''
  $uri = $uploadBase + "?name=" + [uri]::EscapeDataString($stagedName)
  $asset = Invoke-RestMethod -Uri $uri -Headers $Headers -Method Post -InFile $Path -ContentType $ContentType
  if ([long]$asset.size -ne $ExpectedSize) {
    throw "GitHub reported an unexpected size for staged asset $CanonicalName."
  }
  return $asset
}

function Promote-StagedAsset {
  param(
    [Parameter(Mandatory=$true)]$Asset,
    [Parameter(Mandatory=$true)][string]$CanonicalName,
    [Parameter(Mandatory=$true)]$Release,
    [Parameter(Mandatory=$true)][string]$Api,
    [Parameter(Mandatory=$true)][hashtable]$Headers
  )
  foreach ($existing in @($Release.assets)) {
    if ([string]$existing.name -ceq $CanonicalName) {
      Remove-ReleaseAsset -Asset $existing -Api $Api -Headers $Headers
    }
  }
  $body = @{ name = $CanonicalName } | ConvertTo-Json
  $promoted = Invoke-RestMethod -Uri "$Api/releases/assets/$($Asset.id)" -Headers $Headers `
    -Method Patch -Body $body -ContentType "application/json; charset=utf-8"
  if ([string]$promoted.name -cne $CanonicalName) {
    throw "GitHub did not promote staged asset to $CanonicalName."
  }
}

function Invoke-PublicVerificationWithRetry {
  param(
    [Parameter(Mandatory=$true)][string]$Description,
    [Parameter(Mandatory=$true)][scriptblock]$Operation,
    [int]$Attempts = 10
  )
  $lastError = ""
  for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
    try {
      & $Operation $attempt
      return
    } catch {
      $lastError = $_.Exception.Message
      if ($attempt -lt $Attempts) {
        Start-Sleep -Seconds ([Math]::Min(2 * $attempt, 15))
      }
    }
  }
  throw "$Description failed after $Attempts attempts: $lastError"
}

function Assert-PublicAsset {
  param(
    [Parameter(Mandatory=$true)][string]$Url,
    [Parameter(Mandatory=$true)][long]$ExpectedSize,
    [Parameter(Mandatory=$true)][string]$RevisionToken
  )
  Invoke-PublicVerificationWithRetry -Description "Public asset verification for $Url" -Operation {
    param($attempt)
    $separator = if ($Url.Contains("?")) { "&" } else { "?" }
    $uri = $Url + $separator + "verify=" + $RevisionToken + "-" + $attempt
    $response = Invoke-WebRequest -Uri $uri -Method Head -MaximumRedirection 8 -TimeoutSec 30 `
      -UseBasicParsing -Headers @{ "Cache-Control" = "no-cache" }
    if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 400) {
      throw "HTTP $($response.StatusCode)"
    }
    $lengthValues = @($response.Headers["Content-Length"])
    $lengthHeader = if ($lengthValues.Count -gt 0) { [string]$lengthValues[0] } else { "" }
    $reportedLength = [long]0
    if ($lengthHeader) {
      if (-not [long]::TryParse($lengthHeader, [ref]$reportedLength)) {
        throw "invalid content length $lengthHeader"
      }
      if ($reportedLength -ne $ExpectedSize) {
        throw "content length $reportedLength does not match $ExpectedSize"
      }
    }
  }
}

if (-not $SkipBuild) {
  & (Join-Path $ScriptDir "build_installer.ps1")
  if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }
}

$ReleaseRoot = Join-Path $Workspace "HWAgent_release"
if (-not (Test-Path -LiteralPath $ReleaseRoot -PathType Container)) { throw "Release tree is missing: $ReleaseRoot" }
$releaseVersion = (Get-Content -LiteralPath (Join-Path $ReleaseRoot "VERSION") -Raw -Encoding UTF8).Trim()
$releaseRevision = (Get-Content -LiteralPath (Join-Path $ReleaseRoot "REVISION") -Raw -Encoding UTF8).Trim().ToLowerInvariant()
if ($releaseVersion -cne $Version -or $releaseRevision -cne $Revision) {
  throw "Release tree metadata does not match VERSION and the current git revision."
}

if ([string]::IsNullOrWhiteSpace($SetupPath)) { $SetupPath = Join-Path $Workspace "Insta360_HW_Setup.exe" }
if (-not (Test-Path -LiteralPath $SetupPath -PathType Leaf)) { throw "Setup package is missing: $SetupPath" }
if ([System.IO.Path]::GetFileName($SetupPath) -cne "Insta360_HW_Setup.exe") {
  throw "Setup package must be named Insta360_HW_Setup.exe."
}

$expectedRuntimeName = "Insta360_HW_runtime_v$Version.zip"
if ([string]::IsNullOrWhiteSpace($ZipPath)) { $ZipPath = Join-Path $Workspace $expectedRuntimeName }
if ([System.IO.Path]::GetFileName($ZipPath) -cne $expectedRuntimeName) {
  throw "Runtime package must be named $expectedRuntimeName."
}
if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
Compress-Archive -Path $ReleaseRoot -DestinationPath $ZipPath -CompressionLevel Optimal

$runtimeHash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$runtimeSize = (Get-Item -LiteralPath $ZipPath).Length
$setupHash = (Get-FileHash -LiteralPath $SetupPath -Algorithm SHA256).Hash.ToLowerInvariant()
$setupSize = (Get-Item -LiteralPath $SetupPath).Length
$runtimeName = [System.IO.Path]::GetFileName($ZipPath)
$setupName = [System.IO.Path]::GetFileName($SetupPath)
$releaseBase = "https://github.com/$Repo/releases/download/$Tag"

$noticePath = Join-Path $Root "UPDATE_NOTICE.json"
$notice = if (Test-Path -LiteralPath $noticePath) {
  Get-Content -LiteralPath $noticePath -Raw -Encoding UTF8 | ConvertFrom-Json
} else { [pscustomobject]@{} }
$highlights = if ($notice.highlights) { @($notice.highlights) } else { @() }
$manifest = [ordered]@{
  schema = 2
  product = "Insta360_HW"
  version = $Version
  revision = $Revision
  published_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
  channel = "stable"
  minimum_launcher_version = "0.3.3"
  assets = [ordered]@{
    runtime = [ordered]@{
      name = $runtimeName
      url = "$releaseBase/$runtimeName"
      sha256 = $runtimeHash
      size_bytes = $runtimeSize
    }
    setup = [ordered]@{
      name = $setupName
      url = "$releaseBase/$setupName"
      sha256 = $setupHash
      size_bytes = $setupSize
    }
  }
  notice = [ordered]@{
    title = if ($notice.title) { [string]$notice.title } else { "Insta360_HW $Version" }
    summary = if ($notice.summary) { [string]$notice.summary } else { "Insta360_HW $Version release" }
    highlights = $highlights
    compatibility = if ($notice.compatibility) { [string]$notice.compatibility } else { "Windows 10/11; OrCAD Capture 16.6 and 17.4" }
  }
}
$manifestPath = Join-Path $Workspace "update-manifest.json"
$manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Assert-ReleaseManifest -ReleaseRoot $ReleaseRoot -Path $manifestPath
$manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
$manifestSize = (Get-Item -LiteralPath $manifestPath).Length

Write-Host "Release artifacts prepared:" -ForegroundColor Cyan
Write-Host "  runtime: $ZipPath"
Write-Host "  setup:   $SetupPath"
Write-Host "  manifest:$manifestPath"
Write-Host "  runtime sha256: $runtimeHash"
if ($DryRun) { exit 0 }

if ([string]::IsNullOrWhiteSpace($Token)) { $Token = $env:GH_TOKEN }
if ([string]::IsNullOrWhiteSpace($Token)) { $Token = $env:GITHUB_TOKEN }
if ([string]::IsNullOrWhiteSpace($Token)) { throw "GH_TOKEN is required to publish a production release." }
$headers = @{
  Authorization = "Bearer $Token"
  Accept = "application/vnd.github+json"
  "X-GitHub-Api-Version" = "2022-11-28"
  "User-Agent" = "Insta360-HWAgent-Publisher"
}
$api = "https://api.github.com/repos/$Repo"
$release = Get-GitHubReleaseByTag -Api $api -ReleaseTag $Tag -Headers $headers
$tagRevision = Resolve-GitHubTagRevision -Api $api -ReleaseTag $Tag -Headers $headers
if (-not [string]::IsNullOrWhiteSpace($tagRevision) -and $tagRevision -cne $Revision) {
  throw "Existing tag $Tag does not point to current revision $Revision. Bump VERSION instead of replacing another build."
}
if ($null -ne $release -and -not [bool]$release.draft -and [string]::IsNullOrWhiteSpace($tagRevision)) {
  throw "Existing release $Tag has no resolvable git tag."
}
if ($null -ne $release -and [bool]$release.draft -and [string]$release.target_commitish -cne $Revision) {
  throw "Existing draft $Tag was created for a different revision."
}

if ($null -eq $release) {
  $body = @{
    tag_name = $Tag
    target_commitish = $Revision
    name = "Insta360 Hardware Productivity Platform $Tag"
    body = [string]$manifest.notice.summary
    draft = $true
    prerelease = $false
  } | ConvertTo-Json
  $release = Invoke-RestMethod -Uri "$api/releases" -Headers $headers -Method Post -Body $body `
    -ContentType "application/json; charset=utf-8"
}

$uploadId = $Revision.Substring(0, 12) + "-" + [guid]::NewGuid().ToString("N")
$stagedRuntime = Publish-StagedAsset -Release $release -Path $ZipPath -CanonicalName $runtimeName `
  -ContentType "application/zip" -ExpectedSize $runtimeSize -UploadId $uploadId -Api $api -Headers $headers
$stagedSetup = Publish-StagedAsset -Release $release -Path $SetupPath -CanonicalName $setupName `
  -ContentType "application/octet-stream" -ExpectedSize $setupSize -UploadId $uploadId -Api $api -Headers $headers
$stagedManifest = Publish-StagedAsset -Release $release -Path $manifestPath -CanonicalName "update-manifest.json" `
  -ContentType "application/json" -ExpectedSize $manifestSize -UploadId $uploadId -Api $api -Headers $headers

Promote-StagedAsset -Asset $stagedRuntime -CanonicalName $runtimeName -Release $release -Api $api -Headers $headers
Promote-StagedAsset -Asset $stagedSetup -CanonicalName $setupName -Release $release -Api $api -Headers $headers
Promote-StagedAsset -Asset $stagedManifest -CanonicalName "update-manifest.json" -Release $release -Api $api -Headers $headers

if ([bool]$release.draft) {
  $publishBody = @{
    tag_name = $Tag
    target_commitish = $Revision
    name = "Insta360 Hardware Productivity Platform $Tag"
    body = [string]$manifest.notice.summary
    draft = $false
    prerelease = $false
  } | ConvertTo-Json
  $release = Invoke-RestMethod -Uri "$api/releases/$($release.id)" -Headers $headers -Method Patch `
    -Body $publishBody -ContentType "application/json; charset=utf-8"
}

$publishedRevision = Resolve-GitHubTagRevision -Api $api -ReleaseTag $Tag -Headers $headers
if ($publishedRevision -cne $Revision) {
  throw "Published tag $Tag does not point to current revision $Revision."
}

Assert-PublicAsset -Url "$releaseBase/$runtimeName" -ExpectedSize $runtimeSize -RevisionToken $Revision
Assert-PublicAsset -Url "$releaseBase/$setupName" -ExpectedSize $setupSize -RevisionToken $Revision
$latestManifestUrl = "https://github.com/$Repo/releases/latest/download/update-manifest.json"
$downloadedManifest = Join-Path ([System.IO.Path]::GetTempPath()) ("insta360_hw_manifest_" + [guid]::NewGuid().ToString("N") + ".json")
try {
  Invoke-PublicVerificationWithRetry -Description "Latest release manifest verification" -Operation {
    param($attempt)
    $uri = $latestManifestUrl + "?verify=" + $Revision + "-" + $attempt
    Invoke-WebRequest -Uri $uri -OutFile $downloadedManifest -MaximumRedirection 8 -TimeoutSec 30 `
      -UseBasicParsing -Headers @{ "Cache-Control" = "no-cache" } | Out-Null
    $downloadedHash = (Get-FileHash -LiteralPath $downloadedManifest -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($downloadedHash -cne $manifestHash) {
      throw "expected manifest SHA256 $manifestHash but received $downloadedHash"
    }
    Assert-ReleaseManifest -ReleaseRoot $ReleaseRoot -Path $downloadedManifest
  }
} finally {
  Remove-Item -LiteralPath $downloadedManifest -Force -ErrorAction SilentlyContinue
}

Write-Host "Published and verified $Tag at $Revision" -ForegroundColor Green
