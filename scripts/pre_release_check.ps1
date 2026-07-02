$ErrorActionPreference = "Continue"  # We collect all errors, don't die on first

$root = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $root
$errors = @()

function Add-Error { param([string]$msg) $script:errors += $msg }

Write-Host "Pre-release check starting at $root" -ForegroundColor Cyan

# 1. git status clean
$status = (& git -C $root status --porcelain 2>&1) -join "`n"
if ($status.Trim()) {
    Add-Error "Uncommitted changes present:`n$status"
} else {
    Write-Host "[OK] git status clean" -ForegroundColor Green
}

# 2. VERSION consistency with iss/notice
$version = (Get-Content -Raw (Join-Path $root "VERSION")).Trim()
$issContent = Get-Content -Raw (Join-Path $root "HWAgent_Setup.iss")
$issPattern = '#define MyAppVersion "' + $version + '"'
if ($issContent -notmatch [regex]::Escape($issPattern)) {
    Add-Error "HWAgent_Setup.iss MyAppVersion does not match VERSION ($version)"
} else {
    Write-Host "[OK] iss version matches VERSION ($version)" -ForegroundColor Green
}

# 3. Source REVISION matches UPDATE_NOTICE; release REVISION is checked against HEAD after build.
$revision = (Get-Content -Raw (Join-Path $root "REVISION")).Trim()
$notice = Get-Content -Raw (Join-Path $root "UPDATE_NOTICE.json") | ConvertFrom-Json
if ([string]$notice.revision -ne $revision) {
    Add-Error "UPDATE_NOTICE.revision ($($notice.revision)) does not match REVISION ($revision). Run scripts\bump_version.ps1 to sync."
} else {
    Write-Host "[OK] REVISION matches UPDATE_NOTICE.revision" -ForegroundColor Green
}

# 4. UPDATE_NOTICE.assets non-empty with sha256
. (Join-Path $root "scripts\lib\ReleaseNotice.ps1")
try {
    Assert-HwAgentNoticeHasAssets -Path (Join-Path $root "UPDATE_NOTICE.json")
    Write-Host "[OK] UPDATE_NOTICE.json has valid assets with sha256" -ForegroundColor Green
} catch {
    Add-Error "UPDATE_NOTICE.json: $($_.Exception.Message)"
}

# 5. HWAgent_release/Insta360_HW.exe exists and mtime > VERSION mtime
$releaseExe = Join-Path $repoRoot "HWAgent_release\Insta360_HW.exe"
if (-not (Test-Path $releaseExe)) {
    Add-Error "HWAgent_release\Insta360_HW.exe not built. Run scripts\build_release.ps1 first."
} else {
    $head = (& git -C $root rev-parse HEAD 2>&1).Trim()
    $releaseRevisionPath = Join-Path $repoRoot "HWAgent_release\REVISION"
    $releaseRevision = if (Test-Path $releaseRevisionPath) { (Get-Content -Raw $releaseRevisionPath).Trim() } else { "" }
    $releaseIsAncestor = $false
    if ($releaseRevision -match '^[0-9a-fA-F]{40}$') {
        & git -C $root merge-base --is-ancestor $releaseRevision $head 2>$null
        $releaseIsAncestor = ($LASTEXITCODE -eq 0)
    }
    if (-not $releaseIsAncestor) {
        Add-Error "HWAgent_release\REVISION ($releaseRevision) is not an ancestor of git HEAD ($head). Rebuild release from this branch."
    } else {
        Write-Host "[OK] HWAgent_release REVISION is on current branch" -ForegroundColor Green
    }
    $exeMtime = (Get-Item $releaseExe).LastWriteTime
    $versionMtime = (Get-Item (Join-Path $root "VERSION")).LastWriteTime
    if ($exeMtime -lt $versionMtime) {
        Add-Error "Insta360_HW.exe ($($exeMtime)) is older than VERSION ($($versionMtime)) — rebuild required"
    } else {
        Write-Host "[OK] Insta360_HW.exe built after VERSION" -ForegroundColor Green
    }
}

# 6. pytest fast tests pass
Write-Host "Running fast pytest (may take up to 2 minutes)..." -ForegroundColor Cyan
$pytestOut = & python -m pytest -m "not slow and not network" --tb=line -q 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Add-Error "pytest fast tests failing:`n$($pytestOut -split "`n" | Select-Object -Last 15 | Out-String)"
} else {
    Write-Host "[OK] pytest fast tests pass" -ForegroundColor Green
}

# 7. frontend build passes
Write-Host "Running npm run build..." -ForegroundColor Cyan
Push-Location (Join-Path $root "frontend")
try {
    $npmLog = Join-Path ([System.IO.Path]::GetTempPath()) ("hwagent_npm_build_" + [System.Guid]::NewGuid().ToString("N") + ".log")
    & npm run build > $npmLog 2>&1
    $npmExit = $LASTEXITCODE
    $npmOut = if (Test-Path -LiteralPath $npmLog) { Get-Content -LiteralPath $npmLog -Raw -ErrorAction SilentlyContinue } else { "" }
    if (Test-Path -LiteralPath $npmLog) { Remove-Item -LiteralPath $npmLog -Force -ErrorAction SilentlyContinue }
    if ($npmExit -ne 0) {
        Add-Error "frontend build failing:`n$($npmOut -split "`n" | Select-Object -Last 10 | Out-String)"
    } else {
        Write-Host "[OK] frontend build passes" -ForegroundColor Green
    }
} finally {
    Pop-Location
}

# Summary
Write-Host ""
if ($errors.Count -gt 0) {
    Write-Host "PRE-RELEASE CHECK FAILED ($($errors.Count) errors):" -ForegroundColor Red
    foreach ($e in $errors) { Write-Host "  - $e" -ForegroundColor Red }
    exit 1
}
Write-Host "ALL PRE-RELEASE CHECKS PASSED" -ForegroundColor Green
exit 0
