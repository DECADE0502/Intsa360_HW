# insta360_HW module: toggle NC prefix and gray display for selected Capture parts.

namespace eval ::capNCToggleSelected {
    variable prefix {NC/}
    variable grayColor {RGB(192,192,192)}
    variable restoreColor {Default}
    variable grayDisplayColor 45
    variable normalDisplayColor 48
}

proc ::capNCToggleSelected::log {message} {
    set line [format {[capNCToggleSelected] %s} $message]
    catch {
        set msg [DboTclHelper_sMakeCString $line]
        DboState_WriteToSessionLog $msg
    }
    catch {puts $line}
}

proc ::capNCToggleSelected::toggleFromMenu {args} {
    if {[catch {::capNCToggleSelected::toggle} err]} {
        ::capNCToggleSelected::log "ERROR: $err"
        catch {tk_messageBox -icon error -type ok -title "Toggle Selected NC" -message $err}
    }
}

proc ::capNCToggleSelected::enabled {} {
    if {[info commands GetSelectedObjects] eq ""} { return 0 }
    if {[catch {set selected [GetSelectedObjects]}]} { return 0 }
    return [expr {[llength $selected] > 0}]
}

proc ::capNCToggleSelected::toggle {} {
    if {![::capNCToggleSelected::enabled]} {
        catch {tk_messageBox -icon info -type ok -title "Toggle Selected NC" -message "Select one or more parts first."}
        ::capNCToggleSelected::log "no selected objects"
        return 0
    }

    set selected [GetSelectedObjects]
    set added 0
    set removed 0
    set skipped 0

    foreach obj $selected {
        set part [::capNCToggleSelected::asPart $obj]
        if {$part == "NULL"} {
            incr skipped
            continue
        }

        set result [::capNCToggleSelected::togglePart $part]
        switch -- $result {
            added { incr added }
            removed { incr removed }
            default { incr skipped }
        }
    }

    ::capNCToggleSelected::log "added: $added, removed: $removed, skipped: $skipped"
    return [expr {$added + $removed}]
}

proc ::capNCToggleSelected::togglePart {part} {
    variable prefix
    set info [::capNCToggleSelected::getEffectiveStringProperty $part "Value"]
    if {![lindex $info 0]} { return skipped }

    set oldValue [lindex $info 1]
    if {[string match "$prefix*" $oldValue]} {
        if {[::capNCToggleSelected::removeNC $part $oldValue]} { return removed }
    } else {
        if {[::capNCToggleSelected::addNC $part $oldValue]} { return added }
    }
    return skipped
}

proc ::capNCToggleSelected::addNC {part oldValue} {
    variable prefix
    set newValue "$prefix$oldValue"
    if {![::capNCToggleSelected::setPartValue $part $newValue]} {
        if {![::capNCToggleSelected::setEffectiveStringProperty $part "Value" $newValue]} { return 0 }
    }
    ::capNCToggleSelected::grayPart $part
    catch {$part Update}
    return 1
}

proc ::capNCToggleSelected::removeNC {part oldValue} {
    variable prefix
    set newValue [string range $oldValue [string length $prefix] end]
    if {![::capNCToggleSelected::setPartValue $part $newValue]} {
        if {![::capNCToggleSelected::setEffectiveStringProperty $part "Value" $newValue]} { return 0 }
    }
    ::capNCToggleSelected::restorePart $part
    catch {$part Update}
    return 1
}

proc ::capNCToggleSelected::asPart {obj} {
    if {$obj == "NULL" || $obj == ""} { return "NULL" }
    if {![catch {set placed [DboPartInstToDboPlacedInst $obj]}] && $placed != "NULL"} { return $placed }
    if {![catch {set drawn [DboPartInstToDboDrawnInst $obj]}] && $drawn != "NULL"} { return $drawn }
    if {[::capNCToggleSelected::canReadValue $obj]} { return $obj }
    return "NULL"
}

proc ::capNCToggleSelected::canReadValue {part} {
    return [lindex [::capNCToggleSelected::getEffectiveStringProperty $part "Value"] 0]
}

proc ::capNCToggleSelected::getEffectiveStringProperty {obj propName} {
    set prop [DboTclHelper_sMakeCString $propName]
    set value [DboTclHelper_sMakeCString ""]
    if {[catch {set state [$obj GetEffectivePropStringValue $prop $value]}]} { return [list 0 ""] }
    set str [DboTclHelper_sGetConstCharPtr $value]
    return [list 1 $str]
}

proc ::capNCToggleSelected::setEffectiveStringProperty {obj propName propValue} {
    set prop [DboTclHelper_sMakeCString $propName]
    set value [DboTclHelper_sMakeCString $propValue]
    if {[catch {$obj SetEffectivePropStringValue $prop $value}]} { return 0 }
    return 1
}

proc ::capNCToggleSelected::setPartValue {part value} {
    if {[catch {$part SetPartValue $value}]} { return 0 }
    return 1
}

proc ::capNCToggleSelected::grayPart {part} {
    variable grayColor
    variable grayDisplayColor
    ::capNCToggleSelected::setEffectiveStringProperty $part "Color" $grayColor
    catch {$part SetColor $grayDisplayColor}
    ::capNCToggleSelected::setDisplayPropsColor $part $grayDisplayColor
}

proc ::capNCToggleSelected::restorePart {part} {
    variable restoreColor
    variable normalDisplayColor
    ::capNCToggleSelected::setEffectiveStringProperty $part "Color" $restoreColor
    catch {$part SetColor $normalDisplayColor}
    ::capNCToggleSelected::setDisplayPropsColor $part $normalDisplayColor
}

proc ::capNCToggleSelected::setDisplayPropsColor {part colorIndex} {
    set status [DboState]
    set placed $part
    if {![catch {set converted [DboPartInstToDboPlacedInst $part]}] && $converted != "NULL"} { set placed $converted }
    if {[catch {set iter [$placed NewDisplayPropsIter $status]}]} { return 0 }
    set prop [$iter NextProp $status]
    while {$prop != "NULL"} {
        catch {$prop SetColor $colorIndex}
        set prop [$iter NextProp $status]
    }
    catch {delete_DboDisplayPropsIter $iter}
    return 1
}
