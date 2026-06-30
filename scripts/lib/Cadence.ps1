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

function Get-HwAgentShortcutActionId {
  param([Parameter(Mandatory=$true)]$Object)
  if (Test-HwAgentProperty -Object $Object -Name "shortcut_action") {
    return [string]$Object.shortcut_action
  }
  if ([string]$Object.id -eq "cadence_nc_toggle") {
    return "NC Toggle Selected Parts"
  }
  return (([string]$Object.id) + "_shortcut")
}

function Get-HwAgentShortcutCleanupActionIds {
  param([Parameter(Mandatory=$true)]$Object)
  $ids = New-Object System.Collections.Generic.List[string]
  if ($Object.show_in_cadence -ne $true) {
    $ids.Add((Get-HwAgentShortcutActionId -Object $Object)) | Out-Null
  }
  $legacy = (([string]$Object.id) + "_shortcut")
  if (-not $ids.Contains($legacy)) { $ids.Add($legacy) | Out-Null }
  return $ids.ToArray()
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

  $registeredNamespaces = @{}

  foreach ($item in @($items)) {
    if ($item.type -ne "cadence_tcl") { continue }
    # 收集要清理的 namespace
    if ($item.module) {
      $ns = [string]$item.command
      if ($ns -match '^(::[^:]+)') {
        $nsName = $matches[1]
        if (-not $registeredNamespaces.ContainsKey($nsName)) {
          $registeredNamespaces[$nsName] = $true
        }
      }
    }
    if ($item.show_in_cadence -ne $true) { continue }
    $name = Escape-TclMenuText ([string]$item.name)
    if (Test-HwAgentProperty -Object $item -Name "shortcut") {
      $name = Escape-TclMenuText (([string]$item.name) + " (" + ([string]$item.shortcut) + ")")
    }
    $command = Escape-TclMenuText ([string]$item.command)
    if ($item.module) {
      $module = Escape-TclPathLiteral ([string]$item.module)
      $lines += ('        source "$::IAC_ROOT/' + $module + '"')
    }
    $lines += ('        AddAccessoryMenu "insta360_HW" "' + $name + '" "' + $command + '"')
  }

  # 生成 cleanup 块：放在 addAccessory proc 开头，加载新内容前先清理旧残留
  $cleanupLines = @('        # ---- cleanup old module state (hot-reload safe) ----')
  foreach ($nsName in ($registeredNamespaces.Keys | Sort-Object)) {
    $cleanupLines += ('        catch {namespace delete ' + $nsName + '}')
  }
  $cleanup = ($cleanupLines -join "`r`n")
  return ($cleanup + "`r`n" + ($lines -join "`r`n"))
}

function Get-EnabledCadenceShortcutItems {
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
    if (-not (Test-HwAgentProperty -Object $item -Name "shortcut")) { continue }
    foreach ($cleanupId in (Get-HwAgentShortcutCleanupActionIds -Object $item)) {
      $actionId = Escape-TclMenuText $cleanupId
      $lines += ('    catch {RegisterAction "' + $actionId + '" "::IAC::shouldProcess" "" "" ""}')
    }
  }

  foreach ($item in @($items)) {
    if ($item.type -ne "cadence_tcl") { continue }
    if ($item.show_in_cadence -ne $true) { continue }
    if (-not (Test-HwAgentProperty -Object $item -Name "shortcut")) { continue }

    if ($item.module) {
      $module = Escape-TclPathLiteral ([string]$item.module)
      $lines += ('    source "$::IAC_ROOT/' + $module + '"')
    }
    $actionId = Escape-TclMenuText (Get-HwAgentShortcutActionId -Object $item)
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
    $lines += ('    if {[catch {RegisterAction "' + $actionId + '" "' + $enabledCommand + '" "' + $shortcut + '" "' + $shortcutCommand + '" "' + $shortcutContext + '"} err]} {')
    $lines += ('        ::IAC::log "IAC: shortcut registration failed: ' + $actionId + ' $err"')
    $lines += ('    } else {')
    $lines += ('        ::IAC::log "IAC: shortcut registered: ' + $actionId + ' ' + $shortcut + '"')
    $lines += ('    }')
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
  $shortcutItems = Get-EnabledCadenceShortcutItems -ToolRoot $ToolRoot
  $template = $template -replace '(?m)^\s*# \{\{CADENCE_SCRIPT_MENU_ITEMS\}\}', $menuItems
  $template = $template -replace '(?m)^\s*# \{\{CADENCE_SCRIPT_SHORTCUT_ITEMS\}\}', $shortcutItems
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

