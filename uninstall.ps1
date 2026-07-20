param(
  [ValidateSet("PreserveData", "PurgeData", "Detach", "Full")]
  [string]$Mode = "PurgeData",
  [string]$InstallDir = "",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$uninstallKey = "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{B7F3AC9E-2D5E-4A8C-9F6E-1A3D4E5F6B72}_is1"

function Get-ExecutableFromCommand {
  param([string]$Command)

  $value = [string]$Command
  if ([string]::IsNullOrWhiteSpace($value)) { return "" }
  $value = $value.Trim()
  if ($value -match '^"([^"]+\.exe)"') { return [string]$Matches[1] }
  if ($value -match '^(.+?\.exe)(?:\s|$)') { return ([string]$Matches[1]).Trim() }
  return ""
}

function Find-RegisteredUninstaller {
  foreach ($registryPath in @(
    "Registry::HKEY_LOCAL_MACHINE\$uninstallKey",
    "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{B7F3AC9E-2D5E-4A8C-9F6E-1A3D4E5F6B72}_is1",
    "Registry::HKEY_CURRENT_USER\$uninstallKey",
    "Registry::HKEY_CURRENT_USER\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{B7F3AC9E-2D5E-4A8C-9F6E-1A3D4E5F6B72}_is1"
  )) {
    $registration = Get-ItemProperty -LiteralPath $registryPath -ErrorAction SilentlyContinue
    if ($null -eq $registration) { continue }

    $fromCommand = Get-ExecutableFromCommand -Command ([string]$registration.UninstallString)
    if (-not [string]::IsNullOrWhiteSpace($fromCommand) -and
        (Test-Path -LiteralPath $fromCommand -PathType Leaf)) {
      return [System.IO.Path]::GetFullPath($fromCommand)
    }

    $registeredDir = [string]$registration.InstallLocation
    if (-not [string]::IsNullOrWhiteSpace($registeredDir)) {
      $candidate = Join-Path $registeredDir "unins000.exe"
      if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        return [System.IO.Path]::GetFullPath($candidate)
      }
    }
  }
  return ""
}

function Resolve-OfficialUninstaller {
  param([string]$RequestedInstallDir)

  if (-not [string]::IsNullOrWhiteSpace($RequestedInstallDir)) {
    return [System.IO.Path]::GetFullPath((Join-Path $RequestedInstallDir "unins000.exe"))
  }

  $registered = Find-RegisteredUninstaller
  if (-not [string]::IsNullOrWhiteSpace($registered)) { return $registered }

  $candidates = New-Object System.Collections.Generic.List[string]
  foreach ($base in @(
    $env:ProgramFiles,
    ${env:ProgramFiles(x86)},
    $env:ProgramData
  )) {
    if (-not [string]::IsNullOrWhiteSpace([string]$base)) {
      $candidates.Add((Join-Path $base "Insta360\HWAgent\unins000.exe"))
    }
  }
  foreach ($drive in [System.IO.DriveInfo]::GetDrives()) {
    if ($drive.IsReady -and $drive.DriveType -eq [System.IO.DriveType]::Fixed) {
      $candidates.Add((Join-Path $drive.RootDirectory.FullName "Insta360\HWAgent\unins000.exe"))
    }
  }

  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
      return [System.IO.Path]::GetFullPath($candidate)
    }
  }
  return ""
}

$mappedMode = $Mode
if ($Mode -eq "Detach") {
  $mappedMode = "PreserveData"
  Write-Host "兼容模式 Detach 已映射为 PreserveData（保留用户数据）。"
} elseif ($Mode -eq "Full") {
  $mappedMode = "PurgeData"
  Write-Host "兼容模式 Full 已映射为 PurgeData（清除用户数据）。"
}

try {
  $uninstaller = Resolve-OfficialUninstaller -RequestedInstallDir $InstallDir
  if ([string]::IsNullOrWhiteSpace($uninstaller) -or
      -not (Test-Path -LiteralPath $uninstaller -PathType Leaf)) {
    throw "未找到平台官方卸载器 unins000.exe。请通过 Windows 设置中的已安装应用卸载平台；若条目损坏，请重新运行 Insta360_HW_Setup.exe 修复后再卸载。"
  }

  $dataArgument = if ($mappedMode -eq "PreserveData") { "/PRESERVEDATA" } else { "/PURGEDATA" }
  $arguments = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", $dataArgument)
  $displayCommand = '& "{0}" {1}' -f $uninstaller, ($arguments -join " ")

  if ($DryRun) {
    Write-Host "将执行官方卸载命令："
    Write-Host $displayCommand
    exit 0
  }

  $process = Start-Process -FilePath $uninstaller -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
  if ($process.ExitCode -ne 0) {
    throw "官方卸载器执行失败，退出码：$($process.ExitCode)。"
  }
  exit 0
} catch {
  Write-Error $_.Exception.Message
  exit 1
}
