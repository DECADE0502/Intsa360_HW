$ErrorActionPreference = "Stop"

function Read-HwAgentNotice {
  param([Parameter(Mandatory=$true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) {
    throw "UPDATE_NOTICE.json not found: $Path"
  }
  return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Write-HwAgentNotice {
  param(
    [Parameter(Mandatory=$true)][object]$Notice,
    [Parameter(Mandatory=$true)][string]$Path
  )
  $Notice | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function New-HwAgentReleaseZip {
  param(
    [Parameter(Mandatory=$true)][string]$ReleaseDir,
    [Parameter(Mandatory=$true)][string]$ZipPath
  )
  if (-not (Test-Path -LiteralPath $ReleaseDir)) { throw "Release tree missing: $ReleaseDir" }
  if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
  # Zip the directory itself, not its contents: every deployed
  # Find-HwAgentUpdatePayloadRoot locates the runtime by scanning top-level
  # directories of the extracted archive, so the wrapper must be present.
  Compress-Archive -Path $ReleaseDir -DestinationPath $ZipPath -Force
}

function Assert-HwAgentNoticeHasAssets {
  param([Parameter(Mandatory=$true)][string]$Path)
  $notice = Read-HwAgentNotice -Path $Path
  if (-not $notice.assets -or @($notice.assets).Count -eq 0) {
    throw "UPDATE_NOTICE.json.assets is empty: run publish_release.ps1 before tagging"
  }
  foreach ($asset in @($notice.assets)) {
    $sha256 = [string]$asset.sha256
    if ($sha256 -notmatch '^[a-f0-9]{64}$') {
      throw "asset missing valid sha256: $($asset.url)"
    }
    if (-not $asset.url) {
      throw "asset missing url"
    }
  }
}

function Update-HwAgentNoticeAssets {
  param(
    [Parameter(Mandatory=$true)][string]$NoticePath,
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][string]$TagName,
    [Parameter(Mandatory=$true)][string]$ZipPath
  )
  if (-not (Test-Path -LiteralPath $ZipPath)) {
    throw "release zip not found: $ZipPath"
  }
  $notice = Read-HwAgentNotice -Path $NoticePath
  $sha256 = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
  $sizeBytes = (Get-Item -LiteralPath $ZipPath).Length
  $fileName = [System.IO.Path]::GetFileName($ZipPath)
  $releaseUrl = "https://github.com/$($Repo)/releases/download/$($TagName)/$($fileName)"

  $notice.version = $Version
  $notice.assets = @(
    [pscustomobject]@{
      kind = "release_zip"
      url = $releaseUrl
      sha256 = $sha256
      size_bytes = $sizeBytes
    }
  )
  Write-HwAgentNotice -Notice $notice -Path $NoticePath
  return @{ sha256 = $sha256; size_bytes = $sizeBytes; url = $releaseUrl }
}
