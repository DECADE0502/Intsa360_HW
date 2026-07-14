$ErrorActionPreference = "Stop"

$script:HwAgentCadenceLoaderMarker = "# Insta360_HW Cadence Loader | schema=2 | managed=true"

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

function Get-HwAgentCadenceMenuName {
  param([Parameter(Mandatory=$true)]$Object)
  if (Test-HwAgentProperty -Object $Object -Name "cadence_name") {
    return [string]$Object.cadence_name
  }
  $name = [string]$Object.name
  if ($name -cmatch "^[\x20-\x7E]+$") {
    return $name
  }
  return [string]$Object.id
}

function Get-HwAgentPluginStatePath {
  param(
    [Parameter(Mandatory=$true)][string]$ToolRoot,
    [string]$PluginStatePath
  )
  if (-not [string]::IsNullOrWhiteSpace($PluginStatePath)) {
    return $PluginStatePath
  }
  if ((Test-Path -LiteralPath (Join-Path $ToolRoot "install_manifest.json") -PathType Leaf) -and -not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    return (Join-Path $env:LOCALAPPDATA "Insta360_HW\config\plugin_state.json")
  }
  return (Join-Path $ToolRoot "config\plugin_state.json")
}

function Get-HwAgentPluginStateOverrides {
  param([Parameter(Mandatory=$true)][string]$PluginStatePath)
  $overrides = @{}
  if (-not (Test-Path -LiteralPath $PluginStatePath -PathType Leaf)) {
    return $overrides
  }
  try {
    $state = Get-Content -LiteralPath $PluginStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $state -or $state.schema_version -ne 1 -or $null -eq $state.plugins) {
      return $overrides
    }
    foreach ($property in @($state.plugins.PSObject.Properties)) {
      $entry = $property.Value
      if ($entry -is [bool]) {
        $overrides[[string]$property.Name] = [bool]$entry
      } elseif ($null -ne $entry -and $null -ne $entry.PSObject.Properties["enabled"] -and $entry.enabled -is [bool]) {
        $overrides[[string]$property.Name] = [bool]$entry.enabled
      }
    }
  } catch {
    return @{}
  }
  return $overrides
}

function Apply-HwAgentPluginStateOverrides {
  param(
    [Parameter(Mandatory=$true)][AllowEmptyCollection()][object[]]$Items,
    [Parameter(Mandatory=$true)][hashtable]$Overrides
  )
  foreach ($item in $Items) {
    if ($null -eq $item -or $item.type -ne "cadence_tcl") { continue }
    $id = [string]$item.id
    if (-not $Overrides.ContainsKey($id)) { continue }
    $enabled = [bool]$Overrides[$id]
    $item | Add-Member -NotePropertyName show_in_cadence -NotePropertyValue $enabled -Force
    $item | Add-Member -NotePropertyName status -NotePropertyValue $(if ($enabled) { "available" } else { "disabled" }) -Force
  }
  return $Items
}

function Get-EnabledCadenceMenuItems {
  param(
    [Parameter(Mandatory=$true)][string]$ToolRoot,
    [string]$PluginStatePath
  )
  $lines = @()
  $statePath = Get-HwAgentPluginStatePath -ToolRoot $ToolRoot -PluginStatePath $PluginStatePath

  $items = @()
  $capabilitiesPath = Join-Path $ToolRoot "config\capabilities.json"
  if (Test-Path -LiteralPath $capabilitiesPath) {
    $data = Get-Content -LiteralPath $capabilitiesPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $items += @($data.capabilities)
  }

  $userPluginDir = Join-Path $ToolRoot "plugins\user"
  if (Test-Path -LiteralPath $userPluginDir) {
    foreach ($manifest in Get-ChildItem -LiteralPath $userPluginDir -Filter "*.json" -File -ErrorAction SilentlyContinue) {
      try {
        $plugin = Get-Content -LiteralPath $manifest.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
      } catch {
        continue
      }
      if ($plugin.type -eq "cadence_tcl" -and $plugin.script) {
        $plugin | Add-Member -NotePropertyName module -NotePropertyValue ("plugins/user/" + ([string]$plugin.script -replace "\\", "/")) -Force
      }
      $items += $plugin
    }
  }
  $items = @(Apply-HwAgentPluginStateOverrides -Items $items -Overrides (Get-HwAgentPluginStateOverrides -PluginStatePath $statePath))

  $registeredNamespaces = @{}

  foreach ($item in @($items)) {
    if ($item.type -ne "cadence_tcl") { continue }
    # 收集要清理的 namespace
    if ($item.module) {
      $ns = [string]$item.command
      if ($ns -match '^(::[^:]+)') {
        $nsName = $matches[1]
        if ((-not (Test-HwAgentProperty -Object $item -Name "shortcut")) -and -not $registeredNamespaces.ContainsKey($nsName)) {
          $registeredNamespaces[$nsName] = $true
        }
      }
    }
    if ($item.show_in_cadence -ne $true) { continue }
    $name = Escape-TclMenuText (Get-HwAgentCadenceMenuName -Object $item)
    if (Test-HwAgentProperty -Object $item -Name "shortcut") {
      $name = Escape-TclMenuText ((Get-HwAgentCadenceMenuName -Object $item) + " (" + ([string]$item.shortcut) + ")")
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
  param(
    [Parameter(Mandatory=$true)][string]$ToolRoot,
    [string]$PluginStatePath
  )
  $lines = @()
  $statePath = Get-HwAgentPluginStatePath -ToolRoot $ToolRoot -PluginStatePath $PluginStatePath

  $items = @()
  $capabilitiesPath = Join-Path $ToolRoot "config\capabilities.json"
  if (Test-Path -LiteralPath $capabilitiesPath) {
    $data = Get-Content -LiteralPath $capabilitiesPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $items += @($data.capabilities)
  }

  $userPluginDir = Join-Path $ToolRoot "plugins\user"
  if (Test-Path -LiteralPath $userPluginDir) {
    foreach ($manifest in Get-ChildItem -LiteralPath $userPluginDir -Filter "*.json" -File -ErrorAction SilentlyContinue) {
      try {
        $plugin = Get-Content -LiteralPath $manifest.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
      } catch {
        continue
      }
      if ($plugin.type -eq "cadence_tcl" -and $plugin.script) {
        $plugin | Add-Member -NotePropertyName module -NotePropertyValue ("plugins/user/" + ([string]$plugin.script -replace "\\", "/")) -Force
      }
      $items += $plugin
    }
  }
  $items = @(Apply-HwAgentPluginStateOverrides -Items $items -Overrides (Get-HwAgentPluginStateOverrides -PluginStatePath $statePath))

  foreach ($item in @($items)) {
    if ($item.type -ne "cadence_tcl") { continue }
    if (-not (Test-HwAgentProperty -Object $item -Name "shortcut")) { continue }

    $itemId = Escape-TclMenuText ([string]$item.id)
    $module = ""
    if (Test-HwAgentProperty -Object $item -Name "module") {
      $module = Escape-TclPathLiteral ([string]$item.module)
    }
    $enabled = if ($item.show_in_cadence -eq $true) { "1" } else { "0" }
    $shortcutCommand = [string]$item.command
    if (Test-HwAgentProperty -Object $item -Name "shortcut_command") {
      $shortcutCommand = [string]$item.shortcut_command
    }
    $shortcutCommand = Escape-TclMenuText $shortcutCommand
    $lines += ('    ::IAC::SetShortcut "' + $itemId + '" ' + $enabled + ' "' + $shortcutCommand + '" "' + $module + '"')

    if ($module) {
      $lines += ('    source "$::IAC_ROOT/' + $module + '"')
    }
    $actionId = Escape-TclMenuText (Get-HwAgentShortcutActionId -Object $item)
    $shortcut = Escape-TclMenuText ([string]$item.shortcut)
    $shortcutContext = ""
    if (Test-HwAgentProperty -Object $item -Name "shortcut_context") {
      $shortcutContext = [string]$item.shortcut_context
    }
    $shortcutContext = Escape-TclMenuText $shortcutContext
    $lines += ('    if {[catch {RegisterAction "' + $actionId + '" "::IAC::ShortcutEnabled ' + $itemId + '" "' + $shortcut + '" "::IAC::RunShortcut ' + $itemId + '" "' + $shortcutContext + '"} err]} {')
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
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [string]$PluginStatePath
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
  $template = $template.Replace('{{TOOL_ROOT}}', $root)
  $template = $template.Replace('{{PYTHON_PATH}}', $python)
  $statePath = Get-HwAgentPluginStatePath -ToolRoot $ToolRoot -PluginStatePath $PluginStatePath
  $menuItems = Get-EnabledCadenceMenuItems -ToolRoot $ToolRoot -PluginStatePath $statePath
  $shortcutItems = Get-EnabledCadenceShortcutItems -ToolRoot $ToolRoot -PluginStatePath $statePath
  $template = $template -replace '(?m)^\s*# \{\{CADENCE_SCRIPT_MENU_ITEMS\}\}', $menuItems
  $template = $template -replace '(?m)^\s*# \{\{CADENCE_SCRIPT_SHORTCUT_ITEMS\}\}', $shortcutItems
  if ($template -match '\{\{[A-Z_]+\}\}') {
    throw ("Unrendered placeholder in Cadence loader: " + $Matches[0])
  }
  $template = $script:HwAgentCadenceLoaderMarker + "`r`n" + $template
  $encoding = [System.Text.Encoding]::GetEncoding(936)
  [System.IO.File]::WriteAllText($OutputPath, $template, $encoding)
  return $OutputPath
}

function Install-CadenceLoader {
  param(
    [Parameter(Mandatory=$true)][string]$ToolRoot,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string[]]$AutoLoadDirs,
    [string]$PluginStatePath
  )
  $installed = @()
  foreach ($dir in $AutoLoadDirs) {
    if (-not $dir) { continue }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $target = Join-Path $dir "iac_bom_tool.tcl"
    if (Test-Path -LiteralPath $target -PathType Leaf) {
      $owned = $false
      if (Get-Command Test-HwAgentOwnedCadenceLoader -ErrorAction SilentlyContinue) {
        $owned = Test-HwAgentOwnedCadenceLoader -LoaderPath $target
      } else {
        $existing = [System.IO.File]::ReadAllText($target)
        $owned = $existing.IndexOf($script:HwAgentCadenceLoaderMarker, [System.StringComparison]::Ordinal) -ge 0
      }
      if (-not $owned) {
        throw "Refusing to overwrite an unowned Cadence loader: $target"
      }
    }
    Write-CadenceLoader -ToolRoot $ToolRoot -PythonPath $PythonPath -OutputPath $target -PluginStatePath $PluginStatePath | Out-Null
    Write-Host ((Get-HwAgentText "5bey5a6J6KOFIENhZGVuY2Ug6I+c5Y2V6ISa5pys77ya") + $target)
    $installed += $target
  }
  return $installed
}

