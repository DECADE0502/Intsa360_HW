$ErrorActionPreference = "Stop"

function Get-HwAgentText {
  param([Parameter(Mandatory=$true)][string]$Base64)
  return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Base64))
}

# Items preserved across an update: user data, outputs, history, local config
# and custom plugins. Kept as a single source of truth used by both the zip
# and git paths so neither can drift on what is protected.
$script:HwAgentProtected = @("data", "uploads", "outputs", "history", "config/local.json", "plugins/user")

# Dirs/files excluded when mirroring the freshly-fetched tree over the live
# install: the protected items above, plus dev-only and transient caches that
# must never land in an installed copy.
$script:HwAgentExcludeDirs = @(".git", "data", "uploads", "outputs", "history", "plugins\user", "frontend\node_modules", ".pytest_cache", "__pycache__")
$script:HwAgentExcludeFiles = @("local.json")


# ── ZIP-based update (primary, zero-dependency) ───────────────────────
# Downloads a source snapshot as a zip from GitHub (no git required on the
# user's machine), extracts it, then mirrors it over the install root while
# preserving protected items.
function Invoke-HwAgentZipUpdate {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [string]$Repo = "",
    [string]$Branch = "main"
  )
  Write-Host ((Get-HwAgentText "5pu05paw5pe25Lya5L+d55WZ77ya") + ($script:HwAgentProtected -join ", "))

  if ([string]::IsNullOrWhiteSpace($Repo)) {
    Write-Host (Get-HwAgentText "5LuT5bqT5Zyw5Z2A5Li656m677yM6Lez6L+HIFpJUCDmm7TmlrDjgII=")
    return @{ skipped = $true; reason = "empty_repo" }
  }

  # Normalize "owner/repo" or a full URL into owner/repo for codeload.
  $repoPath = $Repo
  if ($repoPath -match '^https?://github\.com/(.+?)(\.git)?/?$') { $repoPath = $Matches[1] }
  $zipUrl = "https://codeload.github.com/$repoPath/zip/refs/heads/$Branch"
  Write-Host ((Get-HwAgentText "5LiL6L29IFpJUCDmupDnoIHljIUuLi4g") + $zipUrl)

  $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("insta360_hw_update_" + [System.Guid]::NewGuid().ToString("N"))
  $zipPath = Join-Path $tempRoot "update.zip"
  $extractRoot = Join-Path $tempRoot "extracted"
  $cloneRoot = Join-Path $extractRoot "source"
  $backupRoot = Join-Path $tempRoot "protected"
  try {
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null

    # Download via .NET so no shell/Internet Explorer dependency is needed and
    # TLS 1.2 is negotiated for GitHub.
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
    $client = New-Object System.Net.WebClient
    $client.Headers.Add("User-Agent", "HWAgent-Updater")
    try {
      $client.DownloadFile($zipUrl, $zipPath)
    } finally {
      $client.Dispose()
    }
    if (-not (Test-Path -LiteralPath $zipPath)) { throw (Get-HwAgentText "WklQIOS4i+i9veWksei0pe+8jOivt+ajgOafpee9kee7nOi/nuaOpeWQjuWGjeivlQ==") }

    # Extract with the shell-less Expand-Archive, then locate the single
    # top-level folder GitHub wraps the archive in (owner-repo-branch).
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
    $top = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
    if (-not $top) { throw (Get-HwAgentText "6Kej5Y6L5ZCO55qEIFpJUCDnvLrlsJHpobblsYLnm67lvZU=") }
    Rename-Item -LiteralPath $top.FullName -NewName "source" -Force
    if (-not (Test-Path -LiteralPath $cloneRoot)) { throw (Get-HwAgentText "6Kej5Y6L5ZCO55qEIFpJUCDlhoXmnKrmib7liLDlubPlj7Dnm67lvZU=") }

    # Backup protected items, mirror, restore — same contract as the git path.
    foreach ($item in $script:HwAgentProtected) {
      $sourcePath = Join-Path $Root $item
      if (Test-Path -LiteralPath $sourcePath) {
        $backupPath = Join-Path $backupRoot $item
        $backupParent = Split-Path -Parent $backupPath
        if ($backupParent) { New-Item -ItemType Directory -Force -Path $backupParent | Out-Null }
        Copy-Item -LiteralPath $sourcePath -Destination $backupPath -Recurse -Force
      }
    }

    $args = @($cloneRoot, $Root, "/MIR", "/XD") + $script:HwAgentExcludeDirs + @("/XF") + $script:HwAgentExcludeFiles
    & robocopy @args | Out-Null
    if ($LASTEXITCODE -ge 8) {
      throw ((Get-HwAgentText "cm9ib2NvcHkg5aSx6LSl77yMZXhpdCBjb2RlOiA=") + $LASTEXITCODE)
    }

    foreach ($item in $script:HwAgentProtected) {
      $backupPath = Join-Path $backupRoot $item
      if (Test-Path -LiteralPath $backupPath) {
        $targetPath = Join-Path $Root $item
        $targetParent = Split-Path -Parent $targetPath
        if ($targetParent) { New-Item -ItemType Directory -Force -Path $targetParent | Out-Null }
        Copy-Item -LiteralPath $backupPath -Destination $targetPath -Recurse -Force
      }
    }
  } finally {
    if (Test-Path -LiteralPath $tempRoot) {
      Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
  Write-Host (Get-HwAgentText "WklQIOmVnOWDj+abtOaWsOWujOaIkO+8jOW8gOWni+mqjOivgeOAgg==")
  return @{ skipped = $false; branch = $Branch; method = "zip" }
}


# ── Git-based update (fallback when git is present) ───────────────────
function Invoke-HwAgentGitUpdate {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [string]$Repo = "",
    [string]$Branch = "main"
  )
  Write-Host ((Get-HwAgentText "5pu05paw5pe25Lya5L+d55WZ77ya") + ($script:HwAgentProtected -join ", "))

  if ([string]::IsNullOrWhiteSpace($Repo)) {
    Write-Host (Get-HwAgentText "5LuT5bqT5Zyw5Z2A5Li656m677yM6Lez6L+HIGdpdCDmm7TmlrDjgII=")
    return @{ skipped = $true; reason = "empty_repo" }
  }

  $git = Get-Command git.exe -ErrorAction SilentlyContinue
  if (-not $git) { throw (Get-HwAgentText "5pyq5om+5YiwIGdpdO+8jOaXoOazleabtOaWsOOAgg==") }

  Push-Location $Root
  try {
    if (Test-Path -LiteralPath (Join-Path $Root ".git")) {
      if (-not [string]::IsNullOrWhiteSpace($Repo)) {
        $remote = (& git remote get-url origin 2>$null)
        if ($LASTEXITCODE -ne 0) {
          & git remote add origin $Repo
          if ($LASTEXITCODE -ne 0) { throw "git remote add failed" }
        } elseif ($remote -ne $Repo) {
          & git remote set-url origin $Repo
          if ($LASTEXITCODE -ne 0) { throw "git remote set-url failed" }
        }
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

        foreach ($item in $script:HwAgentProtected) {
          $sourcePath = Join-Path $Root $item
          if (Test-Path -LiteralPath $sourcePath) {
            $backupPath = Join-Path $backupRoot $item
            $backupParent = Split-Path -Parent $backupPath
            if ($backupParent) { New-Item -ItemType Directory -Force -Path $backupParent | Out-Null }
            Copy-Item -LiteralPath $sourcePath -Destination $backupPath -Recurse -Force
          }
        }

        $args = @($cloneRoot, $Root, "/MIR", "/XD") + $script:HwAgentExcludeDirs + @("/XF") + $script:HwAgentExcludeFiles
        & robocopy @args | Out-Null
        if ($LASTEXITCODE -ge 8) {
          throw ("robocopy failed: " + $LASTEXITCODE)
        }

        foreach ($item in $script:HwAgentProtected) {
          $backupPath = Join-Path $backupRoot $item
          if (Test-Path -LiteralPath $backupPath) {
            $targetPath = Join-Path $Root $item
            $targetParent = Split-Path -Parent $targetPath
            if ($targetParent) { New-Item -ItemType Directory -Force -Path $targetParent | Out-Null }
            Copy-Item -LiteralPath $backupPath -Destination $targetPath -Recurse -Force
          }
        }
      } finally {
        if (Test-Path -LiteralPath $tempRoot) {
          Remove-Item -LiteralPath $tempRoot -Recurse -Force
        }
      }
    }
  } finally {
    Pop-Location
  }
  Write-Host (Get-HwAgentText "5pu05paw5a6M5oiQ77yM5byA5aeL6aqM6K+B44CC")
  return @{ skipped = $false; branch = $Branch }
}


# Decide the update path: zip by default (no git needed on user machines),
# git only when explicitly requested. Callers pass the chosen method.
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
