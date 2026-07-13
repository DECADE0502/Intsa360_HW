$ErrorActionPreference = "Stop"

$script:HwAgentPythonVersion = "3.11.9"
$script:HwAgentPythonZipUrl = "https://www.python.org/ftp/python/$script:HwAgentPythonVersion/python-$script:HwAgentPythonVersion-embed-amd64.zip"
$script:HwAgentPythonZipSha256 = "009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b"

$script:HwAgentPythonWheels = @(
  @{
    Name = "openpyxl"
    FileName = "openpyxl-3.1.5-py2.py3-none-any.whl"
    Url = "https://files.pythonhosted.org/packages/c0/da/977ded879c29cbd04de313843e76868e6e13408a94ed6b987245dc7c8506/openpyxl-3.1.5-py2.py3-none-any.whl"
    Sha256 = "5282c12b107bffeef825f4617dc029afaf41d0ea60823bbb665ef3079dc79de2"
  },
  @{
    Name = "et_xmlfile"
    FileName = "et_xmlfile-2.0.0-py3-none-any.whl"
    Url = "https://files.pythonhosted.org/packages/c1/8b/5fe2cc11fee489817272089c4203e679c63b570a5aaeb18d852ae3cbba6a/et_xmlfile-2.0.0-py3-none-any.whl"
    Sha256 = "7a91720bc756843502c3b7504c77b8fe44217c85c537d85037f0f536151b2caa"
  }
)

function Assert-HwAgentSha256 {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$ExpectedSha256
  )
  if (-not (Test-Path -LiteralPath $Path)) {
    throw "File not found for SHA256 verification: $Path"
  }
  $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
  $expected = $ExpectedSha256.ToLowerInvariant()
  if ($actual -ne $expected) {
    throw "SHA256 mismatch for $Path`: expected $expected, got $actual"
  }
}

function Get-HwAgentDownloadCacheRoot {
  $base = $env:LOCALAPPDATA
  if ([string]::IsNullOrWhiteSpace($base)) { $base = [System.IO.Path]::GetTempPath() }
  return (Join-Path $base "Insta360_HW\build-cache\downloads")
}

function Get-HwAgentDownloadCachePath {
  param(
    [Parameter(Mandatory=$true)][string]$Url,
    [Parameter(Mandatory=$true)][string]$Sha256
  )
  $name = [System.IO.Path]::GetFileName(([uri]$Url).AbsolutePath)
  if ([string]::IsNullOrWhiteSpace($name)) { $name = "download.bin" }
  $name = $name -replace '[^0-9A-Za-z._-]', '_'
  return (Join-Path (Get-HwAgentDownloadCacheRoot) ($Sha256.ToLowerInvariant() + "-" + $name))
}

function Invoke-HwAgentDownload {
  param(
    [Parameter(Mandatory=$true)][string]$Url,
    [Parameter(Mandatory=$true)][string]$OutFile,
    [Parameter(Mandatory=$true)][string]$Sha256
  )
  $cache = Get-HwAgentDownloadCachePath -Url $Url -Sha256 $Sha256
  $cacheDir = Split-Path -Parent $cache
  New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
  $cacheValid = $false
  if (Test-Path -LiteralPath $cache -PathType Leaf) {
    try {
      Assert-HwAgentSha256 -Path $cache -ExpectedSha256 $Sha256
      $cacheValid = $true
    } catch {
      Remove-Item -LiteralPath $cache -Force -ErrorAction SilentlyContinue
    }
  }
  if (-not $cacheValid) {
    $partial = Join-Path $cacheDir ((Split-Path -Leaf $cache) + "." + [guid]::NewGuid().ToString("N") + ".part")
    try {
      Invoke-WebRequest -Uri $Url -OutFile $partial -UseBasicParsing
      Assert-HwAgentSha256 -Path $partial -ExpectedSha256 $Sha256
      Move-Item -LiteralPath $partial -Destination $cache -Force
    } finally {
      Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
    }
  } else {
    Write-Host ("Using verified download cache: " + (Split-Path -Leaf $cache))
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutFile) | Out-Null
  Copy-Item -LiteralPath $cache -Destination $OutFile -Force
  Assert-HwAgentSha256 -Path $OutFile -ExpectedSha256 $Sha256
}

function Expand-HwAgentZip {
  param(
    [Parameter(Mandatory=$true)][string]$Archive,
    [Parameter(Mandatory=$true)][string]$Destination
  )
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  [System.IO.Compression.ZipFile]::ExtractToDirectory($Archive, $Destination)
}

function Enable-HwAgentEmbeddedSitePackages {
  param([Parameter(Mandatory=$true)][string]$PythonDir)
  $pth = Get-ChildItem -LiteralPath $PythonDir -Filter "python*._pth" -File | Select-Object -First 1
  if (-not $pth) { throw "Embedded Python _pth file not found in $PythonDir" }
  $lines = Get-Content -LiteralPath $pth.FullName -Encoding ASCII
  $updated = New-Object System.Collections.Generic.List[string]
  $hasSitePackages = $false
  $hasImportSite = $false
  foreach ($line in $lines) {
    if ($line.Trim() -eq "Lib/site-packages") { $hasSitePackages = $true }
    if ($line.Trim() -eq "import site") { $hasImportSite = $true }
    if ($line.Trim() -eq "#import site") {
      $updated.Add("import site") | Out-Null
      $hasImportSite = $true
    } else {
      $updated.Add($line) | Out-Null
    }
  }
  if (-not $hasSitePackages) { $updated.Insert([Math]::Max(0, $updated.Count - 1), "Lib/site-packages") }
  if (-not $hasImportSite) { $updated.Add("import site") | Out-Null }
  Set-Content -LiteralPath $pth.FullName -Value $updated.ToArray() -Encoding ASCII
}

function Download-EmbeddedPython {
  param([Parameter(Mandatory=$true)][string]$OutDir)
  if (Test-Path -LiteralPath $OutDir) {
    Remove-Item -LiteralPath $OutDir -Recurse -Force
  }
  New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
  $zip = Join-Path $OutDir "python-embed.zip"
  Invoke-HwAgentDownload -Url $script:HwAgentPythonZipUrl -OutFile $zip -Sha256 $script:HwAgentPythonZipSha256
  Expand-HwAgentZip -Archive $zip -Destination $OutDir
  Remove-Item -LiteralPath $zip -Force
  New-Item -ItemType Directory -Force -Path (Join-Path $OutDir "Lib\site-packages") | Out-Null
  Enable-HwAgentEmbeddedSitePackages -PythonDir $OutDir
}

function Install-HwAgentWheel {
  param(
    [Parameter(Mandatory=$true)][string]$WheelPath,
    [Parameter(Mandatory=$true)][string]$SitePackages
  )
  $extractDir = Join-Path ([System.IO.Path]::GetTempPath()) ("hwagent-wheel-" + [System.Guid]::NewGuid().ToString("N"))
  try {
    New-Item -ItemType Directory -Force -Path $extractDir | Out-Null
    Expand-HwAgentZip -Archive $WheelPath -Destination $extractDir
    Get-ChildItem -LiteralPath $extractDir -Force |
      ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $SitePackages -Recurse -Force }
  } finally {
    if (Test-Path -LiteralPath $extractDir) {
      Remove-Item -LiteralPath $extractDir -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

function Install-OpenpyxlWheel {
  param([Parameter(Mandatory=$true)][string]$PythonDir)
  $sitePackages = Join-Path $PythonDir "Lib\site-packages"
  New-Item -ItemType Directory -Force -Path $sitePackages | Out-Null
  $wheelDir = Join-Path $PythonDir "wheels"
  New-Item -ItemType Directory -Force -Path $wheelDir | Out-Null
  foreach ($wheel in $script:HwAgentPythonWheels) {
    $wheelPath = Join-Path $wheelDir $wheel.FileName
    Invoke-HwAgentDownload -Url $wheel.Url -OutFile $wheelPath -Sha256 $wheel.Sha256
    Install-HwAgentWheel -WheelPath $wheelPath -SitePackages $sitePackages
  }
  Remove-Item -LiteralPath $wheelDir -Recurse -Force
}
