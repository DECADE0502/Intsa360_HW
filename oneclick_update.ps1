param([switch]$Silent)

$ErrorActionPreference = "Stop"

function T {
    param([Parameter(Mandatory=$true)][string]$Base64)
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Base64))
}

$Host.UI.RawUI.WindowTitle = T "SFdBZ2VudCDkuIDplK7mm7TmlrA="

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$UpdateScript = Join-Path $ScriptDir "update.ps1"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host (T "ICBJbnN0YTM2MCDnoazku7bmj5DmlYjlubPlj7AgLSDkuIDplK7mm7TmlrA=") -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path -LiteralPath $UpdateScript)) {
    Write-Host (T "5pyq5om+5YiwIHVwZGF0ZS5wczHvvIzor7fnoa7orqTlubPlj7Dmlofku7blrozmlbTjgII=") -ForegroundColor Red
    exit 1
}

$git = Get-Command git.exe -ErrorAction SilentlyContinue
if (-not $git) {
    Write-Host (T "5pyq5om+5YiwIEdpdO+8jOaXoOazleS7juS7k+W6k+aJp+ihjCBPVEEg5pu05paw44CC") -ForegroundColor Red
    Write-Host (T "6K+35YWI5a6J6KOFIEdpdCBmb3IgV2luZG93c++8jOaIluiuqee7tOaKpOiAheebtOaOpeWQjOatpeaWsOeJiOW5s+WPsOaWh+S7tuWkueOAgg==") -ForegroundColor Yellow
    Write-Host (T "5LiL6L295Zyw5Z2AOiBodHRwczovL2dpdC1zY20uY29tL2Rvd25sb2FkL3dpbg==") -ForegroundColor Gray
    exit 1
}

Write-Host (T "5Y2z5bCG5pu05paw5bmz5Y+w56iL5bqP5paH5Lu244CC") -ForegroundColor Yellow
Write-Host (T "5Lya5L+d55WZIGRhdGHjgIFjb25maWcvbG9jYWwuanNvbuOAgXBsdWdpbnMvdXNlciDnrYnnlKjmiLfmlbDmja7jgII=") -ForegroundColor Gray
Write-Host ""

if (-not $Silent) {
    $answer = Read-Host (T "56Gu6K6k5pu05pawPyDovpPlhaUgWSDnu6fnu63vvIzlhbbku5bplK7lj5bmtog=")
    if ($answer -ne "Y" -and $answer -ne "y") {
        Write-Host (T "5bey5Y+W5raI5pu05paw44CC") -ForegroundColor Green
        exit 0
    }
}

& powershell -NoProfile -ExecutionPolicy Bypass -File $UpdateScript
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host (T "5pu05paw6L+H56iL5Ye66ZSZ77yM6K+35p+l55yL5LiK5pa55pel5b+X44CC") -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host (T "ICDmm7TmlrDlrozmiJDjgII=") -ForegroundColor Green
Write-Host (T "ICDlpoIgT3JDQUQgQ2FwdHVyZSDlt7LmiZPlvIDvvIzor7fmiafooYzng63mm7TmlrDmjIfku6TmiJbph43lkK8gQ2FwdHVyZeOAgg==") -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Cyan
