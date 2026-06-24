# insta360_HW module: restore displayed net name colors to default.

namespace eval ::capMenuUtil {}

proc ::capMenuUtil::resetNetColorActiveDesignOrWarn {} {
    set design ""
    catch {set design [GetActivePMDesign]}
    if {$design eq "NULL" || $design eq ""} {
        catch {tk_messageBox -icon error -message "未找到当前打开的设计。"}
        return "NULL"
    }
    return $design
}

proc ::capMenuUtil::resetNetColorSetObjectDefault {obj} {
    set prop [DboTclHelper_sMakeCString "Color"]
    set value [DboTclHelper_sMakeCString "Default"]
    catch {$obj SetEffectivePropStringValue $prop $value}
}

proc ::capMenuUtil::resetNetColorDisplayProps {obj colorIndex lStatus} {
    if {[catch {set iter [$obj NewDisplayPropsIter $lStatus]}]} { return }
    set prop [$iter NextProp $lStatus]
    while {$prop != "NULL"} {
        catch {$prop SetColor $colorIndex}
        set prop [$iter NextProp $lStatus]
    }
    catch {delete_DboDisplayPropsIter $iter}
}

proc ::capMenuUtil::ResetNetnameColor {args} {
    set lStatus [DboState]
    set lDesign [::capMenuUtil::resetNetColorActiveDesignOrWarn]
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
            ::capMenuUtil::resetNetColorWireAliases $lPage $lStatus
            ::capMenuUtil::resetNetColorOffPages $lPage $lStatus
            ::capMenuUtil::resetNetColorPorts $lPage $lStatus
            set lPage [$lPagesIter NextPage $lStatus]
        }
        catch {delete_DboSchematicPagesIter $lPagesIter}
        set lView [$lSchematicIter NextView $lStatus]
    }
    catch {delete_DboLibViewsIter $lSchematicIter}
    catch {$lStatus -delete}
}

proc ::capMenuUtil::resetNetColorWireAliases {lPage lStatus} {
    set lWiresIter [$lPage NewWiresIter $lStatus]
    set lWire [$lWiresIter NextWire $lStatus]
    while {$lWire != "NULL"} {
        set lAliasIter [$lWire NewAliasesIter $lStatus]
        set lAlias [$lAliasIter NextAlias $lStatus]
        while {$lAlias != "NULL"} {
            ::capMenuUtil::resetNetColorSetObjectDefault $lAlias
            set lAlias [$lAliasIter NextAlias $lStatus]
        }
        catch {delete_DboWireAliasesIter $lAliasIter}
        set lWire [$lWiresIter NextWire $lStatus]
    }
    catch {delete_DboPageWiresIter $lWiresIter}
}

proc ::capMenuUtil::resetNetColorOffPages {lPage lStatus} {
    set lOffPagesIter [$lPage NewOffPageConnectorsIter $lStatus]
    set lOffPage [$lOffPagesIter NextOffPageConnector $lStatus]
    while {$lOffPage != "NULL"} {
        ::capMenuUtil::resetNetColorSetObjectDefault $lOffPage
        ::capMenuUtil::resetNetColorDisplayProps $lOffPage 48 $lStatus
        set lOffPage [$lOffPagesIter NextOffPageConnector $lStatus]
    }
    catch {delete_DboPageOffPageConnectorsIter $lOffPagesIter}
}

proc ::capMenuUtil::resetNetColorPorts {lPage lStatus} {
    set lPortsIter [$lPage NewPortsIter $lStatus]
    set lPort [$lPortsIter NextPort $lStatus]
    while {$lPort != "NULL"} {
        ::capMenuUtil::resetNetColorSetObjectDefault $lPort
        ::capMenuUtil::resetNetColorDisplayProps $lPort 48 $lStatus
        set lPort [$lPortsIter NextPort $lStatus]
    }
    catch {delete_DboPagePortsIter $lPortsIter}
}
