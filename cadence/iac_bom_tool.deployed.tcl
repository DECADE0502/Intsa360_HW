# insta360_HW - Capture integration (GBK, no BOM)
set ::IAC_ROOT "D:/desktop/工具集/insta360_HWagent"
set ::IAC_JUMP "$::IAC_ROOT/iac_jump.bat"
set ::IAC_PY   "C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
set ::IAC_CNV  "$::IAC_ROOT/tools/bom/convert_cadence_bom.py"

namespace eval ::IAC {
    variable PROP_NAMES {
        Color Designator Graphic ID Implementation {Implementation Path} {Implementation Type}
        {Location X-Coordinate} {Location Y-Coordinate} Name {Part Number} {Part Reference}
        {Part Type} {PCB Footprint} {PCB封装} {Power Pins Visible} Primitive Reference
        {Source Library} {Source Package} {Source Part} SPLIT_INST SWAP_INFO Value
        {等级} {规格型号} {器件描述（新整理）} {物料名称}
        {内容} Description {物料优选等级} Manufacturer {制造商} Datasheet datasheet
        {申请人} {时间} {Implementation Designator}
    }

    proc shouldProcess { args } { return 1 }
    proc updatePro { args } { return true }
    proc log { msg } { catch { DboState_WriteToSessionLog [DboTclHelper_sMakeCString $msg] }; catch { puts $msg } }

    # ---- 启动工具 ----
    proc launch { {source ""} {name ""} } {
        set cmd [list wscript.exe "$::IAC_ROOT/launch_tool_suite_hidden.vbs" "$::IAC_ROOT/launch_tool_suite.ps1"]
        if {$source ne ""} { lappend cmd -Source $source }
        if {$name   ne ""} { lappend cmd -Name $name }
        if {[catch {exec {*}$cmd &} err]} { ::IAC::log "IAC: launch FAILED: $err" }
    }
    proc OpenTool { args } { ::IAC::launch }

    # ---- 从设计读器件 ----
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
                if {[dict exists $row Reference] && [dict get $row Reference] ne ""} { lappend parts $row }
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

    proc ReadProps { pDesign lInstOcc } {
        set row [dict create]
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
                if {$key ne ""} { dict set row $key $val }
                set lStatus [$lIter NextEffectiveProp $lName $lValue $lType $lEdit]
            }
            delete_DboEffectivePropsIter $lIter
            $lStatus -delete
        }

        set ref [::IAC::GetReference $lInstOcc]
        if {$ref ne ""} { dict set row Reference $ref }

        foreach prop $::IAC::PROP_NAMES {
            if {$prop eq "Reference"} { continue }
            set val [::IAC::GetPropValue $pDesign $lInstOcc $prop]
            if {$val ne ""} { dict set row $prop $val }
        }
        return $row
    }

    proc CleanDesignName { value } {
        set name [string trim $value]
        if {$name eq ""} { return "" }
        set tail [file tail $name]
        if {$tail ne ""} { set name $tail }
        set root [file rootname $name]
        if {$root ne ""} { set name $root }
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
        return [::IAC::CleanDesignName $ret]
    }
    proc JsonEscape { value } {
        return [string map [list "\\" "\\\\" "\"" "\\\"" "\n" "\\n" "\r" "\\r" "\t" "\\t"] $value]
    }
    proc PartsToJson { parts } {
        set lines [list "\["]; set first 1
        foreach row $parts {
            if {!$first} { lappend lines "," } else { set first 0 }
            set kv [list]
            foreach key [dict keys $row] {
                if {[dict exists $row $key]} {
                    lappend kv "\"[::IAC::JsonEscape $key]\":\"[::IAC::JsonEscape [dict get $row $key]]\""
                }
            }
            lappend lines "\{[join $kv ,]\}"
        }
        lappend lines "\]"; return [join $lines "\n"]
    }

    # ---- 导出 + 处理 ----
    proc ExportAndProcess { args } {
        set dsnRaw [::IAC::GetDsnName]
        set dsn [::IAC::CleanDesignName $dsnRaw]
        if {$dsn eq ""} { set dsn "BOM" }
        ::IAC::log "IAC: ExportAndProcess design name = $dsn"
        set inbox [file normalize "$::IAC_ROOT/data/inbox/${dsn}.xlsx"]
        catch { file mkdir [file dirname $inbox] }
        set exported 0

        # 1) Tcl 读取设计 → JSON → Python 转 xlsx
        if {[file exists $::IAC_CNV]} { catch {
            set parts [::IAC::ReadParts]
            ::IAC::log "IAC: ReadParts count = [llength $parts]"
            if {[llength $parts] > 0} {
                set jf [file normalize "$::IAC_ROOT/data/inbox/_bom_data.json"]
                set fh [open $jf w]; fconfigure $fh -encoding utf-8; puts $fh [::IAC::PartsToJson $parts]; close $fh
                exec $::IAC_PY "$::IAC_CNV" "$jf" "$inbox"
                if {[file exists $inbox] && [file size $inbox] > 100} { set exported 1 }
            }
        }}

        # 2) cadence_export.ps1
        if {!$exported} {
            set exp "$::IAC_ROOT/cadence/cadence_export.ps1"
            if {[file exists $exp]} { catch {
                exec cmd /c start /wait "" cmd /c "powershell -NoProfile -EP Bypass -File \"$exp\" -Out \"$inbox\""
                if {[file exists $inbox] && [file size $inbox] > 100} { set exported 1 }
            }}
        }

        # 3) 复用已有 xlsx
        if {!$exported} {
            foreach f [glob -nocomplain "$::IAC_ROOT/data/inbox/*.xlsx"] {
                if {[file exists $f] && [file size $f] > 100 && $f ne $inbox} { set inbox $f; set exported 1; break }
            }
        }

        set src [expr {$exported && [file exists $inbox] && [file size $inbox] > 100 ? $inbox : ""}]
        ::IAC::launch $src $dsn
    }
}

# ---- 全局命令 ----
proc iac  {} { ::IAC::launch }
proc iacx {} { ::IAC::ExportAndProcess }

# ---- 菜单 ----
catch {
    RegisterAction "iacOpen"   "::IAC::shouldProcess" "" "::IAC::OpenTool" ""
    RegisterAction "iacExport" "::IAC::shouldProcess" "" "::IAC::ExportAndProcess" ""
    RegisterAction "iacUpd"    "::IAC::shouldProcess" "" "::IAC::updatePro"    ""
    InsertXMLMenu [list [list "IACBOM"] "" "" [list "popup" "insta360_HW" "" "" "" "" ""] ""]
    InsertXMLMenu [list [list "IACBOM" "Open"]   "" "" [list "action" "Open Tool Suite" "0" "iacOpen"   "iacUpd" "" "Open hardware tool suite"] ""]
    InsertXMLMenu [list [list "IACBOM" "Export"] "" "" [list "action" "Export and Process BOM" "0" "iacExport" "iacUpd" "" "Export Capture BOM and open processing wizard"] ""]
}
catch {
    proc ::IAC::addAccessoryMenu { args } {
        AddAccessoryMenu "insta360_HW" "进入平台" "::IAC::OpenTool"
        AddAccessoryMenu "insta360_HW" "导出并处理BOM" "::IAC::ExportAndProcess"

    }
    RegisterAction "_cdnCapTclAddDesignCustomMenu" "::IAC::shouldProcess" "" "::IAC::addAccessoryMenu" ""
}
puts "IAC: insta360_HW loaded"

