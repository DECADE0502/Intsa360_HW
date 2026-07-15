param(
  [string]$BundleDir = "",
  [string]$Token = "",
  [string]$Repo = "DECADE0502/Intsa360_HW",
  [switch]$DryRun,
  [int]$TimeoutMinutes = 20
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$Workspace = Split-Path -Parent $Root
$Version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw -Encoding UTF8).Trim()
$Revision = (& git -C $Root rev-parse HEAD).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $Revision -notmatch '^[a-f0-9]{40}$') { throw "A full git revision is required." }
if ([string]::IsNullOrWhiteSpace($BundleDir)) { $BundleDir = Join-Path $Workspace ("Insta360_HW_release_" + $Version) }
$BundleDir = [System.IO.Path]::GetFullPath($BundleDir)
$ReleaseTool = Join-Path $Root "scripts\release\release_bundle.py"
$PublicKey = Join-Path $Root "config\update_public_key.pem"
$Tag = "v$Version"
$validation_id = [guid]::NewGuid().ToString("N")

$dirty = @(& git -C $Root status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0) { throw "Unable to verify the git worktree." }
if ($dirty.Count -gt 0) { throw "Publishing requires a clean git worktree." }
& python $ReleaseTool verify --bundle-dir $BundleDir --public-key $PublicKey --version $Version --revision $Revision
if ($LASTEXITCODE -ne 0) { throw "Local release bundle verification failed." }
if ($DryRun) {
  Write-Host "Dry run passed. The exact local bundle is publishable: $BundleDir" -ForegroundColor Green
  exit 0
}

if ([string]::IsNullOrWhiteSpace($Token)) { $Token = $env:GH_TOKEN }
if ([string]::IsNullOrWhiteSpace($Token)) { $Token = $env:GITHUB_TOKEN }
if ([string]::IsNullOrWhiteSpace($Token)) { throw "GH_TOKEN is required to upload the local release bundle." }
$Headers = @{
  Authorization = "Bearer $Token"
  Accept = "application/vnd.github+json"
  "X-GitHub-Api-Version" = "2022-11-28"
  "User-Agent" = "Insta360-HWAgent-LocalPublisher"
}
$Api = "https://api.github.com/repos/$Repo"

function Get-HttpStatusCode {
  param($ErrorRecord)
  try { return [int]$ErrorRecord.Exception.Response.StatusCode } catch { return 0 }
}

function Get-ReleaseByTag {
  try {
    return Invoke-RestMethod -Uri ("$Api/releases/tags/" + [uri]::EscapeDataString($Tag)) -Headers $Headers
  } catch {
    if ((Get-HttpStatusCode $_) -ne 404) { throw }
  }
  for ($page = 1; $page -le 10; $page++) {
    $items = @(Invoke-RestMethod -Uri "$Api/releases?per_page=100&page=$page" -Headers $Headers)
    foreach ($item in $items) {
      if ([string]$item.tag_name -ceq $Tag) { return $item }
    }
    if ($items.Count -lt 100) { break }
  }
  return $null
}

$RepositoryInfo = Invoke-RestMethod -Uri $Api -Headers $Headers
$DefaultBranch = [string]$RepositoryInfo.default_branch
if ([string]::IsNullOrWhiteSpace($DefaultBranch)) { throw "GitHub did not report a default branch." }
try { $DefaultHead = Invoke-RestMethod -Uri "$Api/commits/$DefaultBranch" -Headers $Headers }
catch { throw "Unable to resolve GitHub default branch $DefaultBranch." }
if (([string]$DefaultHead.sha).ToLowerInvariant() -cne $Revision) {
  throw "Release revision must be the current GitHub $DefaultBranch head. Push or merge it before publishing."
}
$Release = Get-ReleaseByTag
if ($Release -and -not [bool]$Release.draft) {
  throw "Release $Tag is already public and immutable. Bump VERSION for another release."
}
if ($Release -and [string]$Release.target_commitish -cne $Revision) {
  throw "Existing draft $Tag belongs to another revision. Delete it or bump VERSION."
}
$manifest = Get-Content -LiteralPath (Join-Path $BundleDir "update-manifest-v3.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$summary = if (@($manifest.changelog).Count -gt 0) { [string]$manifest.changelog[0] } else { "Insta360_HW $Version" }
if (-not $Release) {
  $body = @{
    tag_name = $Tag
    target_commitish = $Revision
    name = "Insta360 Hardware Productivity Platform $Tag"
    body = $summary
    draft = $true
    prerelease = $false
  } | ConvertTo-Json
  $Release = Invoke-RestMethod -Uri "$Api/releases" -Headers $Headers -Method Post -Body $body -ContentType "application/json; charset=utf-8"
}

$ExpectedNames = @(
  "Insta360_HW_Runtime_$Version.zip",
  "Insta360_HW_runtime_v$Version.zip",
  "Insta360_HW_Setup.exe",
  "update-manifest-v3.json",
  "update-manifest.json",
  "SHA256SUMS.txt"
)
foreach ($asset in @($Release.assets)) {
  Invoke-RestMethod -Uri "$Api/releases/assets/$($asset.id)" -Headers $Headers -Method Delete | Out-Null
}
$uploadBase = ([string]$Release.upload_url) -replace '\{\?name,label\}', ''
for ($index = 0; $index -lt $ExpectedNames.Count; $index++) {
  $name = $ExpectedNames[$index]
  $path = Join-Path $BundleDir $name
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Release asset is missing: $path" }
  $percent = [int](($index / $ExpectedNames.Count) * 100)
  Write-Progress -Activity "Uploading verified release assets" -Status $name -PercentComplete $percent
  $uri = $uploadBase + "?name=" + [uri]::EscapeDataString($name)
  $contentType = if ($name.EndsWith(".zip")) { "application/zip" } elseif ($name.EndsWith(".json")) { "application/json" } else { "application/octet-stream" }
  $uploaded = Invoke-RestMethod -Uri $uri -Headers $Headers -Method Post -InFile $path -ContentType $contentType
  if ([long]$uploaded.size -ne (Get-Item -LiteralPath $path).Length) { throw "GitHub reported a wrong size for $name." }
}
Write-Progress -Activity "Uploading verified release assets" -Completed

$dispatch = @{
  ref = $DefaultBranch
  inputs = @{
    tag = $Tag
    revision = $Revision
    validation_id = $validation_id
    release_id = [string]$Release.id
  }
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri "$Api/actions/workflows/release.yml/dispatches" -Headers $Headers -Method Post `
  -Body $dispatch -ContentType "application/json; charset=utf-8" | Out-Null

$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
$Run = $null
do {
  Start-Sleep -Seconds 3
  $runs = Invoke-RestMethod -Uri "$Api/actions/workflows/release.yml/runs?event=workflow_dispatch&per_page=30" -Headers $Headers
  $Run = @($runs.workflow_runs) | Where-Object { ([string]$_.display_title).Contains($validation_id) } | Select-Object -First 1
} while (-not $Run -and (Get-Date) -lt $deadline)
if (-not $Run) { throw "GitHub validation run did not start. Draft $Tag was left unpublished." }

do {
  $Run = Invoke-RestMethod -Uri "$Api/actions/runs/$($Run.id)" -Headers $Headers
  $elapsed = [Math]::Max(0, [int](((Get-Date) - [datetime]$Run.created_at).TotalSeconds))
  Write-Progress -Activity "GitHub is validating the uploaded bytes" -Status ([string]$Run.status) `
    -PercentComplete ([Math]::Min(95, 5 + $elapsed))
  if ([string]$Run.status -eq "completed") { break }
  Start-Sleep -Seconds 5
} while ((Get-Date) -lt $deadline)
Write-Progress -Activity "GitHub is validating the uploaded bytes" -Completed
if ([string]$Run.status -ne "completed") { throw "GitHub validation timed out. Draft $Tag was left unpublished." }
if ([string]$Run.conclusion -ne "success") { throw "GitHub validation failed. Draft $Tag was left unpublished: $($Run.html_url)" }

$Release = Get-ReleaseByTag
if (-not $Release -or [bool]$Release.draft) { throw "Validation passed but GitHub did not publish $Tag." }
Write-Host "Published the exact locally built and remotely validated release: $($Release.html_url)" -ForegroundColor Green
