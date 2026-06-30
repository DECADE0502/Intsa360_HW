$ErrorActionPreference = "Stop"

function Get-HwAgentText {
  param([Parameter(Mandatory=$true)][string]$Base64)
  return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Base64))
}

$script:HwAgentProtected = @("data", "config/local.json", "plugins/user")
$script:HwAgentExcludeDirs = @(".git", "data", "plugins\user", "frontend", "tests", "docs", "frontend\node_modules", ".pytest_cache", "__pycache__")
$script:HwAgentExcludeFiles = @("local.json")

function Copy-HwAgentProtectedItems {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$BackupRoot
  )
  foreach ($item in $script:HwAgentProtected) {
    $sourcePath = Join-Path $Root $item
    if (Test-Path -LiteralPath $sourcePath) {
      $backupPath = Join-Path $BackupRoot $item
      $backupParent = Split-Path -Parent $backupPath
      if ($backupParent) { New-Item -ItemType Directory -Force -Path $backupParent | Out-Null }
      Copy-Item -LiteralPath $sourcePath -Destination $backupPath -Recurse -Force
    }
  }
}

function Restore-HwAgentProtectedItems {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$BackupRoot
  )
  foreach ($item in $script:HwAgentProtected) {
    $backupPath = Join-Path $BackupRoot $item
    if (Test-Path -LiteralPath $backupPath) {
      $targetPath = Join-Path $Root $item
      $targetParent = Split-Path -Parent $targetPath
      if ($targetParent) { New-Item -ItemType Directory -Force -Path $targetParent | Out-Null }
      Copy-Item -LiteralPath $backupPath -Destination $targetPath -Recurse -Force
    }
  }
}

function Sync-HwAgentTree {
  param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [Parameter(Mandatory=$true)][string]$TargetRoot
  )
  $args = @($SourceRoot, $TargetRoot, "/MIR", "/XD") + $script:HwAgentExcludeDirs + @("/XF") + $script:HwAgentExcludeFiles
  & robocopy @args | Out-Null
  if ($LASTEXITCODE -ge 8) {
    throw ("robocopy failed: " + $LASTEXITCODE)
  }
}

function ConvertTo-HwAgentRepoPath {
  param([Parameter(Mandatory=$true)][string]$Repo)
  $repoPath = $Repo
  if ($repoPath -match '^https?://github\.com/(.+?)(\.git)?/?$') {
    $repoPath = $Matches[1]
  }
  return $repoPath.Trim("/")
}

function Resolve-HwAgentReleaseAssetUrl {
  param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [string]$ExpectedRevision = ""
  )
  $repoPath = ConvertTo-HwAgentRepoPath -Repo $Repo
  $apiUrl = "https://api.github.com/repos/$repoPath/releases/latest"
  try {
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
    $headers = @{
      "User-Agent" = "HWAgent-Updater"
      "Accept" = "application/vnd.github+json"
    }
    $release = Invoke-RestMethod -Method Get -Uri $apiUrl -Headers $headers -TimeoutSec 15
    $releaseRevision = ""
    if ($release.target_commitish -match '^[0-9a-fA-F]{40}$') {
      $releaseRevision = [string]$release.target_commitish
    } elseif ($release.target_commitish) {
      $releaseRevision = Resolve-HwAgentRemoteRevision -Repo $Repo -Branch ([string]$release.target_commitish)
    }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedRevision) -and
        -not [string]::IsNullOrWhiteSpace($releaseRevision) -and
        $releaseRevision -ne $ExpectedRevision) {
      Write-Host ("Latest release package is behind main; falling back to source ZIP. release=" + $releaseRevision + " main=" + $ExpectedRevision)
      return $null
    }
    foreach ($asset in @($release.assets)) {
      $name = [string]$asset.name
      if ($name -match '^Insta360_HW_.*\.zip$' -or $name -match 'HWAgent.*\.zip$') {
        return [string]$asset.browser_download_url
      }
    }
  } catch {
    Write-Host ("Release lookup failed; falling back to source ZIP: " + $_.Exception.Message)
  }
  return $null
}

function Resolve-HwAgentRemoteRevision {
  param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [string]$Branch = "main"
  )
  $repoPath = ConvertTo-HwAgentRepoPath -Repo $Repo
  $apiUrl = "https://api.github.com/repos/$repoPath/commits/$Branch"
  try {
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
    $headers = @{
      "User-Agent" = "HWAgent-Updater"
      "Accept" = "application/vnd.github+json"
    }
    $commit = Invoke-RestMethod -Method Get -Uri $apiUrl -Headers $headers -TimeoutSec 15
    return [string]$commit.sha
  } catch {
    Write-Host ("Remote revision lookup failed: " + $_.Exception.Message)
    return ""
  }
}

function Write-HwAgentRevision {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [string]$Revision = ""
  )
  if (-not [string]::IsNullOrWhiteSpace($Revision)) {
    Set-Content -LiteralPath (Join-Path $Root "REVISION") -Value $Revision -Encoding UTF8
  }
}

function Find-HwAgentUpdatePayloadRoot {
  param([Parameter(Mandatory=$true)][string]$ExtractRoot)
  $candidates = @()
  $candidates += Get-ChildItem -LiteralPath $ExtractRoot -Directory -ErrorAction SilentlyContinue
  $candidates += Get-ChildItem -LiteralPath $ExtractRoot -Directory -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "HWAgent_release" }

  foreach ($candidate in $candidates) {
    $manifest = Join-Path $candidate.FullName "install_manifest.json"
    $frontend = Join-Path $candidate.FullName "app\frontend\index.html"
    if ((Test-Path -LiteralPath $manifest) -and (Test-Path -LiteralPath $frontend)) {
      return $candidate.FullName
    }
  }

  foreach ($candidate in $candidates) {
    $sourceRelease = Join-Path $candidate.FullName "HWAgent_release"
    if ((Test-Path -LiteralPath (Join-Path $sourceRelease "install_manifest.json")) -and
        (Test-Path -LiteralPath (Join-Path $sourceRelease "app\frontend\index.html"))) {
      return $sourceRelease
    }
  }

  foreach ($candidate in $candidates) {
    if ((Test-Path -LiteralPath (Join-Path $candidate.FullName "app\backend\suite_app.py")) -and
        (Test-Path -LiteralPath (Join-Path $candidate.FullName "app\frontend\index.html"))) {
      Write-Host "Using source ZIP payload; development-only paths will be excluded."
      return $candidate.FullName
    }
  }

  throw "Update package does not contain a usable HWAgent runtime payload."
}

function Download-HwAgentFile {
  param(
    [Parameter(Mandatory=$true)][string]$Url,
    [Parameter(Mandatory=$true)][string]$Target
  )
  $client = New-Object System.Net.WebClient
  $client.Headers.Add("User-Agent", "HWAgent-Updater")
  try {
    $client.DownloadFile($Url, $Target)
  } finally {
    $client.Dispose()
  }
}

function Invoke-HwAgentZipUpdate {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [string]$Repo = "",
    [string]$Branch = "main"
  )
  Write-Host ("Update will preserve: " + ($script:HwAgentProtected -join ", "))

  if ([string]::IsNullOrWhiteSpace($Repo)) {
    Write-Host "Repository is empty; skip ZIP update."
    return @{ skipped = $true; reason = "empty_repo" }
  }

  $repoPath = ConvertTo-HwAgentRepoPath -Repo $Repo
  $remoteRevision = Resolve-HwAgentRemoteRevision -Repo $Repo -Branch $Branch
  $assetUrl = Resolve-HwAgentReleaseAssetUrl -Repo $Repo -ExpectedRevision $remoteRevision
  if ($assetUrl) {
    $zipUrl = $assetUrl
    Write-Host ("Using runtime release package: " + $zipUrl)
  } else {
    $zipUrl = "https://codeload.github.com/$repoPath/zip/refs/heads/$Branch"
    Write-Host ("No runtime release asset found; falling back to source ZIP: " + $zipUrl)
  }
  Write-Host "__HWAGENT_PROGRESS__ 10 downloading update package"

  $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("insta360_hw_update_" + [System.Guid]::NewGuid().ToString("N"))
  $zipPath = Join-Path $tempRoot "update.zip"
  $extractRoot = Join-Path $tempRoot "extracted"
  $payloadRoot = $null
  $backupRoot = Join-Path $tempRoot "protected"

  try {
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
    Download-HwAgentFile -Url $zipUrl -Target $zipPath
    if (-not (Test-Path -LiteralPath $zipPath)) { throw "ZIP download failed." }
    Write-Host "__HWAGENT_PROGRESS__ 30 update package downloaded"

    Write-Host "__HWAGENT_PROGRESS__ 40 extracting update package"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
    $payloadRoot = Find-HwAgentUpdatePayloadRoot -ExtractRoot $extractRoot

    Write-Host "__HWAGENT_PROGRESS__ 55 backing up user data"
    Copy-HwAgentProtectedItems -Root $Root -BackupRoot $backupRoot

    Write-Host "__HWAGENT_PROGRESS__ 70 applying update files"
    Sync-HwAgentTree -SourceRoot $payloadRoot -TargetRoot $Root

    Write-Host "__HWAGENT_PROGRESS__ 85 restoring user data"
    Restore-HwAgentProtectedItems -Root $Root -BackupRoot $backupRoot
    Write-HwAgentRevision -Root $Root -Revision $remoteRevision
  } finally {
    if (Test-Path -LiteralPath $tempRoot) {
      Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
  }

  Write-Host "__HWAGENT_PROGRESS__ 95 finishing update"
  Write-Host "ZIP update complete; starting verification."
  return @{ skipped = $false; branch = $Branch; method = "zip" }
}

function Invoke-HwAgentGitUpdate {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [string]$Repo = "",
    [string]$Branch = "main"
  )
  Write-Host ("Update will preserve: " + ($script:HwAgentProtected -join ", "))

  if ([string]::IsNullOrWhiteSpace($Repo)) {
    Write-Host "Repository is empty; skip git update."
    return @{ skipped = $true; reason = "empty_repo" }
  }

  $git = Get-Command git.exe -ErrorAction SilentlyContinue
  if (-not $git) { throw "git.exe was not found; cannot use git update." }

  Push-Location $Root
  try {
    if (Test-Path -LiteralPath (Join-Path $Root ".git")) {
      $remote = (& git remote get-url origin 2>$null)
      if ($LASTEXITCODE -ne 0) {
        & git remote add origin $Repo
        if ($LASTEXITCODE -ne 0) { throw "git remote add failed" }
      } elseif ($remote -ne $Repo) {
        & git remote set-url origin $Repo
        if ($LASTEXITCODE -ne 0) { throw "git remote set-url failed" }
      }
      & git pull --ff-only
      if ($LASTEXITCODE -ne 0) { throw "git pull failed" }
    } else {
      $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("insta360_hw_update_" + [System.Guid]::NewGuid().ToString("N"))
      $cloneRoot = Join-Path $tempRoot "repo"
      $backupRoot = Join-Path $tempRoot "protected"
      try {
        $remoteRevision = Resolve-HwAgentRemoteRevision -Repo $Repo -Branch $Branch
        New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
        & git clone --depth 1 --branch $Branch $Repo $cloneRoot
        if ($LASTEXITCODE -ne 0) { throw "git clone failed" }

        Copy-HwAgentProtectedItems -Root $Root -BackupRoot $backupRoot
        Sync-HwAgentTree -SourceRoot $cloneRoot -TargetRoot $Root
        Restore-HwAgentProtectedItems -Root $Root -BackupRoot $backupRoot
        Write-HwAgentRevision -Root $Root -Revision $remoteRevision
      } finally {
        if (Test-Path -LiteralPath $tempRoot) {
          Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
      }
    }
  } finally {
    Pop-Location
  }
  Write-Host "git update complete; starting verification."
  return @{ skipped = $false; branch = $Branch; method = "git" }
}

function Invoke-HwAgentUpdate {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [string]$Repo = "",
    [string]$Branch = "main",
    [ValidateSet("zip", "git")]
    [string]$Method = "zip"
  )
  if ($Method -eq "git") {
    return Invoke-HwAgentGitUpdate -Root $Root -Repo $Repo -Branch $Branch
  }
  return Invoke-HwAgentZipUpdate -Root $Root -Repo $Repo -Branch $Branch
}
