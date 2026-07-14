param(
  [Parameter(Mandatory = $true)][string]$Out
)
# Capture COM BOM export. $Out must be the current invocation's job-local path.
# This script never substitutes an older workbook after a failed export.
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Out) | Out-Null

try {
  $app = [Runtime.InteropServices.Marshal]::GetActiveObject("OrCAD.Application")
  # Configure the version-specific Capture COM export here to write exactly $Out.
  throw "COM BOM 导出未配置（请在 cadence_export.ps1 方式1 中按版本填入真实调用）"
} catch {
  $message = "COM BOM export failed for current job output '$Out': $($_.Exception.Message)"
  Write-Error $message
  throw $message
}
