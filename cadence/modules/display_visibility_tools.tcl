# insta360_HW module: show or hide part Value and U-part pin names.

namespace eval ::capMenuUtil {}

proc ::capMenuUtil::visibilityActiveDesignOrWarn {} {
    set design ""
    catch {set design [GetActivePMDesign]}
    if {$design eq "NULL" || $design eq ""} {
        catch {tk_messageBox -icon error -message "未找到当前打开的设计。"}
        return "NULL"
    }
    return $design
}

proc ::capMenuUtil::visibilityConfirm {message} {
    set confirm "no"
    catch {set confirm [tk_messageBox -icon question -message $message -type yesno]}
    return [expr {$confirm eq "yes"}]
}

proc ::capMenuUtil::visibilityEachPart {callback} {
    set lStatus [DboState]
    set lDesign [::capMenuUtil::visibilityActiveDesignOrWarn]
    if {$lDesign eq "NULL"} { return }

    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }

    set lNullObj NULL
    set lView [$lSchematicIter NextView $lStatus]
    while {$lView != $lNullObj} {
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]
        while {$lPage != $lNullObj} {
            set lPartInstsIter [$lPage NewPartInstsIter $lStatus]
            set lInst [$lPartInstsIter NextPartInst $lStatus]
            while {$lInst != $lNullObj} {
                uplevel #0 [list $callback $lInst $lStatus]
                set lInst [$lPartInstsIter NextPartInst $lStatus]
            }
            catch {delete_DboPagePartInstsIter $lPartInstsIter}
            set lPage [$lPagesIter NextPage $lStatus]
        }
        catch {delete_DboSchematicPagesIter $lPagesIter}
        set lView [$lSchematicIter NextView $lStatus]
    }
    catch {delete_DboLibViewsIter $lSchematicIter}
    catch {$lStatus -delete}
}

proc ::capMenuUtil::visibilityGetPartReference {part} {
    set propName [DboTclHelper_sMakeCString "Reference"]
    set propValue [DboTclHelper_sMakeCString]
    catch {$part GetEffectivePropStringValue $propName $propValue}
    set value [DboTclHelper_sGetConstCharPtr $propValue]
    catch {DboTclHelper_sDeleteCString $propName}
    catch {DboTclHelper_sDeleteCString $propValue}
    return $value
}

proc ::capMenuUtil::visibilityPartMatches {part onlyU} {
    if {!$onlyU} { return 1 }
    set refDes [::capMenuUtil::visibilityGetPartReference $part]
    return [regexp -nocase {^U} $refDes]
}

proc ::capMenuUtil::visibilitySetPartValueDisplayType {part lStatus displayType onlyU} {
    if {![::capMenuUtil::visibilityPartMatches $part $onlyU]} { return }

    set lNullObj NULL
    set lPlacedInst [DboPartInstToDboPlacedInst $part]
    if {$lPlacedInst eq $lNullObj} { return }
    if {[catch {set lDisplayPropsIter [$lPlacedInst NewDisplayPropsIter $lStatus]}]} { return }

    set lDProp [$lDisplayPropsIter NextProp $lStatus]
    while {$lDProp != $lNullObj} {
        set lNameCStr [DboTclHelper_sMakeCString]
        catch {$lDProp GetName $lNameCStr}
        set lNameString [DboTclHelper_sGetConstCharPtr $lNameCStr]
        if {[string equal -nocase $lNameString "Value"]} {
            catch {$lDProp SetDisplayType $displayType}
        }
        catch {DboTclHelper_sDeleteCString $lNameCStr}
        set lDProp [$lDisplayPropsIter NextProp $lStatus]
    }
    catch {delete_DboDisplayPropsIter $lDisplayPropsIter}
}

proc ::capMenuUtil::visibilitySetUPinNamesHidden {part lStatus} {
    if {![::capMenuUtil::visibilityPartMatches $part 1]} { return }

    set lNullObj NULL
    set lPlacedInst [DboPartInstToDboPlacedInst $part]
    if {$lPlacedInst eq $lNullObj} { return }

    set pinProp [DboTclHelper_sMakeCString "Name"]
    if {[catch {set lPinsIter [$lPlacedInst NewPinsIter $lStatus]}]} {
        catch {DboTclHelper_sDeleteCString $pinProp}
        return
    }
    set lPin [$lPinsIter NextPin $lStatus]
    while {$lPin != $lNullObj} {
        set dispProp [$lPin GetDisplayProp $pinProp $lStatus]
        if {$dispProp != $lNullObj} {
            catch {$dispProp SetDisplayType 0}
        } else {
            set rotation 0
            set logfont [DboTclHelper_sMakeLOGFONT]
            set lColor $::DboValue_DEFAULT_OBJECT_COLOR
            set displocation [DboTclHelper_sMakeCPoint 0 0]
            catch {
                set newDispProp [$lPin NewDisplayProp $lStatus $pinProp $displocation $rotation $logfont $lColor]
                if {$newDispProp != $lNullObj} { $newDispProp SetDisplayType 0 }
            }
            catch {DboTclHelper_sDeleteLOGFONT $logfont}
            catch {DboTclHelper_sDeleteCPoint $displocation}
        }
        set lPin [$lPinsIter NextPin $lStatus]
    }
    catch {delete_DboPlacedInstPinsIter $lPinsIter}
    catch {DboTclHelper_sDeleteCString $pinProp}
}

proc ::capMenuUtil::setPartValueDisplayType {pLib onlyU displayType} {
    set ::capMenuUtil::visibilityOnlyU $onlyU
    set ::capMenuUtil::visibilityDisplayType $displayType
    ::capMenuUtil::visibilityEachPart ::capMenuUtil::visibilityApplyPartValueDisplayType
}

proc ::capMenuUtil::visibilityApplyPartValueDisplayType {part lStatus} {
    ::capMenuUtil::visibilitySetPartValueDisplayType $part $lStatus $::capMenuUtil::visibilityDisplayType $::capMenuUtil::visibilityOnlyU
}

proc ::capMenuUtil::confirmHideUcomponent {args} {
    if {![::capMenuUtil::visibilityConfirm "将隐藏 U 器件的 Value。\n是否继续？"]} { return }
    ::capMenuUtil::HideUcomponent
}

proc ::capMenuUtil::HideUcomponent {args} {
    ::capMenuUtil::setPartValueDisplayType "" 1 0
}

proc ::capMenuUtil::confirmShowUcomponent {args} {
    if {![::capMenuUtil::visibilityConfirm "将显示 U 器件的 Value。\n是否继续？"]} { return }
    ::capMenuUtil::ShowUcomponent
}

proc ::capMenuUtil::ShowUcomponent {args} {
    ::capMenuUtil::setPartValueDisplayType "" 1 1
}

proc ::capMenuUtil::confirmHideALLcomponent {args} {
    if {![::capMenuUtil::visibilityConfirm "将隐藏所有器件的 Value。\n是否继续？"]} { return }
    ::capMenuUtil::HideALLcomponent
}

proc ::capMenuUtil::HideALLcomponent {args} {
    ::capMenuUtil::setPartValueDisplayType "" 0 0
}

proc ::capMenuUtil::confirmShowALLcomponent {args} {
    if {![::capMenuUtil::visibilityConfirm "将显示所有器件的 Value。\n是否继续？"]} { return }
    ::capMenuUtil::ShowALLcomponent
}

proc ::capMenuUtil::ShowALLcomponent {args} {
    ::capMenuUtil::setPartValueDisplayType "" 0 1
}

proc ::capMenuUtil::confirmHideUPinNames {args} {
    if {![::capMenuUtil::visibilityConfirm "将隐藏 U 器件的 Pin 名称。\n是否继续？"]} { return }
    ::capMenuUtil::HideUPinNames
}

proc ::capMenuUtil::HideUPinNames {args} {
    ::capMenuUtil::visibilityEachPart ::capMenuUtil::visibilitySetUPinNamesHidden
}
