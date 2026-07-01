# Enhanced core tools for Insta360\u786c\u4ef6\u63d0\u6548\u5e73\u53f0.
# This module is sourced only by the controlled platform loader when a script is enabled.
# It must not register Capture menus or global actions by itself.

package provide capMenuUtil 1.0

namespace eval ::capMenuUtil {
    variable toolVersion "V1.8"
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    if {[catch {package require Tk}]} {
        puts "Warning: Tk package not available, GUI features will be disabled"
    } else {
        # \u9690\u85cf\u4e3bTk\u7a97\u53e3\uff08\u542f\u52a8\u65f6\u4e0d\u663e\u793a\uff09
        if {[winfo exists .]} {
            wm withdraw .
            # \u7ed1\u5b9a\u7a97\u53e3\u6620\u5c04\u4e8b\u4ef6\uff0c\u9632\u6b62\u4e3b\u7a97\u53e3\u610f\u5916\u663e\u793a
            bind . <Map> { wm withdraw . }
        }
    }
    
    # \u7f13\u5b58\u7f51\u7edc\u540d\u6620\u5c04\u5173\u7cfb\uff0c\u63d0\u9ad8\u6027\u80fd
    variable netNameMap [list]
    # \u5df2\u751f\u6210\u7684\u968f\u673a\u540d\u79f0\u96c6\u5408\uff0c\u786e\u4fdd\u552f\u4e00\u6027
    variable generatedNames [list]
    # \u6027\u80fd\u4f18\u5316\uff1a\u9ed8\u8ba4\u5173\u95ed\u9010\u5bf9\u8c61\u65e5\u5fd7\uff0c\u907f\u514d\u5927\u578b\u539f\u7406\u56fe\u5728 Capture \u547d\u4ee4\u7a97\u53e3\u5237\u5c4f\u5361\u987f\u3002
    variable verboseLog 0
}

proc ::capMenuUtil::logDebug {message} {
    variable verboseLog
    if {$verboseLog} {
        puts $message
    }
}

# ////////////////////////////////////////////////////////////////////////////////
# \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
# ////////////////////////////////////////////////////////////////////////////////
# ////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::confirmGrayedPartToNC { pLib } {
    # \u6b65\u9aa41\uff1a\u7528\u6237\u786e\u8ba4\uff08\u9632\u6b62\u8bef\u64cd\u4f5c\uff09
    set confirm [tk_messageBox -icon question -message "Set Value to NC for NC parts.\nContinue?" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	::capMenuUtil::GrayedPartToNC $pLib
}

proc ::capMenuUtil::confirmHideUPinNames { pLib } {
    # \u6b65\u9aa41\uff1a\u7528\u6237\u786e\u8ba4\uff08\u9632\u6b62\u8bef\u64cd\u4f5c\uff09
    set confirm [tk_messageBox -icon question -message "Hide pin names for U parts.\nContinue?" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	::capMenuUtil::HideUPinNames $pLib
	
}

proc ::capMenuUtil::confirmRandomizeNetNames { pLib } {
# \u6b65\u9aa41\uff1a\u7528\u6237\u786e\u8ba4\uff08\u9632\u6b62\u8bef\u64cd\u4f5c\uff09
    set confirm [tk_messageBox -icon question -message "Randomize all schematic net names.\nEquivalent names keep the same generated value.\nContinue?" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	::capMenuUtil::RandomizeNetNames $pLib
	# \u663e\u793a\u5b8c\u6210\u7ed3\u679c
    tk_messageBox -message "Net name randomization completed." -icon info
}
proc ::capMenuUtil::confirmDeleteAllGraphic { pLib } {
    # \u6b65\u9aa41\uff1a\u7528\u6237\u786e\u8ba4\uff08\u9632\u6b62\u8bef\u64cd\u4f5c\uff09
    set confirm [tk_messageBox -icon question -message "Delete all graphic objects.\nContinue?" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	::capMenuUtil::DeleteAllGraphic $pLib
	
}
proc ::capMenuUtil::confirmHideUcomponent { pLib } {
    # \u6b65\u9aa41\uff1a\u7528\u6237\u786e\u8ba4\uff08\u9632\u6b62\u8bef\u64cd\u4f5c\uff09
    set confirm [tk_messageBox -icon question -message "Hide Value for U parts.\nContinue?" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	::capMenuUtil::HideUcomponent $pLib
	
}
proc ::capMenuUtil::confirmHideALLcomponent { pLib } {
    # \u6b65\u9aa41\uff1a\u7528\u6237\u786e\u8ba4\uff08\u9632\u6b62\u8bef\u64cd\u4f5c\uff09
    set confirm [tk_messageBox -icon question -message "Hide Value for all parts.\nContinue?" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	::capMenuUtil::HideALLcomponent $pLib
	
}
proc ::capMenuUtil::confirmDeleteTextTitleblocks { pLib } {
    # \u6b65\u9aa41\uff1a\u7528\u6237\u786e\u8ba4\uff08\u9632\u6b62\u8bef\u64cd\u4f5c\uff09
    set confirm [tk_messageBox -icon question -message "Clear text and delete title blocks.\nContinue?" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	::capMenuUtil::DeleteTextTitleblocks $pLib
	
}
proc ::capMenuUtil::confirmSchematicObfuscation { pLib } {
# \u6b65\u9aa41\uff1a\u7528\u6237\u786e\u8ba4\uff08\u9632\u6b62\u8bef\u64cd\u4f5c\uff09
    set confirm [tk_messageBox -icon question -message "Obfuscate sensitive schematic information.\nContinue?" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	
	::capMenuUtil::DeleteAllGraphic $pLib
	::capMenuUtil::HideALLcomponent $pLib
	::capMenuUtil::HideSensitiveComponentProperties $pLib
	::capMenuUtil::DeleteTextTitleblocks $pLib
	::capMenuUtil::HideUPinNames $pLib
	::capMenuUtil::RandomizeNetNames $pLib
	# \u663e\u793a\u5b8c\u6210\u7ed3\u679c
    tk_messageBox -message "Schematic obfuscation completed." -icon info
}


#/////////////////////////////////////////////////////////////////////////////////
# \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
#/////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::confirmShowUPinNames { pLib } {
    set confirm [tk_messageBox -icon question -message "Show pin names for U parts.\nContinue?" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
    ::capMenuUtil::ShowUPinNames $pLib
}

proc ::capMenuUtil::confirmShowUcomponent { pLib } {
    set confirm [tk_messageBox -icon question -message "Show Value for U parts.\nContinue?" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
    ::capMenuUtil::ShowUcomponent $pLib
}

proc ::capMenuUtil::confirmShowALLcomponent { pLib } {
    set confirm [tk_messageBox -icon question -message "Show Value for all parts.\nContinue?" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
    ::capMenuUtil::ShowALLcomponent $pLib
}
proc ::capMenuUtil::HideUPinNames { pLib } {
    # \u521d\u59cb\u5316\u57fa\u7840\u5bf9\u8c61
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    set lNullObj NULL
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "No active design is open."
        return
    }

    # \u934f\u714e\ue19016.6\u9428\u52eb\u5e2b\u941e\u55d7\u6d58\u6769\ue15d\u552c\u9363\u3125\u57b1\u5be4?
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }

    # \u904d\u5386\u6240\u6709\u539f\u7406\u56fe
    set lView [$lSchematicIter NextView $lStatus]
    while {$lView != $lNullObj} {
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]

        # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
        set lPage [$lPagesIter NextPage $lStatus]
        while {$lPage != $lNullObj} {
            set lPartInstsIter [$lPage NewPartInstsIter $lStatus]
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            set lInst [$lPartInstsIter NextPartInst $lStatus]
            while {$lInst != $lNullObj} {
                # \u947e\u5cf0\u5f47\u9363\u3124\u6b22\u6d63\u5d85\u5f7f\u951b\u5727eference\u951b?
                set lRefName [DboTclHelper_sMakeCString "Reference"]
                set lRefValue [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lRefName $lRefValue
                set refDes [DboTclHelper_sGetConstCharPtr $lRefValue]
                # \u4ec5\u5904\u7406\u4f4d\u53f7\u4ee5U/u\u5f00\u5934\u7684\u5668\u4ef6
                if {[regexp -nocase {^U} $refDes]} {
                    set lPlacedInst [DboPartInstToDboPlacedInst $lInst]
                    if {$lPlacedInst != $lNullObj} {
                        
                        # \u5df2\u751f\u6210\u7684\u968f\u673a\u540d\u79f0\u96c6\u5408\uff0c\u786e\u4fdd\u552f\u4e00\u6027
                        set pinProp [DboTclHelper_sMakeCString "Name"]
                        
                        # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                        set lPinsIter [$lPlacedInst NewPinsIter $lStatus]
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
                                    set newDispProp [$lPin NewDisplayProp $lStatus $pinProp \
                                                      $displocation $rotation $logfont $lColor]
                                    if {$newDispProp != $lNullObj} {
                                        $newDispProp SetDisplayType 0
                                    }
                                }
                                catch {DboTclHelper_sDeleteLOGFONT $logfont}
                                catch {DboTclHelper_sDeleteCPoint $displocation}
                            }
                            set lPin [$lPinsIter NextPin $lStatus]
                        }
                        
                        # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                        catch {delete_DboPlacedInstPinsIter $lPinsIter}
                        
                        # \u7edf\u4e00\u91ca\u653e\u5916\u90e8\u7533\u8bf7\u7684\u5c5e\u6027\u5b57\u7b26\u4e32
                        catch {DboTclHelper_sDeleteCString $pinProp}
                    }
                }

                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                DboTclHelper_sDeleteCString $lRefName
                DboTclHelper_sDeleteCString $lRefValue
                set lInst [$lPartInstsIter NextPartInst $lStatus]
            }
            delete_DboPagePartInstsIter $lPartInstsIter
            set lPage [$lPagesIter NextPage $lStatus]
        }
        delete_DboSchematicPagesIter $lPagesIter
        set lView [$lSchematicIter NextView $lStatus]
    }
    delete_DboLibViewsIter $lSchematicIter
    
}




# ////////////////////////////////////////////////////////////////////////////////
# \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
# ////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::showNetNameExchangeDialog { pLib } {
    if {[winfo exists .netNameExchange]} {
        destroy .netNameExchange
    }
    # \u5173\u952e\u4f18\u53162\uff1a\u521b\u5efa\u72ec\u7acb\u9876\u7ea7\u7a97\u53e3\uff0c\u4e0d\u4f9d\u8d56\u4e3b\u7a97\u53e3\u663e\u793a
    toplevel .netNameExchange
    wm title .netNameExchange "Replace Net Names"
    wm resizable .netNameExchange 0 0
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    # wm transient .netNameExchange .
    # \u5bee\u54c4\u57d7\u93c4\u5267\u305a\u9a9e\u5241\u7586\u6924?
    wm deiconify .netNameExchange
    raise .netNameExchange
    focus .netNameExchange

    set font {TkDefaultFont 10}
    set pad 8

    frame .netNameExchange.inputFrame -padx $pad -pady $pad
    label .netNameExchange.inputFrame.oldLabel -text "Find net text:" -font $font
    entry .netNameExchange.inputFrame.oldEntry -width 30 -font $font
    label .netNameExchange.inputFrame.newLabel -text "Replace with:" -font $font
    entry .netNameExchange.inputFrame.newEntry -width 30 -font $font

    grid .netNameExchange.inputFrame.oldLabel -row 0 -column 0 -sticky w -pady 2
    grid .netNameExchange.inputFrame.oldEntry -row 0 -column 1 -sticky w -pady 2
    grid .netNameExchange.inputFrame.newLabel -row 1 -column 0 -sticky w -pady 2
    grid .netNameExchange.inputFrame.newEntry -row 1 -column 1 -sticky w -pady 2

    frame .netNameExchange.btnFrame -padx $pad -pady $pad
    button .netNameExchange.btnFrame.ok -text "OK" -font $font \
        -command [list ::capMenuUtil::performNetNameExchange $pLib \
        [list .netNameExchange.inputFrame.oldEntry] \
        [list .netNameExchange.inputFrame.newEntry] \
        [list .netNameExchange]]
    button .netNameExchange.btnFrame.cancel -text "Cancel" -font $font \
        -command [list destroy .netNameExchange]

    pack .netNameExchange.btnFrame.ok -side left -padx 5
    pack .netNameExchange.btnFrame.cancel -side left -padx 5
    pack .netNameExchange.inputFrame -fill x
    pack .netNameExchange.btnFrame -fill x -pady 5

    update idletasks
    set x [expr {([winfo screenwidth .] - [winfo width .netNameExchange]) / 2}]
    set y [expr {([winfo screenheight .] - [winfo height .netNameExchange]) / 2}]
    wm geometry .netNameExchange "+$x+$y"
    vwait ::capMenuUtil::dialogResult
}

proc ::capMenuUtil::performNetNameExchange { pLib oldEntryWidget newEntryWidget window } {
    set oldString [[lindex $oldEntryWidget 0] get]
    set newString [[lindex $newEntryWidget 0] get]
    if {$oldString eq ""} {
        tk_messageBox -icon warning -message "Enter the net-name text to replace."
        return
    }
    destroy [lindex $window 0]
    set ::capMenuUtil::dialogResult 1
    ::capMenuUtil::NetNameExchange $pLib $oldString $newString
}


proc ::capMenuUtil::NetNameExchange { pLib oldString newString } {
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    set replaceMap [list $oldString $newString]
    
    # \u5df2\u751f\u6210\u7684\u968f\u673a\u540d\u79f0\u96c6\u5408\uff0c\u786e\u4fdd\u552f\u4e00\u6027
    set lStatus [DboState]
    # \u947e\u5cf0\u5f47\u93b5\u0446\ue511\u9428\u52ee\ue195\u7481\u2033\ue1ee\u749e?
    set lDesign [GetActivePMDesign]
    
    # \u68c0\u67e5\u662f\u5426\u6709\u6d3b\u52a8\u8bbe\u8ba1
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "No active design is open."
        return
    }
    
    # \u8ba1\u7b97\u603b\u9875\u9762\u6570\u7528\u4e8e\u8fdb\u5ea6\u663e\u793a
    set totalPages [::capMenuUtil::countTotalPages $lDesign $lStatus]
    if {$totalPages == 0} {
        tk_messageBox -icon warning -message "No pages were found in the current design."
        return
    }
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    set progressWindow [::capMenuUtil::showNetExchangeProgressDialog $totalPages $oldString $newString]
    set currentPage 0
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    update
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    # \u83b7\u53d6\u7b2c\u4e00\u4e2a\u539f\u7406\u56fe\u89c6\u56fe
    set lView [$lSchematicIter NextView $lStatus]
    set SchNum 0
    set lNullObj NULL
    set totalReplacements 0  ;# \u7f01\u71bb\ue178\u93ac\u7ed8\u6d5b\u93b9\u3221\ue0bc\u93c1?
    
    while { $lView != $lNullObj} {
        incr SchNum
        # \u4eceDboView\u8f6c\u6362\u4e3aDboSchematic
        set lSchematic [DboViewToDboSchematic $lView]
        # \u65b0\u5efa\u9875\u9762\u8fed\u4ee3\u5668\uff0c\u7528\u4e8e\u904d\u5386
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        # \u947e\u5cf0\u5f47\u7ed7\ue0ff\u7af4\u6924?
        set lPage [$lPagesIter NextPage $lStatus]
        set PageNum 0
        
        while {$lPage!=$lNullObj} {
            incr PageNum
            incr currentPage
            
            # \u66f4\u65b0\u8fdb\u5ea6
            ::capMenuUtil::updateProgress $progressWindow $currentPage $totalPages
            
            puts "\n###############################Process Schematic $SchNum"
            puts "###############################Process Page $PageNum"
            
            ##################################\u5f00\u59cb\u66ff\u6362Net##################################
            puts "Start processing network name replacement"
            
            set lWiresIter [$lPage NewWiresIter $lStatus]
            # \u947e\u5cf0\u5f47\u7ed7\ue0ff\u7af4\u93c9\u2033\ue1f1\u7efe?
            set lWire [$lWiresIter NextWire $lStatus] 
            while {$lWire != $lNullObj} {
                set lAliasIter [$lWire NewAliasesIter $lStatus]
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lAlias [$lAliasIter NextAlias $lStatus]
                while { $lAlias!=$lNullObj} {
                    set lAliasString [DboTclHelper_sMakeCString]
                    $lAlias GetName $lAliasString
                    set lNameString [DboTclHelper_sGetConstCharPtr $lAliasString]
                    # \u5982\u679c\u542b\u6709\u76ee\u6807\u5b57\u7b26\uff0c\u5219\u8fdb\u884c\u66ff\u6362
                    if {[string first $oldString $lNameString] != -1} {
                        incr totalReplacements
                        puts "\nFind the network name: $lNameString"
                        set lNewNameString [string map $replaceMap $lNameString]
                        set lName [DboTclHelper_sMakeCString $lNewNameString]
                        $lAlias SetName $lName
                        set lName [DboTclHelper_sGetConstCharPtr $lName]
                        puts "The network name has been replaced by: $lName"
                    }
                    
                    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                    set lAlias [$lAliasIter NextAlias $lStatus]
                }
                delete_DboWireAliasesIter $lAliasIter
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lWire [$lWiresIter NextWire $lStatus] 
            }
            delete_DboPageWiresIter $lWiresIter
            
            puts "\nNetwork name replacement ends"
            ##################################\u7ed3\u675f\u66ff\u6362Net##################################
            
            ##################################\u5f00\u59cb\u66ff\u6362port##################################
            puts "Start processing port name replacement"
            set lPortsIter [$lPage NewPortsIter $lStatus]
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            set lPort [$lPortsIter NextPort $lStatus]
            while {$lPort!=$lNullObj} {
                set lPortString [DboTclHelper_sMakeCString]
                $lPort GetName $lPortString
                set lNameString [DboTclHelper_sGetConstCharPtr $lPortString]
                # \u5982\u679c\u542b\u6709\u76ee\u6807\u5b57\u7b26\uff0c\u5219\u8fdb\u884c\u66ff\u6362
                if {[string first $oldString $lNameString] != -1} {
                    incr totalReplacements
                    puts "\nFind the port name: $lNameString"
                    set lNewNameString [string map $replaceMap $lNameString]
                    set lName [DboTclHelper_sMakeCString $lNewNameString]
                    $lPort SetName $lName
                    set lName [DboTclHelper_sGetConstCharPtr $lName]
                    puts "The port name has been replaced by: $lName"
                }

                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lPort [$lPortsIter NextPort $lStatus]
            }  
            delete_DboPagePortsIter $lPortsIter
            
            puts "\nPort name replacement ends"
            ##################################\u7ed3\u675f\u66ff\u6362port##################################
            
            ##################################\u5f00\u59cb\u66ff\u6362Offpage##################################
            puts "Start processing Offpage name replacement"
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            if {[info exists ::IterDefs_ALL]} {
                set lOffPagesIter [$lPage NewOffPageConnectorsIter $lStatus $::IterDefs_ALL]
            } else {
                set lOffPagesIter [$lPage NewOffPageConnectorsIter $lStatus]
            }
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            set lOffPage [$lOffPagesIter NextOffPageConnector $lStatus]
            while {$lOffPage!=$lNullObj} {
                set lOffPageString [DboTclHelper_sMakeCString]
                $lOffPage GetName $lOffPageString
                set lNameString [DboTclHelper_sGetConstCharPtr $lOffPageString]
                # \u5982\u679c\u542b\u6709\u76ee\u6807\u5b57\u7b26\uff0c\u5219\u8fdb\u884c\u66ff\u6362
                if {[string first $oldString $lNameString] != -1} {
                    incr totalReplacements
                    puts "\nFind the Offpage name: $lNameString"
                    set lNewNameString [string map $replaceMap $lNameString]
                    set lName [DboTclHelper_sMakeCString $lNewNameString]
                    $lOffPage SetName $lName
                    set lName [DboTclHelper_sGetConstCharPtr $lName]
                    puts "The Offpage name has been replaced by: $lName"
                }
            
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lOffPage [$lOffPagesIter NextOffPageConnector $lStatus]
            }
            delete_DboPageOffPageConnectorsIter $lOffPagesIter
            puts "\nOffpage name replacement ends"
            ##################################\u7ed3\u675f\u66ff\u6362Offpage##################################
            
            ##################################\u5f00\u59cb\u66ff\u6362power##################################
            puts "Start processing Power name replacement"
            set lGlobalsIter [$lPage NewGlobalsIter $lStatus]
            # \u83b7\u53d6\u7b2c\u4e00\u4e2a\u5168\u5c40\u5bf9\u8c61
            set lGlobal [$lGlobalsIter NextGlobal $lStatus]
            while { $lGlobal!=$lNullObj } { 
                set lPropsIter [$lGlobal NewEffectivePropsIter $lStatus]
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lPrpName [DboTclHelper_sMakeCString]
                set lPrpValue [DboTclHelper_sMakeCString]
                set lPrpType [DboTclHelper_sMakeDboValueType]
                set lEditable [DboTclHelper_sMakeInt]
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lStatus [$lPropsIter NextEffectiveProp $lPrpName $lPrpValue $lPrpType $lEditable]
                while { [$lStatus OK] } {
                    set lNameString [DboTclHelper_sGetConstCharPtr $lPrpValue]
                    # \u5982\u679c\u542b\u6709\u76ee\u6807\u5b57\u7b26\uff0c\u5219\u8fdb\u884c\u66ff\u6362
                    if {[string first $oldString $lNameString] != -1} {
                        incr totalReplacements
                        puts "\nFind the Power name: $lNameString"
                        set lNewNameString [string map $replaceMap $lNameString]
                        set lName [DboTclHelper_sMakeCString $lNewNameString]
                        $lGlobal SetEffectivePropStringValue $lPrpName $lName
                        set lName [DboTclHelper_sGetConstCharPtr $lName]
                        puts "The Power name has been replaced by: $lName"
                    }
                
                    set lStatus [$lPropsIter NextEffectiveProp $lPrpName $lPrpValue $lPrpType $lEditable]
                }
                delete_DboEffectivePropsIter $lPropsIter			
                # \u83b7\u53d6\u4e0b\u4e00\u4e2a\u5168\u5c40\u5bf9\u8c61
                set lGlobal [$lGlobalsIter NextGlobal $lStatus]
            }
            delete_DboPageGlobalsIter $lGlobalsIter
            puts "\nPower name replacement ends"
            ##################################\u7ed3\u675f\u66ff\u6362power##################################
            
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            set lPage [$lPagesIter NextPage $lStatus]
        }
        delete_DboSchematicPagesIter $lPagesIter
        # \u83b7\u53d6\u4e0b\u4e00\u4e2a\u539f\u7406\u56fe\u89c6\u56fe
        set lView [$lSchematicIter NextView $lStatus]
    }
    delete_DboLibViewsIter $lSchematicIter
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    destroy $progressWindow
    
    # \u663e\u793a\u5b8c\u6210\u7ed3\u679c
    tk_messageBox -message "Replace Net Names completed.\nTotal replacements: $totalReplacements" -icon info
}

# ////////////////////////////////////////////////////////////////////////////////
# \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
# ////////////////////////////////////////////////////////////////////////////////

proc ::capMenuUtil::NcPartGrayed { pLib } {
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "No active design is open."
        return
    }
    
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    set lView [$lSchematicIter NextView $lStatus]
    set lNullObj NULL

    while { $lView != $lNullObj} {
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]
        while {$lPage!=$lNullObj} {
            set lPartInstsIter [$lPage NewPartInstsIter $lStatus]
            set lInst [$lPartInstsIter NextPartInst $lStatus]
            while {$lInst!=$lNullObj} {
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lPropNameCStr [DboTclHelper_sMakeCString "Value"]
                set lPropValueCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lPropNameCStr $lPropValueCStr
                set lPropValueString [DboTclHelper_sGetConstCharPtr $lPropValueCStr]
                
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lPropPNNameCStr [DboTclHelper_sMakeCString "Part Number"]
                set lPropPNCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lPropPNNameCStr $lPropPNCStr
                set lPropPNString [DboTclHelper_sGetConstCharPtr $lPropPNCStr]

                # \u5224\u65ad\u662f\u5426\u4e3aNC\u5143\u4ef6
                if { $lPropPNString == "" || [regexp "NC/" $lPropValueString] } {
                    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                    set lColorPropNameCStr [DboTclHelper_sMakeCString "Color"]
                    set lColorPropValueCStr [DboTclHelper_sMakeCString "RGB(192,192,192)"]
                    $lInst SetEffectivePropStringValue $lColorPropNameCStr $lColorPropValueCStr
                    
                    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                    set lPlacedInst [DboPartInstToDboPlacedInst $lInst] 
                    if {$lPlacedInst != $lNullObj} {
                        set lPropsIter [$lPlacedInst NewDisplayPropsIter $lStatus] 
                        set lDProp [$lPropsIter NextProp $lStatus]
                        while {$lDProp !=$lNullObj } { 
                            $lDProp SetColor 45
                            set lDProp [$lPropsIter NextProp $lStatus] 
                        }
                        delete_DboDisplayPropsIter $lPropsIter
                    }
                } else {
                    # \u975eNC\u5143\u4ef6\u6062\u590d\u9ed8\u8ba4\u989c\u8272
                    set lColorPropNameCStr [DboTclHelper_sMakeCString "Color"]
                    set lColorPropValueCStr [DboTclHelper_sMakeCString "Default"]
                    $lInst SetEffectivePropStringValue $lColorPropNameCStr $lColorPropValueCStr
                    
                    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                    set lPlacedInst [DboPartInstToDboPlacedInst $lInst] 
                    if {$lPlacedInst != $lNullObj} {
                        set lPropsIter [$lPlacedInst NewDisplayPropsIter $lStatus] 
                        set lDProp [$lPropsIter NextProp $lStatus]
                        while {$lDProp !=$lNullObj } { 
                            $lDProp SetColor 48
                            set lDProp [$lPropsIter NextProp $lStatus]
                        }
                        delete_DboDisplayPropsIter $lPropsIter
                    }
                }
                
                set lInst [$lPartInstsIter NextPartInst $lStatus]
            }
            delete_DboPagePartInstsIter $lPartInstsIter
            set lPage [$lPagesIter NextPage $lStatus]
        }
        delete_DboSchematicPagesIter $lPagesIter
        set lView [$lSchematicIter NextView $lStatus]
    }
    delete_DboLibViewsIter $lSchematicIter
}


# ////////////////////////////////////////////////////////////////////////////////
# \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
# ////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::GroundNameVisible { pLib } {
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "No active design is open."
        return
    }
    
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    set lView [$lSchematicIter NextView $lStatus]
    set lNullObj NULL

    while { $lView != $lNullObj} {
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]
        while {$lPage!=$lNullObj} {
            set lGlobalsIter [$lPage NewGlobalsIter $lStatus]
            set lGlobal [$lGlobalsIter NextGlobal $lStatus]
            while { $lGlobal!=$lNullObj } {
                set lPropsIter [$lGlobal NewEffectivePropsIter $lStatus] 
                set lPrpName [DboTclHelper_sMakeCString]
                set lPrpValue [DboTclHelper_sMakeCString]
                set lPrpType [DboTclHelper_sMakeDboValueType]
                set lEditable [DboTclHelper_sMakeInt]
                set lStatus [$lPropsIter NextEffectiveProp $lPrpName $lPrpValue $lPrpType $lEditable]

                while { [$lStatus OK] } { 
                    set propName [DboTclHelper_sGetConstCharPtr $lPrpName]
                    if {$propName eq "Name"} {
                        set netName [DboTclHelper_sGetConstCharPtr $lPrpValue]
                        # \u5df2\u751f\u6210\u7684\u968f\u673a\u540d\u79f0\u96c6\u5408\uff0c\u786e\u4fdd\u552f\u4e00\u6027
                        if { [regexp "GND" $netName] || $netName == "0" } {
                            set varNullObj NULL
                            set pDispProp [$lGlobal GetDisplayProp $lPrpName $lStatus]
                            if { $pDispProp == $varNullObj } {
                                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                                set rotation 0
                                set logfont [DboTclHelper_sMakeLOGFONT]
                                set lColor $::DboValue_DEFAULT_OBJECT_COLOR
                                set displocation [DboTclHelper_sMakeCPoint 0 10]
                                set pNewDispProp [$lGlobal NewDisplayProp $lStatus $lPrpName $displocation $rotation $logfont $lColor]
                                $pNewDispProp SetDisplayType 1 ;# VALUE_ONLY
                            } else {
                                # \u5df2\u6709\u5c5e\u6027\uff0c\u5f3a\u5236\u663e\u793aValue
                                $pDispProp SetDisplayType 1
                            }
                        }
                    }
                    set lStatus [$lPropsIter NextEffectiveProp $lPrpName $lPrpValue $lPrpType $lEditable]
                }
                delete_DboEffectivePropsIter $lPropsIter
                
                set lGlobal [$lGlobalsIter NextGlobal $lStatus]
            }
            delete_DboPageGlobalsIter $lGlobalsIter
            set lPage [$lPagesIter NextPage $lStatus]
        }
        delete_DboSchematicPagesIter $lPagesIter
        set lView [$lSchematicIter NextView $lStatus]
    }
    delete_DboLibViewsIter $lSchematicIter
}

# ////////////////////////////////////////////////////////////////////////////////
# \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
# ////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::ResetNetnameColor { pLib } {
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "No active design is open."
        return
    }
    
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    set lView [$lSchematicIter NextView $lStatus]
    set lNullObj NULL

    while { $lView != $lNullObj} {
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]

        while {$lPage!=$lNullObj} {
            # \u91cd\u7f6e\u5bfc\u7ebf\u522b\u540d\u989c\u8272
            set lWiresIter [$lPage NewWiresIter $lStatus]
            set lWire [$lWiresIter NextWire $lStatus]
            while {$lWire!=$lNullObj} {
                set lAliasIter [$lWire NewAliasesIter $lStatus]
                set lAlias [$lAliasIter NextAlias $lStatus]
                while { $lAlias!=$lNullObj} {
                    set lColorPropNameCStr [DboTclHelper_sMakeCString "Color"]
                    set lColorPropValueCStr [DboTclHelper_sMakeCString "Default"]
                    $lAlias SetEffectivePropStringValue $lColorPropNameCStr $lColorPropValueCStr
                    
                    set lAlias [$lAliasIter NextAlias $lStatus]
                }
                delete_DboWireAliasesIter $lAliasIter
                set lWire [$lWiresIter NextWire $lStatus]
            }
            delete_DboPageWiresIter $lWiresIter

            # \u91cd\u7f6e\u9875\u95f4\u8fde\u63a5\u989c\u8272
            set lOffPagesIter [$lPage NewOffPageConnectorsIter $lStatus]
            set lOffPage [$lOffPagesIter NextOffPageConnector $lStatus]
            while {$lOffPage!=$lNullObj} {
                set lColorPropNameCStr [DboTclHelper_sMakeCString "Color"]
                set lColorPropValueCStr [DboTclHelper_sMakeCString "Default"]
                $lOffPage SetEffectivePropStringValue $lColorPropNameCStr $lColorPropValueCStr
                
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lPropsIter [$lOffPage NewDisplayPropsIter $lStatus] 
                set lDProp [$lPropsIter NextProp $lStatus]
                while {$lDProp !=$lNullObj } { 
                    $lDProp SetColor 48
                    set lDProp [$lPropsIter NextProp $lStatus] 
                }
                delete_DboDisplayPropsIter $lPropsIter
                
                set lOffPage [$lOffPagesIter NextOffPageConnector $lStatus]
            }
            delete_DboPageOffPageConnectorsIter $lOffPagesIter

            # \u91cd\u7f6e\u7aef\u53e3\u989c\u8272
            set lPortsIter [$lPage NewPortsIter $lStatus]
            set lPort [$lPortsIter NextPort $lStatus]
            while {$lPort!=$lNullObj} {
                set lColorPropNameCStr [DboTclHelper_sMakeCString "Color"]
                set lColorPropValueCStr [DboTclHelper_sMakeCString "Default"]
                $lPort SetEffectivePropStringValue $lColorPropNameCStr $lColorPropValueCStr
                
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lPropsIter [$lPort NewDisplayPropsIter $lStatus] 
                set lDProp [$lPropsIter NextProp $lStatus]
                while {$lDProp !=$lNullObj } { 
                    $lDProp SetColor 48
                    set lDProp [$lPropsIter NextProp $lStatus] 
                }
                delete_DboDisplayPropsIter $lPropsIter
                
                set lPort [$lPortsIter NextPort $lStatus]
            }
            delete_DboPagePortsIter $lPortsIter

            set lPage [$lPagesIter NextPage $lStatus]
        }
        delete_DboSchematicPagesIter $lPagesIter
        set lView [$lSchematicIter NextView $lStatus]
    }
    delete_DboLibViewsIter $lSchematicIter
}

# ////////////////////////////////////////////////////////////////////////////////
# \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
# ////////////////////////////////////////////////////////////////////////////////
# 1. \u968f\u673a\u5b57\u7b26\u4e32\u751f\u6210\u5668 - \u517c\u5bb9Tcl 8.4/8.5

# ////////////////////////////////////////////////////////////////////////////////
# \u5b89\u5168\u53cd\u64cd\u4f5c\uff1a\u9690\u85cf/\u663e\u793a\u7c7b\u64cd\u4f5c\uff0c\u4ec5\u5207\u6362\u663e\u793a\u5c5e\u6027\uff0c\u4e0d\u505a\u5feb\u7167\u6062\u590d\u3002
# ////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::GroundNameHidden { pLib } {
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "No active design is open."
        return
    }

    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    set lView [$lSchematicIter NextView $lStatus]
    set lNullObj NULL

    while {$lView != $lNullObj} {
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]
        while {$lPage != $lNullObj} {
            set lGlobalsIter [$lPage NewGlobalsIter $lStatus]
            set lGlobal [$lGlobalsIter NextGlobal $lStatus]
            while {$lGlobal != $lNullObj} {
                set lPropsIter [$lGlobal NewEffectivePropsIter $lStatus]
                set lPrpName [DboTclHelper_sMakeCString]
                set lPrpValue [DboTclHelper_sMakeCString]
                set lPrpType [DboTclHelper_sMakeDboValueType]
                set lEditable [DboTclHelper_sMakeInt]
                set lStatus [$lPropsIter NextEffectiveProp $lPrpName $lPrpValue $lPrpType $lEditable]
                while {[$lStatus OK]} {
                    set propName [DboTclHelper_sGetConstCharPtr $lPrpName]
                    if {$propName eq "Name"} {
                        set netName [DboTclHelper_sGetConstCharPtr $lPrpValue]
                        if {[regexp "GND" $netName] || $netName == "0"} {
                            set pDispProp [$lGlobal GetDisplayProp $lPrpName $lStatus]
                            if {$pDispProp != $lNullObj} {
                                $pDispProp SetDisplayType 0
                            }
                        }
                    }
                    set lStatus [$lPropsIter NextEffectiveProp $lPrpName $lPrpValue $lPrpType $lEditable]
                }
                delete_DboEffectivePropsIter $lPropsIter
                set lGlobal [$lGlobalsIter NextGlobal $lStatus]
            }
            delete_DboPageGlobalsIter $lGlobalsIter
            set lPage [$lPagesIter NextPage $lStatus]
        }
        delete_DboSchematicPagesIter $lPagesIter
        set lView [$lSchematicIter NextView $lStatus]
    }
    delete_DboLibViewsIter $lSchematicIter
}

proc ::capMenuUtil::setUPinNameDisplayType { pLib displayType } {
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    set lNullObj NULL
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "No active design is open."
        return
    }

    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }

    set lView [$lSchematicIter NextView $lStatus]
    while {$lView != $lNullObj} {
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]
        while {$lPage != $lNullObj} {
            set lPartInstsIter [$lPage NewPartInstsIter $lStatus]
            set lInst [$lPartInstsIter NextPartInst $lStatus]
            while {$lInst != $lNullObj} {
                set lRefName [DboTclHelper_sMakeCString "Reference"]
                set lRefValue [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lRefName $lRefValue
                set refDes [DboTclHelper_sGetConstCharPtr $lRefValue]
                if {[regexp -nocase {^U} $refDes]} {
                    set lPlacedInst [DboPartInstToDboPlacedInst $lInst]
                    if {$lPlacedInst != $lNullObj} {
                        set pinProp [DboTclHelper_sMakeCString "Name"]
                        set lPinsIter [$lPlacedInst NewPinsIter $lStatus]
                        set lPin [$lPinsIter NextPin $lStatus]
                        while {$lPin != $lNullObj} {
                            set dispProp [$lPin GetDisplayProp $pinProp $lStatus]
                              if {$dispProp != $lNullObj} {
                                  catch {$dispProp SetDisplayType $displayType}
                              }
                            set lPin [$lPinsIter NextPin $lStatus]
                        }
                        catch {delete_DboPlacedInstPinsIter $lPinsIter}
                        catch {DboTclHelper_sDeleteCString $pinProp}
                    }
                }
                DboTclHelper_sDeleteCString $lRefName
                DboTclHelper_sDeleteCString $lRefValue
                set lInst [$lPartInstsIter NextPartInst $lStatus]
            }
            delete_DboPagePartInstsIter $lPartInstsIter
            set lPage [$lPagesIter NextPage $lStatus]
        }
        delete_DboSchematicPagesIter $lPagesIter
        set lView [$lSchematicIter NextView $lStatus]
    }
    delete_DboLibViewsIter $lSchematicIter
}

proc ::capMenuUtil::ShowUPinNames { pLib } {
    ::capMenuUtil::setUPinNameDisplayType $pLib 1
}

proc ::capMenuUtil::setPartValueDisplayType { pLib onlyU displayType } {
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    set lNullObj NULL
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "No active design is open."
        return
    }

    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }

    set lView [$lSchematicIter NextView $lStatus]
    while {$lView != $lNullObj} {
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]
        while {$lPage != $lNullObj} {
            set lPartInstsIter [$lPage NewPartInstsIter $lStatus]
            set lInst [$lPartInstsIter NextPartInst $lStatus]
            while {$lInst != $lNullObj} {
                set shouldHandle 1
                set lRefDesNameCStr [DboTclHelper_sMakeCString "Reference"]
                set lRefDesValueCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lRefDesNameCStr $lRefDesValueCStr
                set lRefDesString [DboTclHelper_sGetConstCharPtr $lRefDesValueCStr]
                if {$onlyU && ![regexp -nocase {^U} $lRefDesString]} {
                    set shouldHandle 0
                }

                if {$shouldHandle} {
                    set lPlacedInst [DboPartInstToDboPlacedInst $lInst]
                    if {$lPlacedInst != $lNullObj} {
                        set lDisplayPropsIter [$lPlacedInst NewDisplayPropsIter $lStatus]
                        set lDProp [$lDisplayPropsIter NextProp $lStatus]
                        while {$lDProp != $lNullObj} {
                            set lNameCStr [DboTclHelper_sMakeCString]
                            $lDProp GetName $lNameCStr
                            set lNameString [DboTclHelper_sGetConstCharPtr $lNameCStr]
                            if {[string equal -nocase $lNameString "Value"]} {
                                catch {$lDProp SetDisplayType $displayType}
                            }
                            DboTclHelper_sDeleteCString $lNameCStr
                            set lDProp [$lDisplayPropsIter NextProp $lStatus]
                        }
                        delete_DboDisplayPropsIter $lDisplayPropsIter
                    }
                }

                DboTclHelper_sDeleteCString $lRefDesNameCStr
                DboTclHelper_sDeleteCString $lRefDesValueCStr
                set lInst [$lPartInstsIter NextPartInst $lStatus]
            }
            delete_DboPagePartInstsIter $lPartInstsIter
            set lPage [$lPagesIter NextPage $lStatus]
        }
        delete_DboSchematicPagesIter $lPagesIter
        set lView [$lSchematicIter NextView $lStatus]
    }
    delete_DboLibViewsIter $lSchematicIter
}

proc ::capMenuUtil::ShowUcomponent { pLib } {
    ::capMenuUtil::setPartValueDisplayType $pLib 1 1
}

proc ::capMenuUtil::ShowALLcomponent { pLib } {
    ::capMenuUtil::setPartValueDisplayType $pLib 0 1
    ::capMenuUtil::ShowSensitiveComponentProperties $pLib
}

proc ::capMenuUtil::RestorePartDefaultColor { pLib } {
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    set lNullObj NULL
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "No active design is open."
        return
    }

    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }

    set lColorPropNameCStr [DboTclHelper_sMakeCString "Color"]
    set lColorPropValueCStr [DboTclHelper_sMakeCString "Default"]

    set lView [$lSchematicIter NextView $lStatus]
    while {$lView != $lNullObj} {
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]
        while {$lPage != $lNullObj} {
            set lPartInstsIter [$lPage NewPartInstsIter $lStatus]
            set lInst [$lPartInstsIter NextPartInst $lStatus]
            while {$lInst != $lNullObj} {
                catch {$lInst SetEffectivePropStringValue $lColorPropNameCStr $lColorPropValueCStr}
                set lPlacedInst [DboPartInstToDboPlacedInst $lInst]
                if {$lPlacedInst != $lNullObj} {
                    set lPropsIter [$lPlacedInst NewDisplayPropsIter $lStatus]
                    set lDProp [$lPropsIter NextProp $lStatus]
                    while {$lDProp != $lNullObj} {
                        catch {$lDProp SetColor 48}
                        set lDProp [$lPropsIter NextProp $lStatus]
                    }
                    delete_DboDisplayPropsIter $lPropsIter
                }
                set lInst [$lPartInstsIter NextPartInst $lStatus]
            }
            delete_DboPagePartInstsIter $lPartInstsIter
            set lPage [$lPagesIter NextPage $lStatus]
        }
        delete_DboSchematicPagesIter $lPagesIter
        set lView [$lSchematicIter NextView $lStatus]
    }

    DboTclHelper_sDeleteCString $lColorPropNameCStr
    DboTclHelper_sDeleteCString $lColorPropValueCStr
    delete_DboLibViewsIter $lSchematicIter
}
proc ::capMenuUtil::generateRandomString {} {
    variable generatedNames
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    set prefix "XX_"
    set chars "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    set charCount [string length $chars]
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    while {1} {
        set str $prefix
        # \u5df2\u751f\u6210\u7684\u968f\u673a\u540d\u79f0\u96c6\u5408\uff0c\u786e\u4fdd\u552f\u4e00\u6027
        for {set i 0} {$i < 8} {incr i} {
            append str [string index $chars [expr {int(rand() * $charCount)}]]
        }
        
        # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
        if {[lsearch $generatedNames $str] == -1} {
            lappend generatedNames $str
            return $str
        }
    }
}

# \u5df2\u751f\u6210\u7684\u968f\u673a\u540d\u79f0\u96c6\u5408\uff0c\u786e\u4fdd\u552f\u4e00\u6027
proc ::capMenuUtil::normalizeNetName {netName} {
    # \u53bb\u9664\u524d\u540e\u7a7a\u683c\u5e76\u8f6c\u4e3a\u5927\u5199\uff0c\u786e\u4fdd\u76f8\u540c\u7f51\u7edc\u7684\u4e0d\u540c\u8868\u793a\u5f62\u5f0f\u88ab\u8bc6\u522b\u4e3a\u540c\u4e00\u7f51\u7edc
    return [string trim [string toupper $netName]]
}

# \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
proc ::capMenuUtil::showNetExchangeProgressDialog {totalPages oldString newString} {
    set progressWindow .netExchangeProgress
    if {[winfo exists $progressWindow]} {
        destroy $progressWindow
    }

    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    toplevel $progressWindow
    wm title $progressWindow "Replace Net Names"
    wm resizable $progressWindow 0 0
    wm attributes $progressWindow -toolwindow 1
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    # wm transient $progressWindow .
    # \u5bee\u54c4\u57d7\u93c4\u5267\u305a\u9a9e\u5241\u7586\u6924?
    wm deiconify $progressWindow
    raise $progressWindow
    focus $progressWindow

    # \u8bbe\u7f6e\u5b57\u4f53\u548c\u989c\u8272\uff08\u517c\u5bb916.6\u7684\u9ed8\u8ba4\u5b57\u4f53\uff09
    set font {TkDefaultFont 10}
    set bgColor "#f0f0f0"
    set fgColor "#333333"
    
    # \u914d\u7f6e\u7a97\u53e3\u6837\u5f0f
    $progressWindow configure -bg $bgColor
    
    # \u521b\u5efa\u5185\u5bb9\u6846\u67b6
    set contentFrame [frame $progressWindow.content -bg $bgColor -padx 20 -pady 20]
    pack $contentFrame -fill both -expand 1
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    label $contentFrame.label -text "Replacing net names..." \
        -font $font -fg $fgColor -bg $bgColor
    pack $contentFrame.label -pady 5
    
    # \u663e\u793a\u66ff\u6362\u4fe1\u606f
    label $contentFrame.replaceInfo -text "Replacing: \"$oldString\" -> \"$newString\"" \
        -font [list TkDefaultFont 9] -fg $fgColor -bg $bgColor -wraplength 300
    pack $contentFrame.replaceInfo -pady 5
    
    # \u6dfb\u52a0\u8fdb\u5ea6\u6587\u672c
    label $contentFrame.status -text "Page 0 / $totalPages" \
        -font [list TkDefaultFont 9] -fg $fgColor -bg $bgColor
    pack $contentFrame.status -pady 5
    
    # \u4f7f\u7528\u4f20\u7edf\u8fdb\u5ea6\u6761\uff08\u4e0d\u4f7f\u7528ttk\uff0c\u517c\u5bb9\u65e7\u7248\u672cTk)
    frame $contentFrame.progress -relief sunken -bd 1 -width 300 -height 20
    canvas $contentFrame.progress.canvas -width 296 -height 16 -bg white
    $contentFrame.progress.canvas create rectangle 0 0 0 16 -fill blue -outline blue -tags bar
    pack $contentFrame.progress.canvas -fill both -expand 1
    pack $contentFrame.progress -pady 10 -fill x
    
    # \u6dfb\u52a0\u8bf4\u660e\u6587\u5b57
    label $contentFrame.note -text "Please wait. Do not close OrCAD..." \
        -font [list TkDefaultFont 8] -fg "#666666" -bg $bgColor -wraplength 300
    pack $contentFrame.note -pady 5
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    update

    # \u5c45\u4e2d\u663e\u793a\u5f39\u7a97
    update idletasks
    set x [expr {([winfo screenwidth .] - [winfo reqwidth $progressWindow]) / 2}]
    set y [expr {([winfo screenheight .] - [winfo reqheight $progressWindow]) / 2}]
    wm geometry $progressWindow "+$x+$y"

    # \u5f3a\u5236\u5904\u7406\u6240\u6709\u6302\u8d77\u7684\u4e8b\u4ef6
    update

    return $progressWindow
}

# 4. \u521b\u5efa\u5e76\u663e\u793a\u968f\u673a\u5316\u5904\u7406\u5f39\u7a97\uff08\u4f18\u5316\u663e\u793a\uff09
proc ::capMenuUtil::showProcessingDialog {totalPages} {
    set progressWindow .randomizeProgress
    if {[winfo exists $progressWindow]} {
        destroy $progressWindow
    }

    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    toplevel $progressWindow
    wm title $progressWindow "Processing"
    wm resizable $progressWindow 0 0
    wm attributes $progressWindow -toolwindow 1
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    # wm transient $progressWindow .
    # \u5bee\u54c4\u57d7\u93c4\u5267\u305a\u9a9e\u5241\u7586\u6924?
    wm deiconify $progressWindow
    raise $progressWindow
    focus $progressWindow

    # \u8bbe\u7f6e\u5b57\u4f53\u548c\u989c\u8272\uff08\u517c\u5bb916.6\u7684\u9ed8\u8ba4\u5b57\u4f53\uff09
    set font {TkDefaultFont 10}
    set bgColor "#f0f0f0"
    set fgColor "#333333"
    
    # \u914d\u7f6e\u7a97\u53e3\u6837\u5f0f
    $progressWindow configure -bg $bgColor
    
    # \u521b\u5efa\u5185\u5bb9\u6846\u67b6
    set contentFrame [frame $progressWindow.content -bg $bgColor -padx 20 -pady 20]
    pack $contentFrame -fill both -expand 1
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    label $contentFrame.label -text "Randomizing net names..." \
        -font $font -fg $fgColor -bg $bgColor
    pack $contentFrame.label -pady 5
    
    # \u6dfb\u52a0\u8fdb\u5ea6\u6587\u672c
    label $contentFrame.status -text "Page 0 / $totalPages" \
        -font [list TkDefaultFont 9] -fg $fgColor -bg $bgColor
    pack $contentFrame.status -pady 5
    
    # \u4f7f\u7528\u4f20\u7edf\u8fdb\u5ea6\u6761\uff08\u4e0d\u4f7f\u7528ttk\uff0c\u517c\u5bb9\u65e7\u7248\u672cTk)
    frame $contentFrame.progress -relief sunken -bd 1 -width 300 -height 20
    canvas $contentFrame.progress.canvas -width 296 -height 16 -bg white
    $contentFrame.progress.canvas create rectangle 0 0 0 16 -fill blue -outline blue -tags bar
    pack $contentFrame.progress.canvas -fill both -expand 1
    pack $contentFrame.progress -pady 10 -fill x
    
    # \u6dfb\u52a0\u8bf4\u660e\u6587\u5b57
    label $contentFrame.note -text "Please wait. Do not close OrCAD..." \
        -font [list TkDefaultFont 8] -fg "#666666" -bg $bgColor -wraplength 300
    pack $contentFrame.note -pady 5
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    update

    # \u5c45\u4e2d\u663e\u793a\u5f39\u7a97
    update idletasks
    set x [expr {([winfo screenwidth .] - [winfo reqwidth $progressWindow]) / 2}]
    set y [expr {([winfo screenheight .] - [winfo reqheight $progressWindow]) / 2}]
    wm geometry $progressWindow "+$x+$y"

    # \u5f3a\u5236\u5904\u7406\u6240\u6709\u6302\u8d77\u7684\u4e8b\u4ef6
    update

    return $progressWindow

}

# \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
proc ::capMenuUtil::updateProgress {progressWindow current total} {
    set statusText "Page $current / $total"
    $progressWindow.content.status configure -text $statusText
    
    # \u7481\uff04\u757b\u6769\u6d98\u5bb3\u9427\u60e7\u578e\u59e3?
    set percent [expr {double($current) / $total}]
    set width [expr {int(296 * $percent)}]
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    $progressWindow.content.progress.canvas coords bar 0 0 $width 16
    
    # \u5f3a\u5236\u66f4\u65b0\u754c\u9762
    update idletasks
}

# \u5df2\u751f\u6210\u7684\u968f\u673a\u540d\u79f0\u96c6\u5408\uff0c\u786e\u4fdd\u552f\u4e00\u6027
proc ::capMenuUtil::countTotalPages {lDesign lStatus} {
    set totalPages 0
    set lNullObj NULL
    
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    set lView [$lSchematicIter NextView $lStatus]
    
    while { $lView != $lNullObj} {
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]
        
        while {$lPage != $lNullObj} {
            incr totalPages
            set lPage [$lPagesIter NextPage $lStatus]
        }
        
        delete_DboSchematicPagesIter $lPagesIter
        set lView [$lSchematicIter NextView $lStatus]
    }
    
    delete_DboLibViewsIter $lSchematicIter
    return $totalPages
}

# \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
proc ::capMenuUtil::RandomizeNetNames {pLib} {
    
    
    # \u521d\u59cb\u5316\u7f13\u5b58\uff08\u4f7f\u7528list\u66ff\u4ee3dict\uff0c\u517c\u5bb9Tcl 8.4\u7684\u9650\u5236\uff09
    variable netNameMap
    variable generatedNames
    set netNameMap [list]
    catch {array unset netNameMapArray}
    array set netNameMapArray {}
    set generatedNames [list]
    
    # \u83b7\u53d6\u8bbe\u8ba1\u4fe1\u606f
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    
    # \u68c0\u67e5\u662f\u5426\u6709\u6d3b\u52a8\u8bbe\u8ba1
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "No active design is open.\nOpen a design first."
        return
    }
    
    # \u8ba1\u7b97\u603b\u9875\u9762\u6570\u7528\u4e8e\u8fdb\u5ea6\u663e\u793a
    set totalPages [::capMenuUtil::countTotalPages $lDesign $lStatus]
    if {$totalPages == 0} {
        tk_messageBox -icon warning -message "No pages were found in the current design."
        return
    }
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    set progressWindow [::capMenuUtil::showProcessingDialog $totalPages]
    set currentPage 0
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    update
    
    # \u517c\u5bb916.6\u7684\u8fed\u4ee3\u5668\u521b\u5efa\u65b9\u5f0f
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    set lView [$lSchematicIter NextView $lStatus]
    set lNullObj NULL
    set SchNum 0                      ;# \u539f\u7406\u56fe\u8ba1\u6570\u5668
    
    # \u6b65\u9aa42\uff1a\u904d\u5386\u6240\u6709\u539f\u7406\u56fe
    while {$lView != $lNullObj} {
        incr SchNum
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]
        set PageNum 0                  ;# \u6924\u7538\u6f70\u7481\u2103\u669f\u9363?

        # \u59dd\u30e9\ue0033\u951b\u6c36\u4eb6\u9358\u55d7\u7d8b\u9353\u5d85\u5e2b\u941e\u55d7\u6d58\u9428\u52ec\u588d\u93c8\u5910\u3009\u95c8?
        while {$lPage != $lNullObj} {
            incr PageNum
            incr currentPage
            
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            ::capMenuUtil::updateProgress $progressWindow $currentPage $totalPages
            
            puts "\n===================== Processing Schematic $SchNum, Page $PageNum ====================="

            # //////////////////////////////////////////////////////////////////////
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            # //////////////////////////////////////////////////////////////////////
            puts "\n[clock format [clock seconds] -format {%H:%M:%S}] - Processing Wire Aliases..."
            set lWiresIter [$lPage NewWiresIter $lStatus]
            set lWire [$lWiresIter NextWire $lStatus] 
            
            while {$lWire != $lNullObj} {
                set lAliasIter [$lWire NewAliasesIter $lStatus]
                set lAlias [$lAliasIter NextAlias $lStatus]
                
                while { $lAlias != $lNullObj } {
                    # \u5df2\u751f\u6210\u7684\u968f\u673a\u540d\u79f0\u96c6\u5408\uff0c\u786e\u4fdd\u552f\u4e00\u6027
                    set lAliasString [DboTclHelper_sMakeCString]
                    $lAlias GetName $lAliasString
                    set lNameString [DboTclHelper_sGetConstCharPtr $lAliasString]
                    
                    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                    if {![string match "XX_*" $lNameString] && $lNameString ne ""} {
                        # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                        set normalizedName [::capMenuUtil::normalizeNetName $lNameString]
                        
                        if {[info exists netNameMapArray($normalizedName)]} {
                            set newName $netNameMapArray($normalizedName)
                            ::capMenuUtil::logDebug "Using cached mapping: $lNameString -> $newName"
                        } else {
                            set newName [::capMenuUtil::generateRandomString]
                            set netNameMapArray($normalizedName) $newName
                            lappend netNameMap [list $normalizedName $newName]
                            ::capMenuUtil::logDebug "Mapping new network: $lNameString -> $newName"
                        }
                        
                        # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                        set lNewName [DboTclHelper_sMakeCString $newName]
                        $lAlias SetName $lNewName
                    }
                    
                    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                    set lAlias [$lAliasIter NextAlias $lStatus]
                }
                
                delete_DboWireAliasesIter $lAliasIter
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lWire [$lWiresIter NextWire $lStatus] 
            }
            
            delete_DboPageWiresIter $lWiresIter
            puts "[clock format [clock seconds] -format {%H:%M:%S}] - Wire Aliases processed"

            # //////////////////////////////////////////////////////////////////////
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            # //////////////////////////////////////////////////////////////////////
            puts "\n[clock format [clock seconds] -format {%H:%M:%S}] - Processing Ports..."
            set lPortsIter [$lPage NewPortsIter $lStatus]
            set lPort [$lPortsIter NextPort $lStatus]
            
            while {$lPort != $lNullObj} {
                set lPortString [DboTclHelper_sMakeCString]
                $lPort GetName $lPortString
                set lNameString [DboTclHelper_sGetConstCharPtr $lPortString]
                
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                if {![string match "XX_*" $lNameString] && $lNameString ne ""} {
                    set normalizedName [::capMenuUtil::normalizeNetName $lNameString]
                    
                    if {[info exists netNameMapArray($normalizedName)]} {
                        set newName $netNameMapArray($normalizedName)
                        ::capMenuUtil::logDebug "Using cached mapping: $lNameString -> $newName"
                    } else {
                        set newName [::capMenuUtil::generateRandomString]
                        set netNameMapArray($normalizedName) $newName
                        lappend netNameMap [list $normalizedName $newName]
                        ::capMenuUtil::logDebug "Mapping new port: $lNameString -> $newName"
                    }
                    
                    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                    set lNewName [DboTclHelper_sMakeCString $newName]
                    $lPort SetName $lNewName
                }

                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lPort [$lPortsIter NextPort $lStatus]
            }  
            
            delete_DboPagePortsIter $lPortsIter
            puts "[clock format [clock seconds] -format {%H:%M:%S}] - Ports processed"

            # //////////////////////////////////////////////////////////////////////
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            # //////////////////////////////////////////////////////////////////////
            puts "\n[clock format [clock seconds] -format {%H:%M:%S}] - Processing Offpage Connectors..."
            # \u934f\u714e\ue19016.6\u9428\u51eeffPage\u6769\ue15d\u552c\u9363\u3125\u5f2c\u93c1?
            if {[info exists ::IterDefs_ALL]} {
                set lOffPagesIter [$lPage NewOffPageConnectorsIter $lStatus $::IterDefs_ALL]
            } else {
                set lOffPagesIter [$lPage NewOffPageConnectorsIter $lStatus]
            }
            set lOffPage [$lOffPagesIter NextOffPageConnector $lStatus]
            
            while {$lOffPage != $lNullObj} {
                set lOffPageString [DboTclHelper_sMakeCString]
                $lOffPage GetName $lOffPageString
                set lNameString [DboTclHelper_sGetConstCharPtr $lOffPageString]
                
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                if {![string match "XX_*" $lNameString] && $lNameString ne ""} {
                    set normalizedName [::capMenuUtil::normalizeNetName $lNameString]
                    
                    if {[info exists netNameMapArray($normalizedName)]} {
                        set newName $netNameMapArray($normalizedName)
                        ::capMenuUtil::logDebug "Using cached mapping: $lNameString -> $newName"
                    } else {
                        set newName [::capMenuUtil::generateRandomString]
                        set netNameMapArray($normalizedName) $newName
                        lappend netNameMap [list $normalizedName $newName]
                        ::capMenuUtil::logDebug "Mapping new offpage: $lNameString -> $newName"
                    }
                    
                    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                    set lNewName [DboTclHelper_sMakeCString $newName]
                    $lOffPage SetName $lNewName
                }
                
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lOffPage [$lOffPagesIter NextOffPageConnector $lStatus]
            }
            
            delete_DboPageOffPageConnectorsIter $lOffPagesIter
            puts "[clock format [clock seconds] -format {%H:%M:%S}] - Offpage Connectors processed"

            # //////////////////////////////////////////////////////////////////////
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            # //////////////////////////////////////////////////////////////////////
            puts "\n[clock format [clock seconds] -format {%H:%M:%S}] - Processing Power..."
            set lGlobalsIter [$lPage NewGlobalsIter $lStatus]
            set lGlobal [$lGlobalsIter NextGlobal $lStatus]
            
            while { $lGlobal != $lNullObj } { 
                set lPropsIter [$lGlobal NewEffectivePropsIter $lStatus]
                set lPrpName [DboTclHelper_sMakeCString]
                set lPrpValue [DboTclHelper_sMakeCString]
                set lPrpType [DboTclHelper_sMakeDboValueType]
                set lEditable [DboTclHelper_sMakeInt]
                set lStatus [$lPropsIter NextEffectiveProp $lPrpName $lPrpValue $lPrpType $lEditable]
                
                while { [$lStatus OK] } {
                    set propName [DboTclHelper_sGetConstCharPtr $lPrpName]
                    if {$propName eq "Name"} {
                        set lNameString [DboTclHelper_sGetConstCharPtr $lPrpValue]
                        
                        # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                        set isFilePath [expr {[string match "*:*" $lNameString] || [string match "*\\*" $lNameString] || [string match "*/*" $lNameString]}]
                        set isNumeric [expr {[string is digit $lNameString]}]
                        
                        # \u8fc7\u6ee4\u6761\u4ef6\uff1a\u4e0d\u662fXX_\u524d\u7f00\u3001\u4e0d\u5305\u542bGND\u3001\u4e0d\u662f\u9ed8\u8ba4\u503c\u3001\u4e0d\u662f\u6587\u4ef6\u8def\u5f84\u3001\u4e0d\u662f\u7eaf\u6570\u5b57
                        if {![string match "XX_*" $lNameString] && ![string match -nocase "*GND*" $lNameString] && 
                            ![string match "Default" $lNameString] && !$isFilePath && !$isNumeric && $lNameString ne ""} {
                            
                            set normalizedName [::capMenuUtil::normalizeNetName $lNameString]
                            
                            if {[info exists netNameMapArray($normalizedName)]} {
                                set newName $netNameMapArray($normalizedName)
                                ::capMenuUtil::logDebug "Using cached mapping: $lNameString -> $newName"
                            } else {
                                set newName [::capMenuUtil::generateRandomString]
                                set netNameMapArray($normalizedName) $newName
                                lappend netNameMap [list $normalizedName $newName]
                                ::capMenuUtil::logDebug "Mapping new power: $lNameString -> $newName"
                            }
                            
                            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                            set lNewName [DboTclHelper_sMakeCString $newName]
                            $lGlobal SetEffectivePropStringValue $lPrpName $lNewName
                        }
                    }
                
                    set lStatus [$lPropsIter NextEffectiveProp $lPrpName $lPrpValue $lPrpType $lEditable]
                }
                
                delete_DboEffectivePropsIter $lPropsIter			
                # \u83b7\u53d6\u4e0b\u4e00\u4e2a\u5168\u5c40\u5bf9\u8c61
                set lGlobal [$lGlobalsIter NextGlobal $lStatus]
            }
            
            delete_DboPageGlobalsIter $lGlobalsIter
            puts "[clock format [clock seconds] -format {%H:%M:%S}] - Power/Ground processed"

            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            set lPage [$lPagesIter NextPage $lStatus]
        }
        
        delete_DboSchematicPagesIter $lPagesIter
        # \u5904\u7406\u4e0b\u4e00\u4e2a\u539f\u7406\u56fe
        set lView [$lSchematicIter NextView $lStatus]
    }
    
    delete_DboLibViewsIter $lSchematicIter

    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    destroy $progressWindow

    
}


# \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
proc ::capMenuUtil::DeleteAllGraphic { pLib } {
    
	
	# \u521d\u59cb\u5316\u72b6\u6001\u5bf9\u8c61\u4e0e\u7a7a\u5bf9\u8c61\u6807\u8bc6\uff08\u6587\u68633.2\u8282\u6807\u51c6\u64cd\u4f5c\uff09
    set lStatus [DboState]
    set lNullObj NULL
    set lDeletedCount 0

    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    set lDesign [GetActivePMDesign]
    if {$lDesign == $lNullObj} {
        puts "Error: No active design is open. Please open a design first."
        $lStatus -delete
        return
    }
	# \u8ba1\u7b97\u603b\u9875\u9762\u6570\u7528\u4e8e\u8fdb\u5ea6\u663e\u793a
    set totalPages [::capMenuUtil::countTotalPages $lDesign $lStatus]
    if {$totalPages == 0} {
        tk_messageBox -icon warning -message "No pages were found in the current design."
        $lStatus -delete
        return
    }
	# \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    set progressWindow [::capMenuUtil::showDeleteGraphicProgressDialog $totalPages]
    set currentPage 0
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    update
	

    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    set lView [$lSchematicIter NextView $lStatus]

    while { $lView != $lNullObj } {
        # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
        set lSchematic [DboViewToDboSchematic $lView]
        
        # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]

        while { $lPage != $lNullObj } {
		    incr currentPage
            # \u66f4\u65b0\u8fdb\u5ea6
            ::capMenuUtil::updateProgress $progressWindow $currentPage $totalPages
			
            # \u5148\u6536\u96c6\u6240\u6709\u9700\u8981\u5220\u9664\u7684\u56fe\u5f62\u5bf9\u8c61\uff0c\u7136\u540e\u518d\u7edf\u4e00\u5220\u9664\uff08\u907f\u514d\u8fed\u4ee3\u5668\u72b6\u6001\u95ee\u9898\uff09
            set bitmapsToDelete [list]
            
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            set lGraphicsIter [$lPage NewCommentGraphicsIter $lStatus]
            set lGraphic [$lGraphicsIter NextCommentGraphic $lStatus]
            while { $lGraphic != $lNullObj } {
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lObjType [$lGraphic GetObjectType]
				
                if {$lObjType == $::DboBaseObject_GRAPHIC_BITMAP_INST||$::DboBaseObject_GRAPHIC_LINE_INST||$::DboBaseObject_GRAPHIC_BOX_INST||$::DboBaseObject_GRAPHIC_ARC_INST||$::DboBaseObject_GRAPHIC_BEZIER_INST} {
                    # \u5df2\u751f\u6210\u7684\u968f\u673a\u540d\u79f0\u96c6\u5408\uff0c\u786e\u4fdd\u552f\u4e00\u6027
					
                    set lImageName [DboTclHelper_sMakeCString]
                    $lGraphic GetName $lImageName  
					
                    set lImageNameStr [DboTclHelper_sGetConstCharPtr $lImageName]
                    ::capMenuUtil::logDebug "Found Graphic: $lImageNameStr"
                    
                    # \u6dfb\u52a0\u5230\u5f85\u5220\u9664\u5217\u8868
                    lappend bitmapsToDelete $lGraphic
                }
                
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lGraphic [$lGraphicsIter NextCommentGraphic $lStatus]
            }

            # \u95b2\u5a43\u6581\u9365\u60e7\u8230\u7035\u7845\u8584\u6769\ue15d\u552c\u9363?
            delete_DboPageCommentGraphicsIter $lGraphicsIter

            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            foreach bitmap $bitmapsToDelete {
                $lPage DeleteCommentGraphic $bitmap
                incr lDeletedCount
                ::capMenuUtil::logDebug "Deleted Graphic"
            }

            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            set lPage [$lPagesIter NextPage $lStatus]
        }

        # \u95b2\u5a43\u6581\u6924\u7538\u6f70\u6769\ue15d\u552c\u9363?
        delete_DboSchematicPagesIter $lPagesIter

        # \u8fed\u4ee3\u4e0b\u4e00\u4e2a\u539f\u7406\u56fe
        set lView [$lSchematicIter NextView $lStatus]
    }

    # \u91ca\u653e\u539f\u7406\u56fe\u8fed\u4ee3\u5668
    delete_DboLibViewsIter $lSchematicIter

    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    destroy $progressWindow

    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    $lStatus -delete
}

# \u9352\u6d98\u7f13\u9a9e\u8235\u6a09\u7ec0\u54c4\u57b9\u95c4\u3085\u6d58\u8930\u3220\ue629\u941e\u55d7\u810a\u7ed0?
proc ::capMenuUtil::showDeleteGraphicProgressDialog {totalPages} {
    set progressWindow .deleteGraphicProgress
    if {[winfo exists $progressWindow]} {
        destroy $progressWindow
    }

    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    toplevel $progressWindow
    wm title $progressWindow "Delete Graphic Objects"
    wm resizable $progressWindow 0 0
    wm attributes $progressWindow -toolwindow 1
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    # wm transient $progressWindow .
    # \u5bee\u54c4\u57d7\u93c4\u5267\u305a\u9a9e\u5241\u7586\u6924?
    wm deiconify $progressWindow
    raise $progressWindow
    focus $progressWindow

    # \u8bbe\u7f6e\u5b57\u4f53\u548c\u989c\u8272\uff08\u517c\u5bb916.6\u7684\u9ed8\u8ba4\u5b57\u4f53\uff09
    set font {TkDefaultFont 10}
    set bgColor "#f0f0f0"
    set fgColor "#333333"
    
    # \u914d\u7f6e\u7a97\u53e3\u6837\u5f0f
    $progressWindow configure -bg $bgColor
    
    # \u521b\u5efa\u5185\u5bb9\u6846\u67b6
    set contentFrame [frame $progressWindow.content -bg $bgColor -padx 20 -pady 20]
    pack $contentFrame -fill both -expand 1
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    label $contentFrame.label -text "Deleting graphic objects..." \
        -font $font -fg $fgColor -bg $bgColor
    pack $contentFrame.label -pady 5
    
    # \u6dfb\u52a0\u8fdb\u5ea6\u6587\u672c
    label $contentFrame.status -text "Page 0 / $totalPages" \
        -font [list TkDefaultFont 9] -fg $fgColor -bg $bgColor
    pack $contentFrame.status -pady 5
    
    # \u4f7f\u7528\u4f20\u7edf\u8fdb\u5ea6\u6761\uff08\u4e0d\u4f7f\u7528ttk\uff0c\u517c\u5bb9\u65e7\u7248\u672cTk)
    frame $contentFrame.progress -relief sunken -bd 1 -width 300 -height 20
    canvas $contentFrame.progress.canvas -width 296 -height 16 -bg white
    $contentFrame.progress.canvas create rectangle 0 0 0 16 -fill blue -outline blue -tags bar
    pack $contentFrame.progress.canvas -fill both -expand 1
    pack $contentFrame.progress -pady 10 -fill x
    
    # \u6dfb\u52a0\u8bf4\u660e\u6587\u5b57
    label $contentFrame.note -text "Please wait. Do not close OrCAD..." \
        -font [list TkDefaultFont 8] -fg "#666666" -bg $bgColor -wraplength 300
    pack $contentFrame.note -pady 5
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    update

    # \u5c45\u4e2d\u663e\u793a\u5f39\u7a97
    update idletasks
    set x [expr {([winfo screenwidth .] - [winfo reqwidth $progressWindow]) / 2}]
    set y [expr {([winfo screenheight .] - [winfo reqheight $progressWindow]) / 2}]
    wm geometry $progressWindow "+$x+$y"

    # \u5f3a\u5236\u5904\u7406\u6240\u6709\u6302\u8d77\u7684\u4e8b\u4ef6
    update

    return $progressWindow
}


# ////////////////////////////////////////////////////////////////////////////////
# \u4e00\u952e\u6df7\u6dc6\u8865\u5145\uff1a\u9690\u85cf\u5668\u4ef6\u578b\u53f7\u3001\u5c01\u88c5\u7b49\u654f\u611f\u663e\u793a\u5c5e\u6027\u3002
# ////////////////////////////////////////////////////////////////////////////////
namespace eval ::capMenuUtil {
    variable toolVersion "V1.8"
    variable sensitiveDisplayProperties [list "Value" "\u89c4\u683c\u578b\u53f7" "Part Number" "PCB Footprint" "Footprint" "Source Package" "Source Part" "Part" "Package"]
}

proc ::capMenuUtil::isSensitiveDisplayProperty {propName} {
    variable sensitiveDisplayProperties
    foreach sensitiveName $sensitiveDisplayProperties {
        if {[string equal -nocase $propName $sensitiveName]} {
            return 1
        }
    }
    return 0
}

proc ::capMenuUtil::SetSensitiveComponentPropertiesDisplayType { pLib displayType } {
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "No active design is open."
        return
    }

    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }

    set lNullObj NULL
    set lView [$lSchematicIter NextView $lStatus]
    set changedCount 0

    while {$lView != $lNullObj} {
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]
        while {$lPage != $lNullObj} {
            set lPartInstsIter [$lPage NewPartInstsIter $lStatus]
            set lInst [$lPartInstsIter NextPartInst $lStatus]
            while {$lInst != $lNullObj} {
                set lPlacedInst [DboPartInstToDboPlacedInst $lInst]
                if {$lPlacedInst != $lNullObj} {
                    set lDisplayPropsIter [$lPlacedInst NewDisplayPropsIter $lStatus]
                    set lDProp [$lDisplayPropsIter NextProp $lStatus]
                    while {$lDProp != $lNullObj} {
                        set lNameCStr [DboTclHelper_sMakeCString]
                        $lDProp GetName $lNameCStr
                        set lNameString [DboTclHelper_sGetConstCharPtr $lNameCStr]
                        if {[::capMenuUtil::isSensitiveDisplayProperty $lNameString]} {
                            catch {$lDProp SetDisplayType $displayType}
                            incr changedCount
                        }
                        DboTclHelper_sDeleteCString $lNameCStr
                        set lDProp [$lDisplayPropsIter NextProp $lStatus]
                    }
                    delete_DboDisplayPropsIter $lDisplayPropsIter
                }
                set lInst [$lPartInstsIter NextPartInst $lStatus]
            }
            delete_DboPagePartInstsIter $lPartInstsIter
            set lPage [$lPagesIter NextPage $lStatus]
        }
        delete_DboSchematicPagesIter $lPagesIter
        set lView [$lSchematicIter NextView $lStatus]
    }

    delete_DboLibViewsIter $lSchematicIter
    ::capMenuUtil::logDebug "SetSensitiveComponentPropertiesDisplayType changed: $changedCount"
}

proc ::capMenuUtil::HideSensitiveComponentProperties { pLib } {
    ::capMenuUtil::SetSensitiveComponentPropertiesDisplayType $pLib 0
}

proc ::capMenuUtil::ShowSensitiveComponentProperties { pLib } {
    ::capMenuUtil::SetSensitiveComponentPropertiesDisplayType $pLib 1
}

proc ::capMenuUtil::HideUcomponent { pLib } {
    # \u5df2\u751f\u6210\u7684\u968f\u673a\u540d\u79f0\u96c6\u5408\uff0c\u786e\u4fdd\u552f\u4e00\u6027
    set lStatus [DboState]
	
    # \u947e\u5cf0\u5f47\u93b5\u0446\ue511\u9428\u52ee\ue195\u7481\u2033\ue1ee\u749e?
    set lDesign [GetActivePMDesign]
    
    # \u68c0\u67e5\u662f\u5426\u6709\u6d3b\u52a8\u8bbe\u8ba1
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "No active design is open."
        return
    }
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    
    # \u83b7\u53d6\u7b2c\u4e00\u4e2a\u539f\u7406\u56fe\u89c6\u56fe
    set lView [$lSchematicIter NextView $lStatus]
    set SchNum 0
    set lNullObj NULL
	
    while { $lView != $lNullObj } {
        incr SchNum
		
        # \u4eceDboView\u8f6c\u6362\u4e3aDboSchematic
        set lSchematic [DboViewToDboSchematic $lView]
        # \u65b0\u5efa\u9875\u9762\u8fed\u4ee3\u5668\uff0c\u7528\u4e8e\u904d\u5386
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        # \u947e\u5cf0\u5f47\u7ed7\ue0ff\u7af4\u6924?
        set lPage [$lPagesIter NextPage $lStatus]
        set pageCount 0
        
        while { $lPage != $lNullObj } {
            incr pageCount
            puts "\nHandling page #$pageCount..."
            
            set lPartInstsIter [$lPage NewPartInstsIter $lStatus]
            set instCount 0
            set uInstCount 0
            set lInst [$lPartInstsIter NextPartInst $lStatus]
            
            while { $lInst != $lNullObj } {
                incr instCount
                # \u947e\u5cf0\u5f47\u9363\u3124\u6b22\u6d63\u5d85\u5f7f\u951b\u5727eference Designator\u951b?
                set lRefDesNameCStr [DboTclHelper_sMakeCString "Reference"]
                set lRefDesValueCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lRefDesNameCStr $lRefDesValueCStr
                set lRefDesString [DboTclHelper_sGetConstCharPtr $lRefDesValueCStr]
                
                ::capMenuUtil::logDebug "  Checking component #$instCount : RefDes = $lRefDesString"

                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                if { [regexp -nocase {^U} $lRefDesString] } {
                    incr uInstCount
                    # \u5c06\u5668\u4ef6\u8f6c\u6362\u4e3aPlacedInst\u5bf9\u8c61
                    set lPlacedInst [DboPartInstToDboPlacedInst $lInst]
                    if { $lPlacedInst != $lNullObj } {
                        # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                        set lDisplayPropsIter [$lPlacedInst NewDisplayPropsIter $lStatus]
                        set propCount 0
                        set valueFound 0
                        set lDProp [$lDisplayPropsIter NextProp $lStatus]
                        
                        while { $lDProp != $lNullObj } {
                            incr propCount
                            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                            set lNameCStr [DboTclHelper_sMakeCString]
                            $lDProp GetName $lNameCStr
                            set lNameString [DboTclHelper_sGetConstCharPtr $lNameCStr]
                            ::capMenuUtil::logDebug " sx #$propCount: $lNameString"
                            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                            if {[string equal -nocase $lNameString "Value"]} {
                                catch {
                                    $lDProp SetDisplayType 0
                                    ::capMenuUtil::logDebug "    Success: Value visibility for $lRefDesString set to 0 (invisible)."
                                } errMsg
                                if {$errMsg ne ""} {
                                    ::capMenuUtil::logDebug "    Warning: Failed to set Value visibility for $lRefDesString - $errMsg"
                                }
                                set valueFound 1 ;# \u6807\u8bb0\u4e3a\u5df2\u627e\u5230
                            }
                            
                            # \u91ca\u653eCString\u5185\u5b58
                            DboTclHelper_sDeleteCString $lNameCStr
                            
                            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                            set lDProp [$lDisplayPropsIter NextProp $lStatus]
                        }
                        
                        if {!$valueFound} {
                           puts "    Warning: 'Value' property not found for component $lRefDesString."
                        }
                        
                        # \u91ca\u653e\u663e\u793a\u5c5e\u6027\u8fed\u4ee3\u5668
                        delete_DboDisplayPropsIter $lDisplayPropsIter
                    }
                }
                
                # \u91ca\u653eCString\u5185\u5b58
                DboTclHelper_sDeleteCString $lRefDesNameCStr
                DboTclHelper_sDeleteCString $lRefDesValueCStr
                
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lInst [$lPartInstsIter NextPartInst $lStatus] 
            }
            
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            delete_DboPagePartInstsIter $lPartInstsIter
            
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            set lPage [$lPagesIter NextPage $lStatus]
        }
        
        # \u95b2\u5a43\u6581\u6924\u7538\u6f70\u6769\ue15d\u552c\u9363?
        delete_DboSchematicPagesIter $lPagesIter
        
        # \u83b7\u53d6\u4e0b\u4e00\u4e2a\u539f\u7406\u56fe\u89c6\u56fe
        set lView [$lSchematicIter NextView $lStatus]
    }
    
    # \u91ca\u653e\u539f\u7406\u56fe\u89c6\u56fe\u8fed\u4ee3\u5668
    delete_DboLibViewsIter $lSchematicIter
    
    puts "\nOperation completed."
}
proc ::capMenuUtil::HideALLcomponent { pLib } {
    # \u5df2\u751f\u6210\u7684\u968f\u673a\u540d\u79f0\u96c6\u5408\uff0c\u786e\u4fdd\u552f\u4e00\u6027
    set lStatus [DboState]
	
    # \u947e\u5cf0\u5f47\u93b5\u0446\ue511\u9428\u52ee\ue195\u7481\u2033\ue1ee\u749e?
    set lDesign [GetActivePMDesign]
    
    # \u68c0\u67e5\u662f\u5426\u6709\u6d3b\u52a8\u8bbe\u8ba1
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "No active design is open."
        return
    }
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    
    # \u83b7\u53d6\u7b2c\u4e00\u4e2a\u539f\u7406\u56fe\u89c6\u56fe
    set lView [$lSchematicIter NextView $lStatus]
    set SchNum 0
    set lNullObj NULL
	
    while { $lView != $lNullObj } {
        incr SchNum
		
        # \u4eceDboView\u8f6c\u6362\u4e3aDboSchematic
        set lSchematic [DboViewToDboSchematic $lView]
        # \u65b0\u5efa\u9875\u9762\u8fed\u4ee3\u5668\uff0c\u7528\u4e8e\u904d\u5386
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        # \u947e\u5cf0\u5f47\u7ed7\ue0ff\u7af4\u6924?
        set lPage [$lPagesIter NextPage $lStatus]
        set pageCount 0
        
        while { $lPage != $lNullObj } {
            incr pageCount
            puts "\nHandling page #$pageCount..."
            
            set lPartInstsIter [$lPage NewPartInstsIter $lStatus]
            set instCount 0
            set uInstCount 0
            set lInst [$lPartInstsIter NextPartInst $lStatus]
            
            while { $lInst != $lNullObj } {
                incr instCount
                # \u947e\u5cf0\u5f47\u9363\u3124\u6b22\u6d63\u5d85\u5f7f\u951b\u5727eference Designator\u951b?
                set lRefDesNameCStr [DboTclHelper_sMakeCString "Reference"]
                set lRefDesValueCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lRefDesNameCStr $lRefDesValueCStr
                set lRefDesString [DboTclHelper_sGetConstCharPtr $lRefDesValueCStr]
                
                ::capMenuUtil::logDebug "  Checking component #$instCount : RefDes = $lRefDesString"

                
                    incr uInstCount
                    # \u5c06\u5668\u4ef6\u8f6c\u6362\u4e3aPlacedInst\u5bf9\u8c61
                    set lPlacedInst [DboPartInstToDboPlacedInst $lInst]
                    if { $lPlacedInst != $lNullObj } {
                        # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                        set lDisplayPropsIter [$lPlacedInst NewDisplayPropsIter $lStatus]
                        set propCount 0
                        set valueFound 0
                        set lDProp [$lDisplayPropsIter NextProp $lStatus]
                        
                        while { $lDProp != $lNullObj } {
                            incr propCount
                            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                            set lNameCStr [DboTclHelper_sMakeCString]
                            $lDProp GetName $lNameCStr
                            set lNameString [DboTclHelper_sGetConstCharPtr $lNameCStr]
                            
                            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                            if {[string equal -nocase $lNameString "Value"]} {
                                catch {
                                    $lDProp SetDisplayType 0
                                    ::capMenuUtil::logDebug "    Success: Value visibility for $lRefDesString set to 0 (invisible)."
                                } errMsg
                                if {$errMsg ne ""} {
                                    ::capMenuUtil::logDebug "    Warning: Failed to set Value visibility for $lRefDesString - $errMsg"
                                }
                                set valueFound 1 ;# \u6807\u8bb0\u4e3a\u5df2\u627e\u5230
                            }
                            
                            # \u91ca\u653eCString\u5185\u5b58
                            DboTclHelper_sDeleteCString $lNameCStr
                            
                            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                            set lDProp [$lDisplayPropsIter NextProp $lStatus]
                        }
                        
                        if {!$valueFound} {
                           puts "    Warning: 'Value' property not found for component $lRefDesString."
                        }
                        
                        # \u91ca\u653e\u663e\u793a\u5c5e\u6027\u8fed\u4ee3\u5668
                        delete_DboDisplayPropsIter $lDisplayPropsIter
                    }
                
                
                # \u91ca\u653eCString\u5185\u5b58
                DboTclHelper_sDeleteCString $lRefDesNameCStr
                DboTclHelper_sDeleteCString $lRefDesValueCStr
                
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lInst [$lPartInstsIter NextPartInst $lStatus] 
            }
            
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            delete_DboPagePartInstsIter $lPartInstsIter
            
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            set lPage [$lPagesIter NextPage $lStatus]
        }
        
        # \u95b2\u5a43\u6581\u6924\u7538\u6f70\u6769\ue15d\u552c\u9363?
        delete_DboSchematicPagesIter $lPagesIter
        
        # \u83b7\u53d6\u4e0b\u4e00\u4e2a\u539f\u7406\u56fe\u89c6\u56fe
        set lView [$lSchematicIter NextView $lStatus]
    }
    
    # \u91ca\u653e\u539f\u7406\u56fe\u89c6\u56fe\u8fed\u4ee3\u5668
    delete_DboLibViewsIter $lSchematicIter
    
    puts "\nOperation completed."
}


proc ::capMenuUtil::DeleteTextTitleblocks { pLib } {
    # \u5df2\u751f\u6210\u7684\u968f\u673a\u540d\u79f0\u96c6\u5408\uff0c\u786e\u4fdd\u552f\u4e00\u6027
    set lStatus [DboState]
	
    # \u947e\u5cf0\u5f47\u93b5\u0446\ue511\u9428\u52ee\ue195\u7481\u2033\ue1ee\u749e?
    set lDesign [GetActivePMDesign]
    
    # \u68c0\u67e5\u662f\u5426\u6709\u6d3b\u52a8\u8bbe\u8ba1
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "No active design is open."
        return
    }
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    
    # \u83b7\u53d6\u7b2c\u4e00\u4e2a\u539f\u7406\u56fe\u89c6\u56fe
    set lView [$lSchematicIter NextView $lStatus]
    set SchNum 0
    set lNullObj NULL
	
    
	
    while { $lView != $lNullObj } {
        incr SchNum
		
        # \u4eceDboView\u8f6c\u6362\u4e3aDboSchematic
        set lSchematic [DboViewToDboSchematic $lView]
        # \u65b0\u5efa\u9875\u9762\u8fed\u4ee3\u5668\uff0c\u7528\u4e8e\u904d\u5386
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        # \u947e\u5cf0\u5f47\u7ed7\ue0ff\u7af4\u6924?
        set lPage [$lPagesIter NextPage $lStatus]
        set pageCount 0
        
        while { $lPage != $lNullObj } {
            incr pageCount
            puts "\nHandling page #$pageCount..."
            ##################\u5f00\u59cb\u5220\u9664Titleblocks#########################
			set lTitleBlocksIter [$lPage NewTitleBlocksIter $lStatus]
			set lTitle [$lTitleBlocksIter NextTitleBlock $lStatus]
			while {$lTitle != $lNullObj} {
			   $lPage DeleteTitleBlock $lTitle
			   set lTitle [$lTitleBlocksIter NextTitleBlock $lStatus]
			}
			delete_DboPageTitleBlocksIter $lTitleBlocksIter
			puts "\n Page $pageCount TitleBlocks has been deleted"
			##################\u7ed3\u675f\u5220\u9664Titleblocks#########################
			
			##################\u5f00\u59cb\u5220\u9664Text#########################
			set lGraphicsIter [$lPage NewCommentGraphicsIter $lStatus]
			set lGraphic [$lGraphicsIter NextCommentGraphic $lStatus]
			
			while {$lGraphic != $lNullObj} {
			   
			   set lComment [DboGraphicInstanceToDboGraphicCommentTextInst $lGraphic]
			   
			   if {$lComment!= $lNullObj} {
			  
			     set lDef [$lComment GetDboCommentText]
				 set lText [DboTclHelper_sMakeCString]
				 $lDef GetText $lText
				 set lTextStr [DboTclHelper_sGetConstCharPtr $lText]
				 
				 
				 if {$lTextStr != $lNullObj} {
				   set lTextNULL [DboTclHelper_sMakeCString]
				   $lDef SetText $lTextNULL
				 }
				 
			  }
			   set lGraphic [$lGraphicsIter NextCommentGraphic $lStatus]
			   
			}
			delete_DboPageCommentGraphicsIter $lGraphicsIter
			puts "\n Page $pageCount Text has been deleted"
			
			##################\u7ed3\u675f\u5220\u9664Text#########################
			
			
			
			puts "\n page #$pageCount complete!"
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            set lPage [$lPagesIter NextPage $lStatus]
        }
        
        # \u95b2\u5a43\u6581\u6924\u7538\u6f70\u6769\ue15d\u552c\u9363?
        delete_DboSchematicPagesIter $lPagesIter
        
        # \u83b7\u53d6\u4e0b\u4e00\u4e2a\u539f\u7406\u56fe\u89c6\u56fe
        set lView [$lSchematicIter NextView $lStatus]
    }
    
    # \u91ca\u653e\u539f\u7406\u56fe\u89c6\u56fe\u8fed\u4ee3\u5668
    delete_DboLibViewsIter $lSchematicIter
    
}


# ////////////////////////////////////////////////////////////////////////////////
# \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
# ////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::GrayedPartToNC { pLib } {
    # \u5df2\u751f\u6210\u7684\u968f\u673a\u540d\u79f0\u96c6\u5408\uff0c\u786e\u4fdd\u552f\u4e00\u6027
    set lStatus [DboState]
    
    # \u947e\u5cf0\u5f47\u93b5\u0446\ue511\u9428\u52ee\ue195\u7481\u2033\ue1ee\u749e?
    set lDesign [GetActivePMDesign]
    
    # \u68c0\u67e5\u662f\u5426\u6709\u6d3b\u52a8\u8bbe\u8ba1
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        puts "Error: No active design is open."
        return
    }
    
    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    
    # \u83b7\u53d6\u7b2c\u4e00\u4e2a\u539f\u7406\u56fe\u89c6\u56fe
    set lView [$lSchematicIter NextView $lStatus]
    set SchNum 0
    set lNullObj NULL
    set processedCount 0  ;# \u7f01\u71bb\ue178\u6fb6\u52ed\u608a\u9428\u52eb\u6ad2\u6d60\u8235\u669f\u95b2?
    
    while { $lView != $lNullObj } {
        incr SchNum
        
        # \u4eceDboView\u8f6c\u6362\u4e3aDboSchematic
        set lSchematic [DboViewToDboSchematic $lView]
        
        # \u65b0\u5efa\u9875\u9762\u8fed\u4ee3\u5668\uff0c\u7528\u4e8e\u904d\u5386
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        
        # \u947e\u5cf0\u5f47\u7ed7\ue0ff\u7af4\u6924?
        set lPage [$lPagesIter NextPage $lStatus]
        set PageNum 0
        
        while { $lPage != $lNullObj } {
            incr PageNum
            
            puts "\nProcessing Schematic $SchNum, Page $PageNum"
            
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            set lPartInstsIter [$lPage NewPartInstsIter $lStatus]
            set lInst [$lPartInstsIter NextPartInst $lStatus]
            
            while { $lInst != $lNullObj } {
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lPropNameCStr [DboTclHelper_sMakeCString "Value"]
                set lPropValueCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lPropNameCStr $lPropValueCStr
                set lPropValueString [DboTclHelper_sGetConstCharPtr $lPropValueCStr]
                
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lPropPNNameCStr [DboTclHelper_sMakeCString "Part Number"]
                set lPropPNCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lPropPNNameCStr $lPropPNCStr
                set lPropPNString [DboTclHelper_sGetConstCharPtr $lPropPNCStr]
                
                # \u947e\u5cf0\u5f47\u9363\u3124\u6b22\u6d63\u5d85\u5f7f\u951b\u5727eference Designator\u951b?
                set lRefDesNameCStr [DboTclHelper_sMakeCString "Reference"]
                set lRefDesValueCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lRefDesNameCStr $lRefDesValueCStr
                set lRefDesString [DboTclHelper_sGetConstCharPtr $lRefDesValueCStr]
                
                # \u5224\u65ad\u662f\u5426\u542b\u6709NC\u5b57\u6837\uff08\u4e0d\u533a\u5206\u5927\u5c0f\u5199\uff09
                set hasNC 0
                if { [regexp -nocase {NC} $lPropValueString] || 
                     [regexp -nocase {NC} $lPropPNString] } {
                    set hasNC 1
                }
                
                # \u5982\u679c\u542b\u6709NC\u5b57\u6837\uff0c\u5219\u8fdb\u884c\u5904\u7406
                if { $hasNC } {
                    incr processedCount
                    
                    # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                    set lNewValueCStr [DboTclHelper_sMakeCString "NC"]
                    $lInst SetEffectivePropStringValue $lPropNameCStr $lNewValueCStr
                    
                    # 2. \u8bbe\u7f6e\u5143\u4ef6\u989c\u8272\u4e3a\u7070\u8272\uff08\u53ef\u9009\uff0c\u4fdd\u6301\u4e0eNC Part Grayed\u4e00\u81f4\uff09
                    set lColorPropNameCStr [DboTclHelper_sMakeCString "Color"]
                    set lColorPropValueCStr [DboTclHelper_sMakeCString "RGB(192,192,192)"]
                    $lInst SetEffectivePropStringValue $lColorPropNameCStr $lColorPropValueCStr
                    
                    # 3. \u8bbe\u7f6e\u5c5e\u6027\u663e\u793a\u4e3a\u53ef\u89c1
                    set lPlacedInst [DboPartInstToDboPlacedInst $lInst]
                    if { $lPlacedInst != $lNullObj } {
                        # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                        set lDisplayPropsIter [$lPlacedInst NewDisplayPropsIter $lStatus]
                        set lDProp [$lDisplayPropsIter NextProp $lStatus]
                        
                        while { $lDProp != $lNullObj } {
                            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                            set lNameCStr [DboTclHelper_sMakeCString]
                            $lDProp GetName $lNameCStr
                            set lNameString [DboTclHelper_sGetConstCharPtr $lNameCStr]
                            
                            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                            if { [string equal -nocase $lNameString "Value"] } {
                                $lDProp SetDisplayType 1
                                ::capMenuUtil::logDebug "  Component $lRefDesString: Value set to 'NC' and made visible"
                            }
                            
                            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                            $lDProp SetColor 45
                            
                            # \u91ca\u653eCString\u5185\u5b58
                            DboTclHelper_sDeleteCString $lNameCStr
                            
                            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                            set lDProp [$lDisplayPropsIter NextProp $lStatus]
                        }
                        
                        # \u91ca\u653e\u663e\u793a\u5c5e\u6027\u8fed\u4ee3\u5668
                        delete_DboDisplayPropsIter $lDisplayPropsIter
                    }
                }
                
                # \u91ca\u653eCString\u5185\u5b58
                DboTclHelper_sDeleteCString $lPropNameCStr
                DboTclHelper_sDeleteCString $lPropValueCStr
                DboTclHelper_sDeleteCString $lPropPNNameCStr
                DboTclHelper_sDeleteCString $lPropPNCStr
                DboTclHelper_sDeleteCString $lRefDesNameCStr
                DboTclHelper_sDeleteCString $lRefDesValueCStr
                
                # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
                set lInst [$lPartInstsIter NextPartInst $lStatus]
            }
            
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            delete_DboPagePartInstsIter $lPartInstsIter
            
            # \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
            set lPage [$lPagesIter NextPage $lStatus]
        }
        
        # \u95b2\u5a43\u6581\u6924\u7538\u6f70\u6769\ue15d\u552c\u9363?
        delete_DboSchematicPagesIter $lPagesIter
        
        # \u83b7\u53d6\u4e0b\u4e00\u4e2a\u539f\u7406\u56fe\u89c6\u56fe
        set lView [$lSchematicIter NextView $lStatus]
    }
    
    # \u91ca\u653e\u539f\u7406\u56fe\u89c6\u56fe\u8fed\u4ee3\u5668
    delete_DboLibViewsIter $lSchematicIter
    
    puts "\nGrayedPartToNC completed! Processed $processedCount components with 'NC' value."
}


# ////////////////////////////////////////////////////////////////////////////////
# \u6ce8\u91ca\u7f16\u7801\u5df2\u7edf\u4e00\u4e3a GBK\uff0c\u539f\u6ce8\u91ca\u5185\u5bb9\u5df2\u6e05\u7406\u3002
# ////////////////////////////////////////////////////////////////////////////////
namespace eval ::capRequiredSanitize {
    variable targetProperties [list "Value" "\u89c4\u683c\u578b\u53f7"]
    variable sanitizedValue "0"
    variable restoreDirName "_required_sanitize_restore"
    variable lastBackupFileName "cap_required_sanitize_last_backup.txt"
}

proc ::capRequiredSanitize::sanitizeFromMenu {args} {
    set confirm [tk_messageBox -icon question -message "Set Value and model properties to 0 for all parts and create a local restore file.\nContinue?" -type yesno]
    if {$confirm ne "yes"} { return }
    if {[catch {set result [::capRequiredSanitize::sanitizeDesign]} err]} {
        catch {tk_messageBox -icon error -message "Required sanitization failed:\n$err"}
        puts "\[capRequiredSanitize\] ERROR: $err"
        return
    }
    catch {tk_messageBox -icon info -message "Required sanitization completed.\nChanged properties: $result"}
}

proc ::capRequiredSanitize::restoreFromMenu {args} {
    set confirm [tk_messageBox -icon question -message "Restore Value and model properties from the latest local restore file.\nContinue?" -type yesno]
    if {$confirm ne "yes"} { return }
    if {[catch {set result [::capRequiredSanitize::restoreDesign]} err]} {
        catch {tk_messageBox -icon error -message "Restore Required Sanitization failed:\n$err"}
        puts "\[capRequiredSanitize\] ERROR: $err"
        return
    }
    catch {tk_messageBox -icon info -message "Restore Required Sanitization completed.\nRestored properties: $result"}
}

proc ::capRequiredSanitize::sanitizeDesign {} {
    variable targetProperties
    variable sanitizedValue

    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        error "No active design is open."
    }

    set backupPath [::capRequiredSanitize::makeBackupPath]
    set changedCount 0
    set fh [open $backupPath w]
    fconfigure $fh -encoding utf-8 -translation lf
    puts $fh "# capRequiredSanitize v1"
    puts $fh "# generated [clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S}]"
    puts $fh "# columns: key property value"

    ::capRequiredSanitize::forEachPart $lDesign $lStatus {part status} {
        set key [::capRequiredSanitize::getPartKey $part]
        foreach propName $::capRequiredSanitize::targetProperties {
            set info [::capRequiredSanitize::getPropertyValue $part $propName]
            if {![lindex $info 0]} { continue }
            set oldValue [lindex $info 1]
            ::capRequiredSanitize::writeBackupRecord $fh $key $propName $oldValue
            if {[::capRequiredSanitize::setPropertyValue $part $propName $::capRequiredSanitize::sanitizedValue]} {
                incr changedCount
            }
        }
        catch {$part Update}
    }

    close $fh
    ::capRequiredSanitize::writeLastBackupPath $backupPath
    puts "\[capRequiredSanitize\] backup: $backupPath"
    puts "\[capRequiredSanitize\] changed properties: $changedCount"
    return $changedCount
}

proc ::capRequiredSanitize::restoreDesign {} {
    set backupPath [::capRequiredSanitize::readLastBackupPath]
    if {$backupPath eq "" || ![file exists $backupPath]} {
        error "No recent restore file was found."
    }

    set records [::capRequiredSanitize::readBackupRecords $backupPath]
    if {[llength $records] == 0} {
        error "Restore file is empty or invalid: $backupPath"
    }

    array unset restoreMap
    array set restoreMap {}
    foreach rec $records {
        set key [lindex $rec 0]
        set propName [lindex $rec 1]
        set propValue [lindex $rec 2]
        set restoreMap($key\t$propName) $propValue
    }

    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        error "No active design is open."
    }

    set restoredCount 0
    ::capRequiredSanitize::forEachPart $lDesign $lStatus {part status} {
        set key [::capRequiredSanitize::getPartKey $part]
        foreach propName $::capRequiredSanitize::targetProperties {
            set mapKey "$key\t$propName"
            if {[info exists restoreMap($mapKey)]} {
                if {[::capRequiredSanitize::setPropertyValue $part $propName $restoreMap($mapKey)]} {
                    incr restoredCount
                }
            }
        }
        catch {$part Update}
    }

    puts "\[capRequiredSanitize\] restored from: $backupPath"
    puts "\[capRequiredSanitize\] restored properties: $restoredCount"
    return $restoredCount
}

proc ::capRequiredSanitize::forEachPart {lDesign lStatus callbackVars callback} {
    set lNullObj NULL
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }

    set lView [$lSchematicIter NextView $lStatus]
    while {$lView != $lNullObj} {
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]
        while {$lPage != $lNullObj} {
            set lPartInstsIter [$lPage NewPartInstsIter $lStatus]
            set lInst [$lPartInstsIter NextPartInst $lStatus]
            while {$lInst != $lNullObj} {
                uplevel 1 [list set part $lInst]
                uplevel 1 [list set status $lStatus]
                uplevel 1 $callback
                set lInst [$lPartInstsIter NextPartInst $lStatus]
            }
            delete_DboPagePartInstsIter $lPartInstsIter
            set lPage [$lPagesIter NextPage $lStatus]
        }
        delete_DboSchematicPagesIter $lPagesIter
        set lView [$lSchematicIter NextView $lStatus]
    }
    delete_DboLibViewsIter $lSchematicIter
}

proc ::capRequiredSanitize::getPropertyValue {obj propName} {
    set prop [DboTclHelper_sMakeCString $propName]
    set value [DboTclHelper_sMakeCString ""]
    if {[catch {$obj GetEffectivePropStringValue $prop $value}]} {
        catch {DboTclHelper_sDeleteCString $prop}
        catch {DboTclHelper_sDeleteCString $value}
        return [list 0 ""]
    }
    set str [DboTclHelper_sGetConstCharPtr $value]
    catch {DboTclHelper_sDeleteCString $prop}
    catch {DboTclHelper_sDeleteCString $value}
    return [list 1 $str]
}

proc ::capRequiredSanitize::setPropertyValue {obj propName propValue} {
    if {$propName eq "Value"} {
        if {![catch {$obj SetPartValue $propValue}]} { return 1 }
    }
    set prop [DboTclHelper_sMakeCString $propName]
    set value [DboTclHelper_sMakeCString $propValue]
    set ok 1
    if {[catch {$obj SetEffectivePropStringValue $prop $value}]} {
        set ok 0
    }
    catch {DboTclHelper_sDeleteCString $prop}
    catch {DboTclHelper_sDeleteCString $value}
    return $ok
}

proc ::capRequiredSanitize::getPartKey {part} {
    set info [::capRequiredSanitize::getPropertyValue $part "Reference"]
    if {[lindex $info 0] && [lindex $info 1] ne ""} {
        return [lindex $info 1]
    }
    return "OBJ_[string map {\" _ \\ _ \t _ \n _} $part]"
}

proc ::capRequiredSanitize::makeBackupPath {} {
    variable restoreDirName
    set designPath [::capRequiredSanitize::getDesignPath]
    if {$designPath eq ""} {
        set baseDir [pwd]
        set designBase "capture_design"
    } else {
        set baseDir [file dirname $designPath]
        set designBase [file rootname [file tail $designPath]]
    }
    set dir [file join $baseDir $restoreDirName]
    if {![file exists $dir]} { file mkdir $dir }
    set stamp [clock format [clock seconds] -format {%Y%m%d_%H%M%S}]
    return [file join $dir "${designBase}_required_sanitize_${stamp}.tsv"]
}

proc ::capRequiredSanitize::getDesignPath {} {
    set lDesign [GetActivePMDesign]
    foreach method {GetDesignFileName GetFullPath GetFileName GetName} {
        if {![catch {set cstr [DboTclHelper_sMakeCString]}] && ![catch {$lDesign $method $cstr}]} {
            set value [DboTclHelper_sGetConstCharPtr $cstr]
            catch {DboTclHelper_sDeleteCString $cstr}
            if {$value ne "" && $value ne "NULL"} { return $value }
        }
    }
    return ""
}

proc ::capRequiredSanitize::writeLastBackupPath {backupPath} {
    variable lastBackupFileName
    set lastPath [file join [file dirname $backupPath] $lastBackupFileName]
    set fh [open $lastPath w]
    fconfigure $fh -encoding utf-8 -translation lf
    puts $fh $backupPath
    close $fh
}

proc ::capRequiredSanitize::readLastBackupPath {} {
    variable restoreDirName
    variable lastBackupFileName
    set designPath [::capRequiredSanitize::getDesignPath]
    if {$designPath eq ""} {
        set dir [file join [pwd] $restoreDirName]
    } else {
        set dir [file join [file dirname $designPath] $restoreDirName]
    }
    set lastPath [file join $dir $lastBackupFileName]
    if {[file exists $lastPath]} {
        set fh [open $lastPath r]
        fconfigure $fh -encoding utf-8
        set backupPath [string trim [read $fh]]
        close $fh
        return $backupPath
    }
    set candidates [glob -nocomplain -directory $dir *_required_sanitize_*.tsv]
    if {[llength $candidates] == 0} { return "" }
    return [lindex [lsort $candidates] end]
}

proc ::capRequiredSanitize::writeBackupRecord {fh key propName propValue} {
    puts $fh [join [list [::capRequiredSanitize::escapeField $key] [::capRequiredSanitize::escapeField $propName] [::capRequiredSanitize::escapeField $propValue]] "\t"]
}

proc ::capRequiredSanitize::readBackupRecords {backupPath} {
    set fh [open $backupPath r]
    fconfigure $fh -encoding utf-8
    set records [list]
    while {[gets $fh line] >= 0} {
        if {$line eq "" || [string index $line 0] eq "#"} { continue }
        set fields [split $line "\t"]
        if {[llength $fields] < 3} { continue }
        lappend records [list [::capRequiredSanitize::unescapeField [lindex $fields 0]] [::capRequiredSanitize::unescapeField [lindex $fields 1]] [::capRequiredSanitize::unescapeField [join [lrange $fields 2 end] "\t"]]]
    }
    close $fh
    return $records
}

proc ::capRequiredSanitize::escapeField {value} {
    return [string map [list "\\" "\\\\" "\t" "\\t" "\n" "\\n" "\r" "\\r"] $value]
}

proc ::capRequiredSanitize::unescapeField {value} {
    set result ""
    set len [string length $value]
    for {set i 0} {$i < $len} {incr i} {
        set ch [string index $value $i]
        if {$ch eq "\\" && $i + 1 < $len} {
            incr i
            set next [string index $value $i]
            switch -- $next {
                t {append result "\t"}
                n {append result "\n"}
                r {append result "\r"}
                default {append result $next}
            }
        } else {
            append result $ch
        }
    }
    return $result
}

# ////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::capTrue {args} {
    return 1
}
