# insta360_HW - Capture integration (GBK, no BOM)
set ::IAC_ROOT "{{TOOL_ROOT}}"
if {[string match "*\{\{*\}\}*" $::IAC_ROOT]} {
    puts "iac_bom_tool.tcl: unrendered template, aborting. Use install.ps1 to render."
    return
}
set ::IAC_JUMP "$::IAC_ROOT/iac_jump.bat"
set ::IAC_PY   "{{PYTHON_PATH}}"
if {[string match "*\{\{*\}\}*" $::IAC_PY]} { set ::IAC_PY "python" }
set ::IAC_CNV  "$::IAC_ROOT/tools/bom/convert_cadence_bom.py"
set ::IAC_STATE_ROOT $::IAC_ROOT
if {[info exists ::env(INSTA360_HW_STATE_ROOT)] && $::env(INSTA360_HW_STATE_ROOT) ne ""} {
    set ::IAC_STATE_ROOT [file normalize $::env(INSTA360_HW_STATE_ROOT)]
} elseif {[file exists "$::IAC_ROOT/install_manifest.json"] && [info exists ::env(LOCALAPPDATA)] && $::env(LOCALAPPDATA) ne ""} {
    set ::IAC_STATE_ROOT [file normalize [file join $::env(LOCALAPPDATA) "Insta360_HW"]]
}

namespace eval ::IAC {
    variable SHORTCUTS
    if {![array exists SHORTCUTS]} { array set SHORTCUTS {} }
    variable LOADED_MODULES
    if {![array exists LOADED_MODULES]} { array set LOADED_MODULES {} }
    variable PLUGIN_LIFECYCLE
    if {![array exists PLUGIN_LIFECYCLE]} { array set PLUGIN_LIFECYCLE {} }
    variable EXPORT_SEQUENCE 0
    variable PROP_NAMES {
        "Color" "Designator" "Graphic ID" "Implementation" "Implementation Path" "Implementation Type"
        "Location X-Coordinate" "Location Y-Coordinate" "Name" "Part Number" "Part Reference" "Part Type"
        "PCB Footprint" "PCB\u5c01\u88c5" "Power Pins Visible" "Primitive" "Reference" "Source Library" "Source Package"
        "Source Part" "SPLIT_INST" "SWAP_INFO" "Value" "\u7b49\u7ea7" "\u89c4\u683c\u578b\u53f7"
        "\u5668\u4ef6\u63cf\u8ff0\uff08\u65b0\u6574\u7406\uff09" "\u7269\u6599\u540d\u79f0" "\u5185\u5bb9" "Description"
        "\u7269\u6599\u4f18\u9009\u7b49\u7ea7" "Manufacturer" "\u5236\u9020\u5546" "Datasheet" "datasheet"
        "\u7533\u8bf7\u4eba" "\u65f6\u95f4" "Implementation Designator"
    }

    proc shouldProcess { args } { return 1 }
    proc updatePro { args } { return true }
    proc log { msg } { catch { DboState_WriteToSessionLog [DboTclHelper_sMakeCString $msg] }; catch { puts $msg } }
    proc SetShortcut { id enabled command module } {
        variable SHORTCUTS
        set SHORTCUTS($id,enabled) $enabled
        set SHORTCUTS($id,command) $command
        set SHORTCUTS($id,module) $module
    }
    proc SourceModule { module } {
        if {[file pathtype $module] eq "absolute"} {
            set path $module
        } else {
            set path "$::IAC_ROOT/$module"
        }
        return [uplevel #0 [list source $path]]
    }
    proc SourceModuleOnce { module } {
        variable LOADED_MODULES
        if {[file pathtype $module] eq "absolute"} {
            set path [file normalize $module]
        } else {
            set path [file normalize "$::IAC_ROOT/$module"]
        }
        if {[info exists LOADED_MODULES($path)]} { return 0 }
        uplevel #0 [list source $path]
        set LOADED_MODULES($path) 1
        return 1
    }
    proc RegisterPluginLifecycle { id {activate ""} {deactivate ""} } {
        variable PLUGIN_LIFECYCLE
        if {$activate eq ""} { set activate "::IACPluginRuntime::activate $id" }
        if {$deactivate eq ""} { set deactivate "::IACPluginRuntime::deactivate $id" }
        set PLUGIN_LIFECYCLE($id,activate) $activate
        set PLUGIN_LIFECYCLE($id,deactivate) $deactivate
        return 1
    }
    proc ActivatePlugin { id } {
        variable PLUGIN_LIFECYCLE
        if {![info exists PLUGIN_LIFECYCLE($id,activate)]} { return 0 }
        return [uplevel #0 $PLUGIN_LIFECYCLE($id,activate)]
    }
    proc DeactivatePlugin { id } {
        variable PLUGIN_LIFECYCLE
        if {![info exists PLUGIN_LIFECYCLE($id,deactivate)]} { return 0 }
        return [uplevel #0 $PLUGIN_LIFECYCLE($id,deactivate)]
    }
    proc BeginPluginReload {} {
        variable SHORTCUTS
        variable LOADED_MODULES
        variable PLUGIN_LIFECYCLE
        set ids {}
        foreach key [array names PLUGIN_LIFECYCLE "*,deactivate"] {
            lappend ids [string range $key 0 end-[string length ",deactivate"]]
        }
        foreach id [lsort -unique $ids] {
            if {[catch {::IAC::DeactivatePlugin $id} err]} {
                ::IAC::log "IAC: plugin deactivation failed: $id $err"
            }
        }
        array unset SHORTCUTS
        array set SHORTCUTS {}
        array unset LOADED_MODULES
        array set LOADED_MODULES {}
        array unset PLUGIN_LIFECYCLE
        array set PLUGIN_LIFECYCLE {}
        return 1
    }
    proc ShortcutEnabled { id args } {
        variable SHORTCUTS
        if {![info exists SHORTCUTS($id,enabled)] || !$SHORTCUTS($id,enabled)} { return 0 }
        set command $SHORTCUTS($id,command)
        set commandName [lindex $command 0]
        if {[info procs $commandName] eq "" && [info commands $commandName] eq ""} {
            set module $SHORTCUTS($id,module)
            if {$module ne ""} { catch {::IAC::SourceModuleOnce $module} }
        }
        if {[info procs $commandName] eq "" && [info commands $commandName] eq ""} { return 0 }
        return 1
    }
    proc RunShortcut { id args } {
        variable SHORTCUTS
        if {![::IAC::ShortcutEnabled $id]} {
            ::IAC::log "IAC: shortcut disabled or unavailable: $id"
            return 0
        }
        set command $SHORTCUTS($id,command)
        if {[catch {uplevel #0 $command} err]} {
            ::IAC::log "IAC: shortcut failed: $id $err"
            catch {tk_messageBox -icon error -type ok -title "insta360_HW" -message $err}
            return 0
        }
        return 1
    }
    proc Probe { phase } {
        catch {
            set logDir [file normalize "$::IAC_STATE_ROOT/data/reports/runtime"]
            file mkdir $logDir
            set fh [open [file join $logDir "cadence_loader_probe.log"] a]
            fconfigure $fh -encoding utf-8
            puts $fh "IAC: loader probe phase=$phase root=$::IAC_ROOT RegisterAction=[expr {[llength [info commands RegisterAction]] > 0 ? "available" : "missing"}] InsertXMLMenu=[expr {[llength [info commands InsertXMLMenu]] > 0 ? "available" : "missing"}] AddAccessoryMenu=[expr {[llength [info commands AddAccessoryMenu]] > 0 ? "available" : "missing"}]"
            close $fh
        }
    }

    # ---- \u542f\u52a8\u5de5\u5177 ----
    proc launch { {source ""} {name ""} } {
        set vbs "$::IAC_ROOT/launch_tool_suite_hidden.vbs"
        set ps1 "$::IAC_ROOT/launch_tool_suite.ps1"
        if {$source ne "" && $name ne ""} {
            set rc [catch {exec wscript.exe $vbs $ps1 -Source $source -Name $name &} err]
        } elseif {$source ne ""} {
            set rc [catch {exec wscript.exe $vbs $ps1 -Source $source &} err]
        } elseif {$name ne ""} {
            set rc [catch {exec wscript.exe $vbs $ps1 -Name $name &} err]
        } else {
            set rc [catch {exec wscript.exe $vbs $ps1 &} err]
        }
        if {$rc} { ::IAC::log "IAC: launch FAILED: $err" }
    }
    proc OpenTool { args } { ::IAC::launch }

    proc Diagnose { args } {
        ::IAC::log "IAC: diagnostics"
        ::IAC::log "IAC: IAC_ROOT = $::IAC_ROOT"
        ::IAC::log "IAC: IAC_PY = $::IAC_PY"
        ::IAC::log "IAC: launcher = $::IAC_ROOT/launch_tool_suite_hidden.vbs"
        ::IAC::log "IAC: converter = $::IAC_CNV"
        ::IAC::log "IAC: launcher exists = [file exists "$::IAC_ROOT/launch_tool_suite_hidden.vbs"]"
        ::IAC::log "IAC: powershell launcher exists = [file exists "$::IAC_ROOT/launch_tool_suite.ps1"]"
        ::IAC::log "IAC: converter exists = [file exists $::IAC_CNV]"
        ::IAC::log "IAC: RegisterAction command = [expr {[llength [info commands RegisterAction]] > 0 ? "available" : "missing"}]"
        ::IAC::log "IAC: InsertXMLMenu command = [expr {[llength [info commands InsertXMLMenu]] > 0 ? "available" : "missing"}]"
        ::IAC::log "IAC: AddAccessoryMenu command = [expr {[llength [info commands AddAccessoryMenu]] > 0 ? "available" : "missing"}]"
        ::IAC::log "IAC: try 'iac' to open platform, 'iacx' to export and process BOM"
    }

    # ---- \u4ece\u8bbe\u8ba1\u8bfb\u5668\u4ef6 ----
    proc ReadParts { } {
        set parts [list]
        catch {
            set lStatus [DboState]
            set pDesign [GetActivePMDesign]
            set lRootOcc [$pDesign GetRootOccurrence $lStatus]
            ::IAC::IterParts $pDesign $lRootOcc parts
            $lStatus -delete
        }
        return $parts
    }
    proc IterParts { pDesign lInstOcc partsVar } {
        upvar $partsVar parts
        set lStatus [DboState]
        set lIter [$lInstOcc NewChildrenIter $lStatus $::IterDefs_INSTS]
        $lIter Sort $lStatus
        set lChild [$lIter NextOccurrence $lStatus]
        set lNullObj NULL
        while { $lChild != $lNullObj } {
            set lInstOcc [DboOccurrenceToDboInstOccurrence $lChild]
            set isPrimitive 0
            catch { set isPrimitive [$lInstOcc IsPrimitive $lStatus] }
            if {$isPrimitive == 1} {
                set row [::IAC::ReadProps $pDesign $lInstOcc]
                if {[::IAC::RowExists $row Reference] && [::IAC::RowGet $row Reference] ne ""} { lappend parts $row }
            }
            ::IAC::IterParts $pDesign $lInstOcc parts
            set lChild [$lIter NextOccurrence $lStatus]
        }
        delete_DboOccurrenceChildrenIter $lIter
        $lStatus -delete
    }

    proc GetReference { lInstOcc } {
        set ret ""
        catch {
            set lName [DboTclHelper_sMakeCString]
            set lStatus [$lInstOcc GetReference $lName]
            set ret [DboTclHelper_sGetConstCharPtr $lName]
            catch {$lStatus -delete}
            catch {$lName -delete}
        }
        return $ret
    }

    proc GetPropValue { pDesign lInstOcc propName } {
        set lNullObj NULL
        set ret ""
        catch {
            set lPropName [DboTclHelper_sMakeCString $propName]
            set lPropValue [DboTclHelper_sMakeCString]
            set lStatus [DboState]
            set lPartInst [$lInstOcc GetPartInst $lStatus]
            set variantKind 0
            if {[$lInstOcc IsVariantPropMapEmpty] == 0} {
                set variantKind 1
            } elseif {$lPartInst != $lNullObj && [$lPartInst IsVariantPropMapEmpty] == 0} {
                set variantKind 2
            }

            if {$variantKind == 1} {
                if {[$lInstOcc GetVariantProp $lPropName $lPropValue] == 1} {
                    set val [DboTclHelper_sGetConstCharPtr $lPropValue]
                    set ns [DboTclHelper_sGetConstCharPtr [$pDesign GetCISNotStuffedString]]
                    if {$val ne $ns} { set ret $val }
                }
            } elseif {$variantKind == 2} {
                if {[$lPartInst GetVariantProp $lPropName $lPropValue] == 1} {
                    set val [DboTclHelper_sGetConstCharPtr $lPropValue]
                    set ns [DboTclHelper_sGetConstCharPtr [$pDesign GetCISNotStuffedString]]
                    if {$val ne $ns} { set ret $val }
                }
            } else {
                set lStatus2 [$lInstOcc GetEffectivePropStringValue $lPropName $lPropValue]
                if {[$lStatus2 OK] == 1} { set ret [DboTclHelper_sGetConstCharPtr $lPropValue] }
                catch {$lStatus2 -delete}
            }
            catch {$lStatus -delete}
            catch {$lPropName -delete}
            catch {$lPropValue -delete}
        }
        return $ret
    }

    proc RowSet { rowVar key value } {
        upvar $rowVar row
        set next [list]
        set found 0
        foreach {k v} $row {
            if {$k eq $key} {
                lappend next $k $value
                set found 1
            } else {
                lappend next $k $v
            }
        }
        if {!$found} { lappend next $key $value }
        set row $next
    }
    proc RowGet { row key } {
        foreach {k v} $row {
            if {$k eq $key} { return $v }
        }
        return ""
    }
    proc RowExists { row key } {
        foreach {k v} $row {
            if {$k eq $key} { return 1 }
        }
        return 0
    }
    proc RowKeys { row } {
        set keys [list]
        foreach {k v} $row { lappend keys $k }
        return $keys
    }

    proc ReadProps { pDesign lInstOcc } {
        set row [list]
        catch {
            set lStatus [DboState]
            set lIter [$lInstOcc NewEffectivePropsIter $lStatus]
            set lName [DboTclHelper_sMakeCString]
            set lValue [DboTclHelper_sMakeCString]
            set lType [DboTclHelper_sMakeDboValueType]
            set lEdit [DboTclHelper_sMakeInt]
            set lStatus [$lIter NextEffectiveProp $lName $lValue $lType $lEdit]
            while {[$lStatus OK] == 1} {
                set key [DboTclHelper_sGetConstCharPtr $lName]
                set val [DboTclHelper_sGetConstCharPtr $lValue]
                if {$key ne ""} { ::IAC::RowSet row $key $val }
                set lStatus [$lIter NextEffectiveProp $lName $lValue $lType $lEdit]
            }
            delete_DboEffectivePropsIter $lIter
            $lStatus -delete
        }

        set ref [::IAC::GetReference $lInstOcc]
        if {$ref ne ""} { ::IAC::RowSet row Reference $ref }

        foreach prop $::IAC::PROP_NAMES {
            if {$prop eq "Reference"} { continue }
            set val [::IAC::GetPropValue $pDesign $lInstOcc $prop]
            if {$val ne ""} { ::IAC::RowSet row $prop $val }
        }
        return $row
    }

    proc DisplayDsnName { value } {
        set name [string trim $value]
        if {$name eq ""} { return "" }
        set tail [file tail $name]
        if {$tail ne ""} { set name $tail }
        set root [file rootname $name]
        if {$root ne ""} { set name $root }
        return $name
    }
    proc CleanDesignName { value } {
        set name [::IAC::DisplayDsnName $value]
        if {$name eq ""} { return "" }
        regsub -all {[\\/:*?"<>|]} $name "_" name
        return $name
    }
    proc GetDsnName { } {
        set ret ""
        catch {
            set lStatus [DboState]
            set pDesign [GetActivePMDesign]
            set lNullObj NULL
            if {$pDesign != $lNullObj} {
                set lPropsIter [$pDesign NewEffectivePropsIter $lStatus]
                set lPrpName [DboTclHelper_sMakeCString]
                set lPrpValue [DboTclHelper_sMakeCString]
                set lPrpType [DboTclHelper_sMakeDboValueType]
                set lEditable [DboTclHelper_sMakeInt]
                set lStatus [$lPropsIter NextEffectiveProp $lPrpName $lPrpValue $lPrpType $lEditable]
                while {[$lStatus OK] == 1} {
                    set propname [DboTclHelper_sGetConstCharPtr $lPrpName]
                    if {$propname eq "Name"} {
                        set ret [DboTclHelper_sGetConstCharPtr $lPrpValue]
                        break
                    }
                    set lStatus [$lPropsIter NextEffectiveProp $lPrpName $lPrpValue $lPrpType $lEditable]
                }
                catch {delete_DboEffectivePropsIter $lPropsIter}
            }
            catch {$lStatus -delete}
        }
        if {$ret eq ""} {
            catch {
                set p [GetActivePMDesign]
                set n [DboTclHelper_sMakeCString]
                set s [DboState]
                $p GetName $n
                set ret [DboTclHelper_sGetConstCharPtr $n]
                $n -delete
                $s -delete
            }
        }
        return [::IAC::DisplayDsnName $ret]
    }
    proc JsonEscape { value } {
        return [string map [list "\\" "\\\\" "\"" "\\\"" "\n" "\\n" "\r" "\\r" "\t" "\\t"] $value]
    }
    proc PartsToJson { parts } {
        set lines [list "\["]; set first 1
        foreach row $parts {
            if {!$first} { lappend lines "," } else { set first 0 }
            set kv [list]
            foreach key [::IAC::RowKeys $row] {
                if {[::IAC::RowExists $row $key]} {
                    lappend kv "\"[::IAC::JsonEscape $key]\":\"[::IAC::JsonEscape [::IAC::RowGet $row $key]]\""
                }
            }
            lappend lines "\{[join $kv ,]\}"
        }
        lappend lines "\]"; return [join $lines "\n"]
    }

    # ---- \u5bfc\u51fa + \u5904\u7406 ----
    proc CreateExportJob { dsn } {
        variable EXPORT_SEQUENCE
        set safeDsn [::IAC::CleanDesignName $dsn]
        if {$safeDsn eq ""} { set safeDsn "BOM" }
        set jobRoot [file normalize "$::IAC_STATE_ROOT/data/jobs"]
        if {[catch {file mkdir $jobRoot} err]} {
            return -code error "Cannot create BOM export job root $jobRoot: $err"
        }
        set stamp [clock seconds]
        set processId [pid]
        set sequence [incr EXPORT_SEQUENCE]
        set jobName "${safeDsn}-${stamp}-${processId}-${sequence}"
        set jobDir [file normalize [file join $jobRoot $jobName]]
        if {[file exists $jobDir]} {
            return -code error "BOM export job directory already exists: $jobDir"
        }
        if {[catch {file mkdir $jobDir} err]} {
            return -code error "Cannot create BOM export job directory $jobDir: $err"
        }
        if {![file isdirectory $jobDir]} {
            return -code error "BOM export job directory is unavailable: $jobDir"
        }
        set jsonPath [file join $jobDir "parts.json"]
        set xlsxPath [file join $jobDir "bom.xlsx"]
        return [list $jobDir $jsonPath $xlsxPath]
    }
    proc ReportExportFailure { jobDir message } {
        set detail "IAC: BOM export failed for job $jobDir: $message"
        ::IAC::log $detail
        catch {tk_messageBox -icon error -type ok -title "insta360_HW BOM Export" -message $detail}
        return 0
    }
    proc ExportAndProcess { args } {
        set dsn [::IAC::GetDsnName]
        if {$dsn eq ""} { set dsn "BOM" }
        if {[catch {set job [::IAC::CreateExportJob $dsn]} err]} {
            return [::IAC::ReportExportFailure "<unavailable>" $err]
        }
        set jobDir [lindex $job 0]
        set jsonPath [lindex $job 1]
        set xlsxPath [lindex $job 2]
        ::IAC::log "IAC: ExportAndProcess design name = $dsn job = $jobDir"

        if {![file exists $::IAC_CNV]} {
            return [::IAC::ReportExportFailure $jobDir "BOM converter is missing: $::IAC_CNV"]
        }
        set parts [::IAC::ReadParts]
        ::IAC::log "IAC: ReadParts count = [llength $parts] job = $jobDir"
        if {[llength $parts] == 0} {
            return [::IAC::ReportExportFailure $jobDir "No BOM parts were read from the active Capture design"]
        }

        set jsonHandle ""
        if {[catch {
            set jsonHandle [open $jsonPath w]
            fconfigure $jsonHandle -encoding utf-8
            puts $jsonHandle [::IAC::PartsToJson $parts]
            close $jsonHandle
            set jsonHandle ""
        } err]} {
            if {$jsonHandle ne ""} { catch {close $jsonHandle} }
            return [::IAC::ReportExportFailure $jobDir "Cannot write job JSON: $err"]
        }
        if {[catch {exec $::IAC_PY $::IAC_CNV $jsonPath $xlsxPath} err]} {
            return [::IAC::ReportExportFailure $jobDir "BOM conversion failed: $err"]
        }
        if {![file exists $xlsxPath] || [file size $xlsxPath] <= 100} {
            return [::IAC::ReportExportFailure $jobDir "BOM conversion did not produce a valid workbook"]
        }
        ::IAC::launch $xlsxPath $dsn
        return 1
    }
}

::IAC::BeginPluginReload

# ---- \u5168\u5c40\u547d\u4ee4 ----
proc iac  {} { ::IAC::launch }
proc iacx {} { ::IAC::ExportAndProcess }
proc iacdiag {} { ::IAC::Diagnose }

# ---- \u83dc\u5355 ----
if {[catch {
    RegisterAction "iacOpen"   "::IAC::shouldProcess" "" "::IAC::OpenTool" ""
    RegisterAction "iacExport" "::IAC::shouldProcess" "" "::IAC::ExportAndProcess" ""
    RegisterAction "iacUpd"    "::IAC::shouldProcess" "" "::IAC::updatePro"    ""
    # {{CADENCE_SCRIPT_SHORTCUT_ITEMS}}
    InsertXMLMenu [list [list "insta360_HW"] "" "" [list "popup" "insta360_HW" "" "" "" "" ""] ""]
    InsertXMLMenu [list [list "insta360_HW" "Open"]   "" "" [list "action" "Open Platform" "0" "iacOpen"   "iacUpd" "" "Open Insta360 hardware platform"] ""]
    InsertXMLMenu [list [list "insta360_HW" "Export"] "" "" [list "action" "Export and Process BOM" "0" "iacExport" "iacUpd" "" "Export Capture BOM and open processing wizard"] ""]
} err]} {
    ::IAC::log "IAC: top menu registration failed: $err"
}
if {[catch {
    proc ::IAC::addAccessoryMenu { args } {
        # {{CADENCE_SCRIPT_MENU_ITEMS}}
    }
    RegisterAction "_cdnCapTclAddDesignCustomMenu" "::IAC::shouldProcess" "" "::IAC::addAccessoryMenu" ""
} err]} {
    ::IAC::log "IAC: accessory menu registration failed: $err"
}
catch { ::IAC::Probe "menu_registered" }
puts "IAC: insta360_HW loaded"
