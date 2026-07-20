$script:HwAgentSupportedCadenceVersions = @("16.6", "17.4")
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

function ConvertTo-HwAgentUniqueFullPaths {
  param([AllowEmptyCollection()][string[]]$Paths = @())

  $result = New-Object System.Collections.Generic.List[string]
  $seen = @{}
  foreach ($path in $Paths) {
    if ([string]::IsNullOrWhiteSpace([string]$path)) { continue }
    try {
      $resolved = [System.IO.Path]::GetFullPath([string]$path)
      $root = [System.IO.Path]::GetPathRoot($resolved)
      $full = if ($resolved -ieq $root) { $root } else { $resolved.TrimEnd("\") }
    } catch { continue }
    if ([string]::IsNullOrWhiteSpace($full) -or $seen.ContainsKey($full)) { continue }
    $seen[$full] = $true
    $result.Add($full) | Out-Null
  }
  return $result.ToArray()
}

function Get-HwAgentDefaultCadenceDriveRoots {
  return @()
}

function Get-HwAgentDefaultCadenceUserRoots {
  $homeProfile = ""
  if (-not [string]::IsNullOrWhiteSpace($env:HOMEDRIVE) -and
      -not [string]::IsNullOrWhiteSpace($env:HOMEPATH)) {
    $homeProfile = $env:HOMEDRIVE + $env:HOMEPATH
  }
  return @(ConvertTo-HwAgentUniqueFullPaths -Paths @(
    $env:SPB_DATA,
    $env:CDS_DATA,
    $env:HOME,
    $homeProfile,
    $env:USERPROFILE
  ))
}

function ConvertTo-HwAgentCadenceUserAutoLoadPath {
  param([Parameter(Mandatory=$true)][string]$Root)

  $full = [System.IO.Path]::GetFullPath($Root).TrimEnd("\")
  if ($full.EndsWith("\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad", [System.StringComparison]::OrdinalIgnoreCase)) {
    return $full
  }
  if ($full.EndsWith("\cdssetup\OrCAD_Capture", [System.StringComparison]::OrdinalIgnoreCase)) {
    return (Join-Path $full "tclscripts\capAutoLoad")
  }
  return (Join-Path $full "cdssetup\OrCAD_Capture\tclscripts\capAutoLoad")
}

function Resolve-HwAgentCadenceVendorInstallRoot {
  param([Parameter(Mandatory=$true)][string]$Path)

  $full = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
  if ($full.EndsWith("\tools\capture\tclscripts\capAutoLoad", [System.StringComparison]::OrdinalIgnoreCase)) {
    foreach ($unused in 1..4) { $full = Split-Path -Parent $full }
  } elseif ((Split-Path -Leaf $full) -ieq "tools") {
    $full = Split-Path -Parent $full
  }
  return $full
}

function Get-HwAgentCadenceVendorRootCandidates {
  param(
    [AllowEmptyCollection()][string[]]$DriveRoots = @(),
    [AllowEmptyCollection()][string[]]$VendorRoots = @()
  )

  $candidates = New-Object System.Collections.Generic.List[object]
  foreach ($value in @(ConvertTo-HwAgentUniqueFullPaths -Paths $VendorRoots)) {
    try { $root = Resolve-HwAgentCadenceVendorInstallRoot -Path $value } catch { continue }
    foreach ($version in $script:HwAgentSupportedCadenceVersions) {
      if ((Split-Path -Leaf $root) -ieq ("SPB_" + $version)) {
        $candidates.Add([pscustomobject]@{ version = $version; root = $root }) | Out-Null
      }
    }
  }
  foreach ($drive in @(ConvertTo-HwAgentUniqueFullPaths -Paths $DriveRoots)) {
    foreach ($version in $script:HwAgentSupportedCadenceVersions) {
      foreach ($relative in @(
        ("Cadence\SPB_" + $version),
        ("Cadence\Cadence\SPB_" + $version)
      )) {
        $candidates.Add([pscustomobject]@{ version = $version; root = (Join-Path $drive $relative) }) | Out-Null
      }
    }
  }
  return $candidates.ToArray()
}

function Get-HwAgentCadenceDiscovery {
  param(
    [AllowEmptyCollection()][string[]]$DriveRoots = (Get-HwAgentDefaultCadenceDriveRoots),
    [AllowEmptyCollection()][string[]]$UserRoots = (Get-HwAgentDefaultCadenceUserRoots),
    [AllowEmptyCollection()][string[]]$VendorRoots = @()
  )

  $userCandidates = New-Object System.Collections.Generic.List[string]
  foreach ($root in @(ConvertTo-HwAgentUniqueFullPaths -Paths $UserRoots)) {
    try { $userCandidates.Add((ConvertTo-HwAgentCadenceUserAutoLoadPath -Root $root)) | Out-Null } catch { continue }
  }
  $userCandidates = @(ConvertTo-HwAgentUniqueFullPaths -Paths $userCandidates.ToArray())
  $existingUserDirs = @($userCandidates | Where-Object {
    $captureRoot = Split-Path -Parent (Split-Path -Parent $_)
    $cdsSetupRoot = Split-Path -Parent $captureRoot
    ((Split-Path -Leaf $captureRoot) -ieq "OrCAD_Capture") -and
    ((Split-Path -Leaf $cdsSetupRoot) -ieq "cdssetup") -and
    (Test-Path -LiteralPath $captureRoot -PathType Container)
  })
  $userDirs = @(ConvertTo-HwAgentUniqueFullPaths -Paths $existingUserDirs)

  $vendorInstallations = New-Object System.Collections.Generic.List[object]
  $seenVendor = @{}
  $defaultVendorRoots = @($env:CDSROOT, $env:CDS_ROOT, $env:CADENCE_ROOT)
  foreach ($candidate in @(Get-HwAgentCadenceVendorRootCandidates `
      -DriveRoots $DriveRoots -VendorRoots @($VendorRoots + $defaultVendorRoots))) {
    $autoLoad = Join-Path ([string]$candidate.root) "tools\capture\tclscripts\capAutoLoad"
    if (-not (Test-Path -LiteralPath $autoLoad -PathType Container)) { continue }
    $full = [System.IO.Path]::GetFullPath($autoLoad).TrimEnd("\")
    if ($seenVendor.ContainsKey($full)) { continue }
    $seenVendor[$full] = $true
    $vendorInstallations.Add([pscustomobject]@{
      version = [string]$candidate.version
      root = [System.IO.Path]::GetFullPath([string]$candidate.root).TrimEnd("\")
      autoload_dir = $full
    }) | Out-Null
  }

  return [pscustomobject]@{
    schema_version = 1
    supported_versions = @($script:HwAgentSupportedCadenceVersions)
    user_autoload_dirs = @($userDirs)
    vendor_installations = @($vendorInstallations.ToArray())
    vendor_autoload_dirs = @($vendorInstallations.ToArray() | ForEach-Object { $_.autoload_dir })
  }
}

function Find-CadenceAutoLoadDirs {
  return @((Get-HwAgentCadenceDiscovery).user_autoload_dirs)
}

function Find-CadenceVendorAutoLoadDirs {
  return @((Get-HwAgentCadenceDiscovery).vendor_autoload_dirs)
}

function Find-CadenceLoaderInstallDirs {
  return @(Find-CadenceAutoLoadDirs)
}
