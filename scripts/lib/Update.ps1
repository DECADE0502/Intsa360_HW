$ErrorActionPreference = "Stop"

function Get-HwAgentText {
  param([Parameter(Mandatory=$true)][string]$Base64)
  return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Base64))
}

function Invoke-HwAgentGitUpdate {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [string]$Repo = "",
    [string]$Branch = "main"
  )
  $protected = @("data", "uploads", "outputs", "history", "config/local.json")
  Write-Host ((Get-HwAgentText "5pu05paw5pe25Lya5L+d55WZ77ya") + ($protected -join ", "))

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

        foreach ($item in $protected) {
          $sourcePath = Join-Path $Root $item
          if (Test-Path -LiteralPath $sourcePath) {
            $backupPath = Join-Path $backupRoot $item
            $backupParent = Split-Path -Parent $backupPath
            if ($backupParent) { New-Item -ItemType Directory -Force -Path $backupParent | Out-Null }
            Copy-Item -LiteralPath $sourcePath -Destination $backupPath -Recurse -Force
          }
        }

        $excludeDirs = @(".git", "data", "uploads", "outputs", "history", "frontend\node_modules")
        $excludeFiles = @("local.json")
        $args = @($cloneRoot, $Root, "/MIR", "/XD") + $excludeDirs + @("/XF") + $excludeFiles
        & robocopy @args | Out-Null
        if ($LASTEXITCODE -ge 8) {
          throw ("robocopy failed: " + $LASTEXITCODE)
        }

        foreach ($item in $protected) {
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
