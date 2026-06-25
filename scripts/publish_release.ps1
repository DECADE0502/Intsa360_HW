param(
  # GitHub personal access token with repo scope. Required to create the
  # release + upload the asset. Pass via -Token or set env GH_TOKEN.
  [string]$Token = "",
  # Repo in owner/name form (must match update.ps1 default for the in-platform
  # updater to find the VERSION it compares against).
  [string]$Repo = "DECADE0502/Intsa360_HW",
  # Tag / version to publish. Defaults to the VERSION file content.
  [string]$Tag = ""
)

$ErrorActionPreference = "Stop"

# resolve project root: scripts\ -> root, then up one to the workspace.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$Workspace = Split-Path -Parent $Root

# 1. Determine version / tag.
if (-not $Tag) {
  $versionFile = Join-Path $Root "VERSION"
  $Tag = (Get-Content -LiteralPath $versionFile -Raw).Trim()
}
if (-not $Tag) { throw "VERSION is empty and no -Tag given." }
$tagName = if ($Tag.StartsWith("v")) { $Tag } else { "v$Tag" }
Write-Host "Publishing release $tagName for $Repo" -ForegroundColor Cyan

# 2. Ensure the release tree is built (exe + frontend + runtime), then pack it
#    into a zip. This zip is what end-user "一键更新" downloads.
& (Join-Path $Root "scripts\build_release.ps1")
$Release = Join-Path $Workspace "HWAgent_release"
if (-not (Test-Path -LiteralPath $Release)) { throw "Release tree missing: $Release" }

$ZipPath = Join-Path $Workspace ("Insta360_HW_$tagName.zip")
if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
Compress-Archive -Path (Join-Path $Release "*") -DestinationPath $ZipPath -Force
$zipSize = (Get-Item -LiteralPath $ZipPath).Length
Write-Host ("Packed release zip: {0} ({1:N1} MB)" -f $ZipPath, ($zipSize / 1MB))

# 3. GitHub token resolution.
if (-not $Token) { $Token = $env:GH_TOKEN }
if (-not $Token) { $Token = $env:GITHUB_TOKEN }
if (-not $Token) {
  Write-Host ""
  Write-Host "No GitHub token (-Token / GH_TOKEN / GITHUB_TOKEN)." -ForegroundColor Yellow
  Write-Host "The zip is ready at: $ZipPath" -ForegroundColor Green
  Write-Host "Create the release manually, or re-run with a token to publish automatically."
  exit 0
}

# 4. Create the release via the GitHub REST API.
$apiBase = "https://api.github.com/repos/$Repo"
$headers = @{
  Authorization = "Bearer $Token"
  Accept        = "application/vnd.github+json"
  "X-GitHub-Api-Version" = "2022-11-28"
  "User-Agent"  = "HWAgent-Publisher"
}

Write-Host "Creating release $tagName..."
$createBody = @{
  tag_name = $tagName
  name     = "Insta360 HWAgent $tagName"
  body     = "硬件提效平台 $tagName 自动发布。安装或更新后，平台内「一键更新」将拉取此版本。"
  draft    = $false
} | ConvertTo-Json

$release = Invoke-RestMethod -Method Post -Uri "$apiBase/releases" -Headers $headers -Body $createBody -ContentType "application/json; charset=utf-8"
Write-Host ("Created release id {0}" -f $release.id) -ForegroundColor Green

# 5. Upload the zip as a release asset.
$uploadUrl = $release.upload_url -replace '\{\?name,label\}', ''
$assetUri = $uploadUrl + "?name=$([uri]::EscapeDataString([System.IO.Path]::GetFileName($ZipPath)))"
Write-Host "Uploading asset..."
$bytes = [System.IO.File]::ReadAllBytes($ZipPath)
Invoke-RestMethod -Method Post -Uri $assetUri -Headers $headers -Body $bytes -ContentType "application/zip" | Out-Null
Write-Host ("Uploaded {0}" -f [System.IO.Path]::GetFileName($ZipPath)) -ForegroundColor Green

Write-Host ""
Write-Host "Published $tagName -> $($release.html_url)" -ForegroundColor Cyan
