$ErrorActionPreference = "Stop"

function Get-HwAgentText {
  param([Parameter(Mandatory=$true)][string]$Base64)
  return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Base64))
}

$script:HwAgentProtected = @("data", "uploads", "outputs", "history", "config/local.json", "plugins/user")
$script:HwAgentExcludeDirs = @(".git", "data", "uploads", "outputs", "history", "plugins\user", "frontend\node_modules", ".pytest_cache", "__pycache__")
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
  $zipUrl = "https://codeload.github.com/$repoPath/zip/refs/heads/$Branch"
  Write-Host ("Downloading ZIP source: " + $zipUrl)
  Write-Host "__HWAGENT_PROGRESS__ 10 downloading update package"

  $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("insta360_hw_update_" + [System.Guid]::NewGuid().ToString("N"))
  $zipPath = Join-Path $tempRoot "update.zip"
  $extractRoot = Join-Path $tempRoot "extracted"
  $cloneRoot = Join-Path $extractRoot "source"
  $backupRoot = Join-Path $tempRoot "protected"

  try {
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
    $client = New-Object System.Net.WebClient
    $client.Headers.Add("User-Agent", "HWAgent-Updater")
    try {
      $client.DownloadFile($zipUrl, $zipPath)
    } finally {
      $client.Dispose()
    }
    if (-not (Test-Path -LiteralPath $zipPath)) { throw "ZIP download failed." }
    Write-Host "__HWAGENT_PROGRESS__ 30 update package downloaded"

    Write-Host "__HWAGENT_PROGRESS__ 40 extracting update package"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
    $top = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
    if (-not $top) { throw "Extracted ZIP has no top-level folder." }
    Rename-Item -LiteralPath $top.FullName -NewName "source" -Force
    if (-not (Test-Path -LiteralPath $cloneRoot)) { throw "Extracted ZIP does not contain platform root." }

    Write-Host "__HWAGENT_PROGRESS__ 55 backing up user data"
    Copy-HwAgentProtectedItems -Root $Root -BackupRoot $backupRoot

    Write-Host "__HWAGENT_PROGRESS__ 70 applying update files"
    Sync-HwAgentTree -SourceRoot $cloneRoot -TargetRoot $Root

    Write-Host "__HWAGENT_PROGRESS__ 85 restoring user data"
    Restore-HwAgentProtectedItems -Root $Root -BackupRoot $backupRoot
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
        New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
        & git clone --depth 1 --branch $Branch $Repo $cloneRoot
        if ($LASTEXITCODE -ne 0) { throw "git clone failed" }

        Copy-HwAgentProtectedItems -Root $Root -BackupRoot $backupRoot
        Sync-HwAgentTree -SourceRoot $cloneRoot -TargetRoot $Root
        Restore-HwAgentProtectedItems -Root $Root -BackupRoot $backupRoot
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
