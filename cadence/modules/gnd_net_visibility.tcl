# insta360_HW module: show or hide GND global net names.

namespace eval ::capMenuUtil {}

proc ::capMenuUtil::activeDesignOrWarn {} {
    set design ""
    catch {set design [GetActivePMDesign]}
    if {$design eq "NULL" || $design eq ""} {
        catch {tk_messageBox -icon error -message "No active design is open."}
        return "NULL"
    }
    return $design
}

proc ::capMenuUtil::isGndName {netName} {
    return [expr {[regexp {GND} $netName] || $netName eq "0"}]
}

proc ::capMenuUtil::eachGlobalPower {callback} {
    set lStatus [DboState]
    set lDesign [::capMenuUtil::activeDesignOrWarn]
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
            set lGlobalsIter [$lPage NewGlobalsIter $lStatus]
            set lGlobal [$lGlobalsIter NextGlobal $lStatus]
            while {$lGlobal != $lNullObj} {
                uplevel #0 [list $callback $lGlobal $lStatus]
                set lGlobal [$lGlobalsIter NextGlobal $lStatus]
            }
            catch {delete_DboPageGlobalsIter $lGlobalsIter}
            set lPage [$lPagesIter NextPage $lStatus]
        }
        catch {delete_DboSchematicPagesIter $lPagesIter}
        set lView [$lSchematicIter NextView $lStatus]
    }
    catch {delete_DboLibViewsIter $lSchematicIter}
    catch {$lStatus -delete}
}

proc ::capMenuUtil::withGndNameDisplayProp {lGlobal lStatus displayType createIfMissing} {
    set lPropsIter [$lGlobal NewEffectivePropsIter $lStatus]
    set lPrpName [DboTclHelper_sMakeCString]
    set lPrpValue [DboTclHelper_sMakeCString]
    set lPrpType [DboTclHelper_sMakeDboValueType]
    set lEditable [DboTclHelper_sMakeInt]
    set propStatus [$lPropsIter NextEffectiveProp $lPrpName $lPrpValue $lPrpType $lEditable]

    while {[$propStatus OK]} {
        set propName [DboTclHelper_sGetConstCharPtr $lPrpName]
        if {$propName eq "Name"} {
            set netName [DboTclHelper_sGetConstCharPtr $lPrpValue]
            if {[::capMenuUtil::isGndName $netName]} {
                set pDispProp [$lGlobal GetDisplayProp $lPrpName $lStatus]
                if {$pDispProp == "NULL" && $createIfMissing} {
                    set rotation 0
                    set logfont [DboTclHelper_sMakeLOGFONT]
                    set lColor $::DboValue_DEFAULT_OBJECT_COLOR
                    set displocation [DboTclHelper_sMakeCPoint 0 10]
                    set pDispProp [$lGlobal NewDisplayProp $lStatus $lPrpName $displocation $rotation $logfont $lColor]
                }
                if {$pDispProp != "NULL"} {
                    $pDispProp SetDisplayType $displayType
                }
            }
        }
        set propStatus [$lPropsIter NextEffectiveProp $lPrpName $lPrpValue $lPrpType $lEditable]
    }

    catch {delete_DboEffectivePropsIter $lPropsIter}
}

proc ::capMenuUtil::GroundNameVisible {args} {
    ::capMenuUtil::eachGlobalPower ::capMenuUtil::showGndName
}

proc ::capMenuUtil::GroundNameHidden {args} {
    ::capMenuUtil::eachGlobalPower ::capMenuUtil::hideGndName
}

proc ::capMenuUtil::showGndName {lGlobal lStatus} {
    ::capMenuUtil::withGndNameDisplayProp $lGlobal $lStatus 1 1
}

proc ::capMenuUtil::hideGndName {lGlobal lStatus} {
    ::capMenuUtil::withGndNameDisplayProp $lGlobal $lStatus 0 0
}
