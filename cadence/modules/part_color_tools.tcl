# insta360_HW module: gray NC parts and restore part colors.

namespace eval ::capMenuUtil {}

proc ::capMenuUtil::partColorActiveDesignOrWarn {} {
    set design ""
    catch {set design [GetActivePMDesign]}
    if {$design eq "NULL" || $design eq ""} {
        catch {tk_messageBox -icon error -message "未找到当前打开的设计。"}
        return "NULL"
    }
    return $design
}

proc ::capMenuUtil::partColorEachPart {callback} {
    set lStatus [DboState]
    set lDesign [::capMenuUtil::partColorActiveDesignOrWarn]
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

proc ::capMenuUtil::partColorGetProperty {part name} {
    set propName [DboTclHelper_sMakeCString $name]
    set propValue [DboTclHelper_sMakeCString]
    catch {$part GetEffectivePropStringValue $propName $propValue}
    set value [DboTclHelper_sGetConstCharPtr $propValue]
    catch {DboTclHelper_sDeleteCString $propName}
    catch {DboTclHelper_sDeleteCString $propValue}
    return $value
}

proc ::capMenuUtil::partColorSetEffectiveColor {part value} {
    set colorName [DboTclHelper_sMakeCString "Color"]
    set colorValue [DboTclHelper_sMakeCString $value]
    catch {$part SetEffectivePropStringValue $colorName $colorValue}
    catch {DboTclHelper_sDeleteCString $colorName}
    catch {DboTclHelper_sDeleteCString $colorValue}
}

proc ::capMenuUtil::partColorSetDisplayProps {part colorIndex lStatus} {
    set lNullObj NULL
    set placed [DboPartInstToDboPlacedInst $part]
    if {$placed eq $lNullObj} { return }
    if {[catch {set iter [$placed NewDisplayPropsIter $lStatus]}]} { return }
    set prop [$iter NextProp $lStatus]
    while {$prop != $lNullObj} {
        catch {$prop SetColor $colorIndex}
        set prop [$iter NextProp $lStatus]
    }
    catch {delete_DboDisplayPropsIter $iter}
}

proc ::capMenuUtil::partColorIsNc {part} {
    set value [::capMenuUtil::partColorGetProperty $part "Value"]
    set partNumber [::capMenuUtil::partColorGetProperty $part "Part Number"]
    return [expr {$partNumber eq "" || [regexp {NC/} $value]}]
}

proc ::capMenuUtil::partColorApplyNcGray {part lStatus} {
    if {[::capMenuUtil::partColorIsNc $part]} {
        ::capMenuUtil::partColorSetEffectiveColor $part "RGB(192,192,192)"
        ::capMenuUtil::partColorSetDisplayProps $part 45 $lStatus
    } else {
        ::capMenuUtil::partColorSetEffectiveColor $part "Default"
        ::capMenuUtil::partColorSetDisplayProps $part 48 $lStatus
    }
}

proc ::capMenuUtil::partColorRestoreDefault {part lStatus} {
    ::capMenuUtil::partColorSetEffectiveColor $part "Default"
    ::capMenuUtil::partColorSetDisplayProps $part 48 $lStatus
}

proc ::capMenuUtil::NcPartGrayed {args} {
    ::capMenuUtil::partColorEachPart ::capMenuUtil::partColorApplyNcGray
}

proc ::capMenuUtil::RestorePartDefaultColor {args} {
    ::capMenuUtil::partColorEachPart ::capMenuUtil::partColorRestoreDefault
}
