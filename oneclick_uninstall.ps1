param(
    [switch]$Silent,
    [ValidateSet("", "Detach", "Full")]
    [string]$Mode = ""
)

$ErrorActionPreference = "Stop"

function T {
    param([Parameter(Mandatory=$true)][string]$Base64)
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Base64))
}

$Host.UI.RawUI.WindowTitle = T "SFdBZ2VudCDkuIDplK7ljbjovb0="

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$UninstallScript = Join-Path $ScriptDir "uninstall.ps1"

function Write-Title {
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host (T "ICBJbnN0YTM2MCDnoazku7bmj5DmlYjlubPlj7AgLSDkuIDplK7ljbjovb0=") -ForegroundColor Cyan
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host ""
}

function Select-UninstallMode {
    if ($Mode) { return $Mode }
    if ($Silent) { return "Detach" }

    Write-Host (T "6K+36YCJ5oup5Y246L295pa55byPOg==") -ForegroundColor Yellow
    Write-Host (T "ICAxLiDlj6rnp7vpmaQgQ2FwdHVyZSDlhaXlj7Dmlofku7bjgIHmnInkuIDliJc=") -ForegroundColor Green
    Write-Host (T "ICAgICDkv53nlZnlubPlj7Dmlofku7bjgIHlkoXmnJ/lkJHmiJDorqTlvZDjgIHphY3nva7ljoblj7LorrDlvZXjgII=") -ForegroundColor Gray
    Write-Host ""
    Write-Host (T "ICAyLiDlrozmlbTljbjovb0=") -ForegroundColor Red
    Write-Host (T "ICAgICDliKDpmaTmlbTkuKrlubPlj7Dnm67lvZXvvIzljIXmi6wgZGF0YeOAgWNvbmZpZ+OAgXBsdWdpbnMvdXNlciDoh6rlrprkuYnohJrmnKzjgII=") -ForegroundColor Gray
    Write-Host ""

    $choice = Read-Host (T "6L6T5YWlIDEg5oiW55u05o6l5Zue6L2m6YCJ5oup5o6o6I2Q6aG577yb6L6T5YWlIDIg5a6M5pW05Y246L29")
    if ($choice -eq "2") { return "Full" }
    return "Detach"
}

function Confirm-FullCleanup {
    param([Parameter(Mandatory=$true)][string]$Root)
    if ($Silent) { return }

    Write-Host ""
    Write-Host (T "5a6M5pW05Y246L295bCG5Yig6Zmk5pW05Liq5bmz5Y+w55uu5b2VOg==") -ForegroundColor Red
    Write-Host "  $Root" -ForegroundColor Yellow
    Write-Host ""
    $answer = Read-Host (T "56Gu6K6k5Yig6Zmk6K+36L6T5YWlIERFTEVURe+8jOWFtuS7lui+k+WFpeWPlua2iA==")
    if ($answer -ne "DELETE") {
        Write-Host ""
        Write-Host (T "5bey5Y+W5raI5a6M5pW05Y246L2944CC") -ForegroundColor Green
        exit 0
    }
}

Write-Title

if (-not (Test-Path -LiteralPath $UninstallScript)) {
    Write-Host (T "5pyq5om+5YiwIHVuaW5zdGFsbC5wczHvvIzor7fnoa7orqTlubPlj7Dmlofku7blrozmlbTjgII=") -ForegroundColor Red
    exit 1
}

$selectedMode = Select-UninstallMode

if ($selectedMode -eq "Full") {
    Confirm-FullCleanup -Root $ScriptDir
    Set-Location -LiteralPath ([System.IO.Path]::GetTempPath())
}

Write-Host ""
Write-Host ((T "5byA5aeL5Y246L2977yM5qih5byPOiA=") + $selectedMode) -ForegroundColor White
Write-Host "==========================================" -ForegroundColor Gray
Write-Host ""

& powershell -NoProfile -ExecutionPolicy Bypass -File $UninstallScript -Mode $selectedMode -InstallDir $ScriptDir -Force
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host (T "5Y246L296L+H56iL5Ye66ZSZ77yM6K+35p+l55yL5LiK5pa55pel5b+X44CC") -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
if ($selectedMode -eq "Full") {
    Write-Host (T "ICDlrozmlbTljbjovb3lrozmiJDjgII=") -ForegroundColor Green
    Write-Host (T "ICBDYXB0dXJlIOWFpeWPo+OAgeWQjuWPsOacjeWKoeWSjOW5s+WPsOebruW9leWdh+W3sua4heeQhuOAgg==") -ForegroundColor White
} else {
    Write-Host (T "ICDljbjovb3lrozmiJDjgII=") -ForegroundColor Green
    Write-Host (T "ICDlt7Lnp7vpmaQgQ2FwdHVyZSDlhaXlj7Dmlofku7bjgIHnvJblgLzlvZXkuLrmlbDmja7jgII=") -ForegroundColor White
    Write-Host (T "ICDlubPlj7Dmlofku7bjgIHlkoXkuK3lkozoh6rlrprkuYnohJrmnKzmhYvkvZPkuozjgII=") -ForegroundColor White
    Write-Host (T "ICDlpoLpnIDph43mlrDlronoo4XvvIzor7flj4zlh7sgW+S4gOmUruWuieijhS5iYXRd44CC") -ForegroundColor Yellow
}
Write-Host "==========================================" -ForegroundColor Cyan
