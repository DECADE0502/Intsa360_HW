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

function Get-HwAgentUserPluginDir {
  param(
    [Parameter(Mandatory=$true)][string]$ToolRoot,
    [string]$PluginStatePath
  )
  $statePath = Get-HwAgentPluginStatePath -ToolRoot $ToolRoot -PluginStatePath $PluginStatePath
  $configDir = Split-Path -Parent ([System.IO.Path]::GetFullPath($statePath))
  $stateRoot = Split-Path -Parent $configDir
  return (Join-Path $stateRoot "plugins\user")
}

function Get-HwAgentCadenceUserPluginItems {
  param(
    [Parameter(Mandatory=$true)][string]$ToolRoot,
    [string]$PluginStatePath
  )
  $items = @()
  $userPluginDir = Get-HwAgentUserPluginDir -ToolRoot $ToolRoot -PluginStatePath $PluginStatePath
  if (-not (Test-Path -LiteralPath $userPluginDir -PathType Container)) {
    return $items
  }

  $pluginRoot = [System.IO.Path]::GetFullPath($userPluginDir).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
  $runtimeUserPluginDir = [System.IO.Path]::GetFullPath((Join-Path $ToolRoot "plugins\user")).TrimEnd('\', '/')
  $usesRuntimePluginDir = [string]::Equals(
    [System.IO.Path]::GetFullPath($userPluginDir).TrimEnd('\', '/'),
    $runtimeUserPluginDir,
    [System.StringComparison]::OrdinalIgnoreCase
  )
  foreach ($manifest in Get-ChildItem -LiteralPath $userPluginDir -Filter "*.json" -File -ErrorAction SilentlyContinue) {
    try {
      $plugin = Get-Content -LiteralPath $manifest.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
      if ($null -eq $plugin -or $plugin.type -ne "cadence_tcl" -or -not (Test-HwAgentProperty -Object $plugin -Name "script")) {
        continue
      }
      $scriptPath = [System.IO.Path]::GetFullPath((Join-Path $userPluginDir ([string]$plugin.script)))
      if (-not $scriptPath.StartsWith($pluginRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        continue
      }
      if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
        continue
      }
      if ($usesRuntimePluginDir) {
        $relativeScript = ([string]$plugin.script -replace "\\", "/")
        $plugin | Add-Member -NotePropertyName module -NotePropertyValue ("plugins/user/" + $relativeScript) -Force
      } else {
        $plugin | Add-Member -NotePropertyName module -NotePropertyValue (ConvertTo-TclPath $scriptPath) -Force
        $plugin | Add-Member -NotePropertyName module_absolute -NotePropertyValue $true -Force
      }
      $items += $plugin
    } catch {
      continue
    }
  }
  return $items
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

function Get-HwAgentCadenceItems {
  param(
    [Parameter(Mandatory=$true)][string]$ToolRoot,
    [string]$PluginStatePath
  )
  $statePath = Get-HwAgentPluginStatePath -ToolRoot $ToolRoot -PluginStatePath $PluginStatePath
  $items = @()
  $capabilitiesPath = Join-Path $ToolRoot "config\capabilities.json"
  if (Test-Path -LiteralPath $capabilitiesPath -PathType Leaf) {
    $data = Get-Content -LiteralPath $capabilitiesPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $items += @($data.capabilities)
  }
  $items += @(Get-HwAgentCadenceUserPluginItems -ToolRoot $ToolRoot -PluginStatePath $statePath)
  return @(Apply-HwAgentPluginStateOverrides -Items $items -Overrides (Get-HwAgentPluginStateOverrides -PluginStatePath $statePath))
}

function Get-HwAgentCadenceEntryScript {
  param([Parameter(Mandatory=$true)]$Object)
  if (Test-HwAgentProperty -Object $Object -Name "entry_script") {
    return [string]$Object.entry_script
  }
  if (Test-HwAgentProperty -Object $Object -Name "module") {
    return [string]$Object.module
  }
  return ""
}

function Get-HwAgentCadenceLoadPriority {
  param([Parameter(Mandatory=$true)]$Object)
  if ($null -ne $Object.PSObject.Properties["load_priority"]) {
    return [int]$Object.load_priority
  }
  return 100
}

function Get-HwAgentCadenceSourceLine {
  param(
    [Parameter(Mandatory=$true)]$Object,
    [Parameter(Mandatory=$true)][string]$Indent
  )
  $entryScript = Get-HwAgentCadenceEntryScript -Object $Object
  if ([string]::IsNullOrWhiteSpace($entryScript)) { return "" }
  $entryScript = Escape-TclPathLiteral $entryScript
  if ((Test-HwAgentProperty -Object $Object -Name "module_absolute") -and $Object.module_absolute -eq $true) {
    return ($Indent + '::IAC::SourceModuleOnce "' + $entryScript + '"')
  }
  return ($Indent + '::IAC::SourceModuleOnce "$::IAC_ROOT/' + $entryScript + '"')
}

function Get-HwAgentCadenceLifecycleLines {
  param(
    [Parameter(Mandatory=$true)]$Object,
    [Parameter(Mandatory=$true)][string]$Indent
  )
  if (-not (Test-HwAgentProperty -Object $Object -Name "activate_command") -or
      -not (Test-HwAgentProperty -Object $Object -Name "deactivate_command")) {
    return @()
  }
  $itemId = Escape-TclMenuText ([string]$Object.id)
  $activate = Escape-TclMenuText ([string]$Object.activate_command)
  $deactivate = Escape-TclMenuText ([string]$Object.deactivate_command)
  return @(
    ($Indent + '::IAC::RegisterPluginLifecycle "' + $itemId + '" "' + $activate + '" "' + $deactivate + '"'),
    ($Indent + '::IAC::ActivatePlugin ' + $itemId)
  )
}

function Get-EnabledCadenceMenuItems {
  param(
    [Parameter(Mandatory=$true)][string]$ToolRoot,
    [string]$PluginStatePath
  )
  $lines = @()
  $items = @(Get-HwAgentCadenceItems -ToolRoot $ToolRoot -PluginStatePath $PluginStatePath)
  $enabledItems = @($items | Where-Object { $_.type -eq "cadence_tcl" -and $_.show_in_cadence -eq $true })
  $menuLoadItems = @(
    $enabledItems |
      Where-Object { -not (Test-HwAgentProperty -Object $_ -Name "shortcut") } |
      Sort-Object @{ Expression = { Get-HwAgentCadenceLoadPriority -Object $_ } }, @{ Expression = { [string]$_.id } }
  )

  # Load every enabled entry first so shared implementation ordering is deterministic.
  foreach ($item in $menuLoadItems) {
    $sourceLine = Get-HwAgentCadenceSourceLine -Object $item -Indent "        "
    if ($sourceLine) { $lines += $sourceLine }
  }
  foreach ($item in $menuLoadItems) {
    $lines += @(Get-HwAgentCadenceLifecycleLines -Object $item -Indent "        ")
  }

  # Preserve capability order for the visible menu.
  foreach ($item in $enabledItems) {
    $name = Escape-TclMenuText (Get-HwAgentCadenceMenuName -Object $item)
    if (Test-HwAgentProperty -Object $item -Name "shortcut") {
      $name = Escape-TclMenuText ((Get-HwAgentCadenceMenuName -Object $item) + " (" + ([string]$item.shortcut) + ")")
    }
    $command = Escape-TclMenuText ([string]$item.command)
    $lines += ('        AddAccessoryMenu "insta360_HW" "' + $name + '" "' + $command + '"')
  }
  return ($lines -join "`r`n")
}

function Get-EnabledCadenceShortcutItems {
  param(
    [Parameter(Mandatory=$true)][string]$ToolRoot,
    [string]$PluginStatePath
  )
  $lines = @()
  $items = @(Get-HwAgentCadenceItems -ToolRoot $ToolRoot -PluginStatePath $PluginStatePath)

  foreach ($item in @($items)) {
    if ($item.type -ne "cadence_tcl") { continue }
    if (-not (Test-HwAgentProperty -Object $item -Name "shortcut")) { continue }

    $itemId = Escape-TclMenuText ([string]$item.id)
    $module = ""
    $module = Escape-TclPathLiteral (Get-HwAgentCadenceEntryScript -Object $item)
    $enabled = if ($item.show_in_cadence -eq $true) { "1" } else { "0" }
    $shortcutCommand = [string]$item.command
    if (Test-HwAgentProperty -Object $item -Name "shortcut_command") {
      $shortcutCommand = [string]$item.shortcut_command
    }
    $shortcutCommand = Escape-TclMenuText $shortcutCommand
    $lines += ('    ::IAC::SetShortcut "' + $itemId + '" ' + $enabled + ' "' + $shortcutCommand + '" "' + $module + '"')

    if ($item.show_in_cadence -eq $true) {
      $sourceLine = Get-HwAgentCadenceSourceLine -Object $item -Indent "    "
      if ($sourceLine) { $lines += $sourceLine }
      $lines += @(Get-HwAgentCadenceLifecycleLines -Object $item -Indent "    ")
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
    $temporary = Join-Path $dir (".iac_bom_tool." + [guid]::NewGuid().ToString("N") + ".tmp")
    try {
      Write-CadenceLoader -ToolRoot $ToolRoot -PythonPath $PythonPath -OutputPath $temporary -PluginStatePath $PluginStatePath | Out-Null
      $unchanged = $false
      if (Test-Path -LiteralPath $target -PathType Leaf) {
        try {
          $currentHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
          $candidateHash = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash
          $unchanged = $currentHash -eq $candidateHash
        } catch { $unchanged = $false }
      }
      if (-not $unchanged) {
        Move-Item -LiteralPath $temporary -Destination $target -Force
      }
    } finally {
      Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
    Write-Host ((Get-HwAgentText "5bey5a6J6KOFIENhZGVuY2Ug6I+c5Y2V6ISa5pys77ya") + $target)
    $installed += $target
  }
  return $installed
}

