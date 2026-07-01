$ErrorActionPreference = "Stop"

function Get-HwAgentText {
  param([Parameter(Mandatory=$true)][string]$Base64)
  return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Base64))
}

$script:HwAgentProtected = @("data", "config/local.json", "plugins/user", "unins000.exe", "unins000.dat", "unins000.msg")
$script:HwAgentInstallerOwned = @("unins000.exe", "unins000.dat", "unins000.msg")
$script:HwAgentExcludeDirs = @(".git", "data", "plugins\user", "tests", "docs", "launcher", "BOM*", "node_modules", ".pytest_cache", "__pycache__")
$script:HwAgentExcludeFiles = @("local.json", ".gitignore", "HWAgent_Setup.iss", "Insta360_HW_Setup.exe")
$script:HwAgentSourceOnlyRootDirs = @("frontend", "tests", "docs", "launcher")
$script:HwAgentSourceOnlyRootFiles = @(".gitignore", "HWAgent_Setup.iss", "Insta360_HW_Setup.exe")

function Get-HwAgentUpdateStateDir {
  param([Parameter(Mandatory=$true)][string]$Root)
  return (Join-Path $Root "data\reports\runtime")
}

function Get-HwAgentUpdatePendingPath {
  param([Parameter(Mandatory=$true)][string]$Root)
  return (Join-Path (Get-HwAgentUpdateStateDir -Root $Root) "update_pending.json")
}

function New-HwAgentRollbackRoot {
  param([Parameter(Mandatory=$true)][string]$Root)
  return (Join-Path (Get-HwAgentUpdateStateDir -Root $Root) "update_rollback_current")
}

function Start-HwAgentUpdateTransaction {
  param([Parameter(Mandatory=$true)][string]$Root)
  $stateDir = Get-HwAgentUpdateStateDir -Root $Root
  New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
  $rollbackRoot = New-HwAgentRollbackRoot -Root $Root
  if (Test-Path -LiteralPath $rollbackRoot) {
    Remove-Item -LiteralPath $rollbackRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
  Copy-HwAgentTreeForRollback -Root $Root -BackupRoot $rollbackRoot
  $pending = @{
    started_at = (Get-Date).ToString("o")
    root = $Root
    rollback_root = $rollbackRoot
  }
  $pending | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Get-HwAgentUpdatePendingPath -Root $Root) -Encoding UTF8
  return $rollbackRoot
}

function Complete-HwAgentUpdateTransaction {
  param([Parameter(Mandatory=$true)][string]$Root)
  $pendingPath = Get-HwAgentUpdatePendingPath -Root $Root
  $rollbackRoot = New-HwAgentRollbackRoot -Root $Root
  if (Test-Path -LiteralPath $pendingPath) {
    Remove-Item -LiteralPath $pendingPath -Force -ErrorAction SilentlyContinue
  }
  if (Test-Path -LiteralPath $rollbackRoot) {
    Remove-Item -LiteralPath $rollbackRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
}

function Restore-HwAgentInterruptedUpdate {
  param([Parameter(Mandatory=$true)][string]$Root)
  $pendingPath = Get-HwAgentUpdatePendingPath -Root $Root
  if (-not (Test-Path -LiteralPath $pendingPath)) { return $false }

  $rollbackRoot = New-HwAgentRollbackRoot -Root $Root
  try {
    $pending = Get-Content -LiteralPath $pendingPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($pending.rollback_root) {
      $rollbackRoot = [string]$pending.rollback_root
    }
  } catch {
    $rollbackRoot = New-HwAgentRollbackRoot -Root $Root
  }

  Write-Host "__HWAGENT_PROGRESS__ 5 restoring interrupted update"
  if (Test-Path -LiteralPath $rollbackRoot) {
    Restore-HwAgentTreeFromRollback -BackupRoot $rollbackRoot -Root $Root
  }
  Complete-HwAgentUpdateTransaction -Root $Root
  Write-Host "Recovered from an interrupted update by restoring previous runtime files."
  return $true
}

function Stop-HwAgentLauncherProcesses {
  param([Parameter(Mandatory=$true)][string]$Root)
  $exePath = Join-Path $Root "Insta360_HW.exe"
  if (-not (Test-Path -LiteralPath $exePath)) { return @() }
  $resolvedExe = (Resolve-Path -LiteralPath $exePath).Path
  $stopped = @()
  try {
    Get-CimInstance Win32_Process |
      Where-Object { $_.Name -ieq "Insta360_HW.exe" -and $_.ExecutablePath -and $_.ExecutablePath -ieq $resolvedExe } |
      ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        $stopped += [string]$_.ProcessId
      }
  } catch {
    return $stopped
  }
  return $stopped
}

function Stop-HwAgentRuntimeLocks {
  param([Parameter(Mandatory=$true)][string]$Root)
  Stop-HwAgentLauncherProcesses -Root $Root | Out-Null
  if (Get-Command Stop-HwAgentServicesByPort -ErrorAction SilentlyContinue) {
    Stop-HwAgentServicesByPort | Out-Null
  }
}

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
  $installerBackupRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("insta360_hw_installer_owned_" + [System.Guid]::NewGuid().ToString("N"))
  try {
    foreach ($item in $script:HwAgentInstallerOwned) {
      $sourcePath = Join-Path $TargetRoot $item
      if (Test-Path -LiteralPath $sourcePath) {
        New-Item -ItemType Directory -Force -Path $installerBackupRoot | Out-Null
        Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $installerBackupRoot $item) -Force
      }
    }

    Stop-HwAgentRuntimeLocks -Root $TargetRoot

    $args = @($SourceRoot, $TargetRoot, "/MIR", "/R:2", "/W:1", "/XD") + $script:HwAgentExcludeDirs + @("/XF") + $script:HwAgentExcludeFiles
    & robocopy @args | Out-Null
    if ($LASTEXITCODE -ge 8) {
      throw ("robocopy failed: " + $LASTEXITCODE)
    }

    foreach ($item in $script:HwAgentInstallerOwned) {
      $backupPath = Join-Path $installerBackupRoot $item
      if (Test-Path -LiteralPath $backupPath) {
        Copy-Item -LiteralPath $backupPath -Destination (Join-Path $TargetRoot $item) -Force
      }
    }

    foreach ($dir in $script:HwAgentSourceOnlyRootDirs) {
      $path = Join-Path $TargetRoot $dir
      if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
      }
    }
    foreach ($file in $script:HwAgentSourceOnlyRootFiles) {
      $path = Join-Path $TargetRoot $file
      if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
      }
    }
  } finally {
    if (Test-Path -LiteralPath $installerBackupRoot) {
      Remove-Item -LiteralPath $installerBackupRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

function Copy-HwAgentTreeForRollback {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$BackupRoot
  )
  New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
  $args = @($Root, $BackupRoot, "/MIR", "/R:2", "/W:1", "/XD", "data", "plugins\user", ".git", "node_modules", "/XF", "config\local.json")
  & robocopy @args | Out-Null
  if ($LASTEXITCODE -ge 8) {
    throw ("rollback backup failed: " + $LASTEXITCODE)
  }
}

function Restore-HwAgentTreeFromRollback {
  param(
    [Parameter(Mandatory=$true)][string]$BackupRoot,
    [Parameter(Mandatory=$true)][string]$Root
  )
  if (-not (Test-Path -LiteralPath $BackupRoot)) { return }
  $args = @($BackupRoot, $Root, "/MIR", "/R:2", "/W:1", "/XD", "data", "plugins\user", ".git", "node_modules", "/XF", "config\local.json")
  & robocopy @args | Out-Null
  if ($LASTEXITCODE -ge 8) {
    throw ("rollback restore failed: " + $LASTEXITCODE)
  }
}

function Invoke-HwAgentWithRollback {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][scriptblock]$Operation
  )
  $rollbackRoot = $null
  try {
    Restore-HwAgentInterruptedUpdate -Root $Root | Out-Null
    $rollbackRoot = Start-HwAgentUpdateTransaction -Root $Root
    & $Operation
    Complete-HwAgentUpdateTransaction -Root $Root
  } catch {
    Write-Host "__HWAGENT_PROGRESS__ 90 rolling back failed update"
    try {
      if ($rollbackRoot -and (Test-Path -LiteralPath $rollbackRoot)) {
        Restore-HwAgentTreeFromRollback -BackupRoot $rollbackRoot -Root $Root
      }
      Complete-HwAgentUpdateTransaction -Root $Root
      Write-Host "Update failed; restored previous runtime files."
    } catch {
      Write-Host ("Rollback failed: " + $_.Exception.Message)
    }
    throw
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
        $sha256 = ""
        if ($asset.sha256) { $sha256 = [string]$asset.sha256 }
        elseif ($asset.digest -and ([string]$asset.digest) -match '^sha256:(.+)$') { $sha256 = $Matches[1] }
        return @{
          Url = [string]$asset.browser_download_url
          Sha256 = $sha256
          Size = [int64]$asset.size
        }
      }
    }
  } catch {
    Write-Host ("Release lookup failed; falling back to source ZIP: " + $_.Exception.Message)
  }
  return $null
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

function Assert-HwAgentFileHash {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [string]$ExpectedSha256 = ""
  )
  if ([string]::IsNullOrWhiteSpace($ExpectedSha256)) { return }
  if (-not (Test-Path -LiteralPath $Path)) { throw "Downloaded file is missing." }

  $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
  $expected = $ExpectedSha256.Trim().ToLowerInvariant()
  if ($actual -ne $expected) {
    Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    throw ("SHA256 mismatch for update package. expected=" + $expected + " actual=" + $actual)
  }
}

function Download-HwAgentFile {
  param(
    [Parameter(Mandatory=$true)][string]$Url,
    [Parameter(Mandatory=$true)][string]$Target,
    [string]$ExpectedSha256 = ""
  )
  $client = New-Object System.Net.WebClient
  $client.Headers.Add("User-Agent", "HWAgent-Updater")
  try {
    $client.DownloadFile($Url, $Target)
  } finally {
    $client.Dispose()
  }
  Assert-HwAgentFileHash -Path $Target -ExpectedSha256 $ExpectedSha256
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
  $asset = Resolve-HwAgentReleaseAssetUrl -Repo $Repo -ExpectedRevision $remoteRevision
  $expectedSha256 = ""
  if ($asset) {
    $zipUrl = [string]$asset.Url
    $expectedSha256 = [string]$asset.Sha256
    Write-Host ("Using runtime release package: " + $zipUrl)
    if ([string]::IsNullOrWhiteSpace($expectedSha256)) {
      Write-Host "Runtime release package has no SHA256 metadata; download will not be integrity-checked."
    }
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
    Download-HwAgentFile -Url $zipUrl -Target $zipPath -ExpectedSha256 $expectedSha256
    if (-not (Test-Path -LiteralPath $zipPath)) { throw "ZIP download failed." }
    Write-Host "__HWAGENT_PROGRESS__ 30 update package downloaded"

    Write-Host "__HWAGENT_PROGRESS__ 40 extracting update package"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
    $payloadRoot = Find-HwAgentUpdatePayloadRoot -ExtractRoot $extractRoot

    Invoke-HwAgentWithRollback -Root $Root -Operation {
      Write-Host "__HWAGENT_PROGRESS__ 55 backing up user data"
      Copy-HwAgentProtectedItems -Root $Root -BackupRoot $backupRoot

      Write-Host "__HWAGENT_PROGRESS__ 70 applying update files"
      Sync-HwAgentTree -SourceRoot $payloadRoot -TargetRoot $Root

      Write-Host "__HWAGENT_PROGRESS__ 85 restoring user data"
      Restore-HwAgentProtectedItems -Root $Root -BackupRoot $backupRoot
      Write-HwAgentRevision -Root $Root -Revision $remoteRevision
    }
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

        Invoke-HwAgentWithRollback -Root $Root -Operation {
          Copy-HwAgentProtectedItems -Root $Root -BackupRoot $backupRoot
          Sync-HwAgentTree -SourceRoot $cloneRoot -TargetRoot $Root
          Restore-HwAgentProtectedItems -Root $Root -BackupRoot $backupRoot
          Write-HwAgentRevision -Root $Root -Revision $remoteRevision
        }
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
