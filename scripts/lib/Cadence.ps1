$ErrorActionPreference = "Stop"

function Get-HwAgentText {
  param([Parameter(Mandatory=$true)][string]$Base64)
  return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Base64))
}

function ConvertTo-TclPath {
  param([Parameter(Mandatory=$true)][string]$Path)
  return ($Path -replace "\\", "/")
}

function Escape-TclMenuText {
  param([Parameter(Mandatory=$true)][string]$Text)
  return (($Text -replace "\\", "\\") -replace '"', '\"')
}

function Escape-TclPathLiteral {
  param([Parameter(Mandatory=$true)][string]$Text)
  return (($Text -replace "\\", "/") -replace '"', '\"')
}

function Test-HwAgentProperty {
  param(
    [Parameter(Mandatory=$true)]$Object,
    [Parameter(Mandatory=$true)][string]$Name
  )
  return $null -ne $Object.PSObject.Properties[$Name] -and -not [string]::IsNullOrWhiteSpace([string]$Object.$Name)
}

function Get-EnabledCadenceMenuItems {
  param([Parameter(Mandatory=$true)][string]$ToolRoot)
  $lines = @()

  $items = @()
  $capabilitiesPath = Join-Path $ToolRoot "config\capabilities.json"
  if (Test-Path -LiteralPath $capabilitiesPath) {
    $data = Get-Content -LiteralPath $capabilitiesPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $items += @($data.capabilities)
  }

  $userPluginDir = Join-Path $ToolRoot "plugins\user"
  if (Test-Path -LiteralPath $userPluginDir) {
    foreach ($manifest in Get-ChildItem -LiteralPath $userPluginDir -Filter "*.json" -File -ErrorAction SilentlyContinue) {
      $plugin = Get-Content -LiteralPath $manifest.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
      if ($plugin.type -eq "cadence_tcl" -and $plugin.script) {
        $plugin | Add-Member -NotePropertyName module -NotePropertyValue ("plugins/user/" + ([string]$plugin.script -replace "\\", "/")) -Force
      }
      $items += $plugin
    }
  }

  foreach ($item in @($items)) {
    if ($item.type -ne "cadence_tcl") { continue }
    if ($item.show_in_cadence -ne $true) { continue }
    $name = Escape-TclMenuText ([string]$item.name)
    $command = Escape-TclMenuText ([string]$item.command)
    if ($item.module) {
      $module = Escape-TclPathLiteral ([string]$item.module)
      $lines += ('        source "$::IAC_ROOT/' + $module + '"')
    }
    $lines += ('        AddAccessoryMenu "insta360_HW" "' + $name + '" "' + $command + '"')
    if (Test-HwAgentProperty -Object $item -Name "shortcut") {
      $actionId = Escape-TclMenuText (([string]$item.id) + "_shortcut")
      $enabledCommand = "::IAC::shouldProcess"
      if (Test-HwAgentProperty -Object $item -Name "enabled_command") {
        $enabledCommand = [string]$item.enabled_command
      }
      $shortcutCommand = [string]$item.command
      if (Test-HwAgentProperty -Object $item -Name "shortcut_command") {
        $shortcutCommand = [string]$item.shortcut_command
      }
      $shortcut = Escape-TclMenuText ([string]$item.shortcut)
      $shortcutContext = ""
      if (Test-HwAgentProperty -Object $item -Name "shortcut_context") {
        $shortcutContext = [string]$item.shortcut_context
      }
      $enabledCommand = Escape-TclMenuText $enabledCommand
      $shortcutCommand = Escape-TclMenuText $shortcutCommand
      $shortcutContext = Escape-TclMenuText $shortcutContext
      $lines += ('        catch {RegisterAction "' + $actionId + '" "' + $enabledCommand + '" "' + $shortcut + '" "' + $shortcutCommand + '" "' + $shortcutContext + '"}')
    }
  }
  return ($lines -join "`r`n")
}

function Write-CadenceLoader {
  param(
    [Parameter(Mandatory=$true)][string]$ToolRoot,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string]$OutputPath
  )
  $root = ConvertTo-TclPath $ToolRoot
  $python = ConvertTo-TclPath $PythonPath
  # Static check anchors:
  # InsertXMLMenu top label: "insta360_HW"
  # Default platform actions are registered only with InsertXMLMenu.
  $templatePath = Join-Path $ToolRoot "cadence\iac_bom_tool.tcl"
  if (-not (Test-Path -LiteralPath $templatePath)) {
    throw ((Get-HwAgentText "5pyq5om+5YiwIENhZGVuY2UgVGNsIOaooeadv++8mg==") + $templatePath)
  }
  $template = Get-Content -LiteralPath $templatePath -Raw -Encoding UTF8
  $template = $template -replace 'set ::IAC_ROOT ".*"', ('set ::IAC_ROOT "' + $root + '"')
  $template = $template -replace 'set ::IAC_PY\s+".*"', ('set ::IAC_PY   "' + $python + '"')
  $menuItems = Get-EnabledCadenceMenuItems -ToolRoot $ToolRoot
  $template = $template -replace '(?m)^\s*# \{\{CADENCE_SCRIPT_MENU_ITEMS\}\}', $menuItems
  $encoding = [System.Text.Encoding]::GetEncoding(936)
  [System.IO.File]::WriteAllText($OutputPath, $template, $encoding)
  return $OutputPath
}

function Install-CadenceLoader {
  param(
    [Parameter(Mandatory=$true)][string]$ToolRoot,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string[]]$AutoLoadDirs
  )
  $installed = @()
  foreach ($dir in $AutoLoadDirs) {
    if (-not $dir) { continue }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $target = Join-Path $dir "iac_bom_tool.tcl"
    Write-CadenceLoader -ToolRoot $ToolRoot -PythonPath $PythonPath -OutputPath $target | Out-Null
    Write-Host ((Get-HwAgentText "5bey5a6J6KOFIENhZGVuY2Ug6I+c5Y2V6ISa5pys77ya") + $target)
    $installed += $target
  }
  return $installed
}

