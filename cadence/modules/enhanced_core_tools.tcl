# Enhanced core tools for Insta360硬件提效平台.
# This module is sourced only by the controlled platform loader when a script is enabled.
# It must not register Capture menus or global actions by itself.

package provide capMenuUtil 1.0

namespace eval ::capMenuUtil {
    variable toolVersion "V1.8"
    # 注释编码已统一为 GBK，原注释内容已清理。
    if {[catch {package require Tk}]} {
        puts "Warning: Tk package not available, GUI features will be disabled"
    } else {
        # 隐藏主Tk窗口（启动时不显示）
        if {[winfo exists .]} {
            wm withdraw .
            # 绑定窗口映射事件，防止主窗口意外显示
            bind . <Map> { wm withdraw . }
        }
    }
    
    # 缓存网络名映射关系，提高性能
    variable netNameMap [list]
    # 已生成的随机名称集合，确保唯一性
    variable generatedNames [list]
    # 性能优化：默认关闭逐对象日志，避免大型原理图在 Capture 命令窗口刷屏卡顿。
    variable verboseLog 0
}

proc ::capMenuUtil::logDebug {message} {
    variable verboseLog
    if {$verboseLog} {
        puts $message
    }
}

# ////////////////////////////////////////////////////////////////////////////////
# 注释编码已统一为 GBK，原注释内容已清理。
# ////////////////////////////////////////////////////////////////////////////////
# ////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::confirmGrayedPartToNC { pLib } {
    # 步骤1：用户确认（防止误操作）
    set confirm [tk_messageBox -icon question -message "将把 NC 器件的 Value 改为 NC。\n是否继续？" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	::capMenuUtil::GrayedPartToNC {pLib}
}

proc ::capMenuUtil::confirmHideUPinNames { pLib } {
    # 步骤1：用户确认（防止误操作）
    set confirm [tk_messageBox -icon question -message "将隐藏 U 器件的 Pin 名称。\n是否继续？" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	::capMenuUtil::HideUPinNames {pLib}
	
}

proc ::capMenuUtil::confirmRandomizeNetNames { pLib } {
# 步骤1：用户确认（防止误操作）
    set confirm [tk_messageBox -icon question -message "将随机化原理图中的全部网络名。\n相同网络名会映射为同一个随机字符串。\n是否继续？" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	::capMenuUtil::RandomizeNetNames {pLib}
	# 显示完成结果
    tk_messageBox -message "网络名随机化完成！" -icon info
}
proc ::capMenuUtil::confirmDeleteAllGraphic { pLib } {
    # 步骤1：用户确认（防止误操作）
    set confirm [tk_messageBox -icon question -message "将Delete All Graphics对象。\n是否继续？" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	::capMenuUtil::DeleteAllGraphic {pLib}
	
}
proc ::capMenuUtil::confirmHideUcomponent { pLib } {
    # 步骤1：用户确认（防止误操作）
    set confirm [tk_messageBox -icon question -message "将隐藏 U 器件的 Value。\n是否继续？" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	::capMenuUtil::HideUcomponent {pLib}
	
}
proc ::capMenuUtil::confirmHideALLcomponent { pLib } {
    # 步骤1：用户确认（防止误操作）
    set confirm [tk_messageBox -icon question -message "将隐藏所有器件的 Value。\n是否继续？" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	::capMenuUtil::HideALLcomponent {pLib}
	
}
proc ::capMenuUtil::confirmDeleteTextTitleblocks { pLib } {
    # 步骤1：用户确认（防止误操作）
    set confirm [tk_messageBox -icon question -message "将清空文本并删除标题栏。\n是否继续？" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	::capMenuUtil::DeleteTextTitleblocks {pLib}
	
}
proc ::capMenuUtil::confirmSchematicObfuscation { pLib } {
# 步骤1：用户确认（防止误操作）
    set confirm [tk_messageBox -icon question -message "将对原理图关键信息执行一键混淆。\n是否继续？" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
	
	::capMenuUtil::DeleteAllGraphic {pLib}
	::capMenuUtil::HideALLcomponent {pLib}
	::capMenuUtil::HideSensitiveComponentProperties {pLib}
	::capMenuUtil::DeleteTextTitleblocks {pLib}
	::capMenuUtil::HideUPinNames {pLib}
	::capMenuUtil::RandomizeNetNames {pLib}
	# 显示完成结果
    tk_messageBox -message "原理图混淆完成！" -icon info
}


#/////////////////////////////////////////////////////////////////////////////////
# 注释编码已统一为 GBK，原注释内容已清理。
#/////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::confirmShowUPinNames { pLib } {
    set confirm [tk_messageBox -icon question -message "将显示 U 器件的 Pin 名称。\n是否继续？" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
    ::capMenuUtil::ShowUPinNames {pLib}
}

proc ::capMenuUtil::confirmShowUcomponent { pLib } {
    set confirm [tk_messageBox -icon question -message "将显示 U 器件的 Value。\n是否继续？" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
    ::capMenuUtil::ShowUcomponent {pLib}
}

proc ::capMenuUtil::confirmShowALLcomponent { pLib } {
    set confirm [tk_messageBox -icon question -message "将显示所有器件的 Value。\n是否继续？" -type yesno]
    if {$confirm ne "yes"} {
        return
    }
    ::capMenuUtil::ShowALLcomponent {pLib}
}
proc ::capMenuUtil::HideUPinNames { pLib } {
    # 初始化基础对象
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    set lNullObj NULL
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "未找到当前打开的设计！"
        return
    }

    # 鍏煎16.6鐨勫師鐞嗗浘杩唬鍣ㄥ垱寤?
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }

    # 遍历所有原理图
    set lView [$lSchematicIter NextView $lStatus]
    while {$lView != $lNullObj} {
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]

        # 注释编码已统一为 GBK，原注释内容已清理。
        set lPage [$lPagesIter NextPage $lStatus]
        while {$lPage != $lNullObj} {
            set lPartInstsIter [$lPage NewPartInstsIter $lStatus]
            # 注释编码已统一为 GBK，原注释内容已清理。
            set lInst [$lPartInstsIter NextPartInst $lStatus]
            while {$lInst != $lNullObj} {
                # 鑾峰彇鍣ㄤ欢浣嶅彿锛圧eference锛?
                set lRefName [DboTclHelper_sMakeCString "Reference"]
                set lRefValue [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lRefName $lRefValue
                set refDes [DboTclHelper_sGetConstCharPtr $lRefValue]
                # 仅处理位号以U/u开头的器件
                if {[regexp -nocase {^U} $refDes]} {
                    set lPlacedInst [DboPartInstToDboPlacedInst $lInst]
                    if {$lPlacedInst != $lNullObj} {
                        
                        # 已生成的随机名称集合，确保唯一性
                        set pinProp [DboTclHelper_sMakeCString "Name"]
                        
                        # 注释编码已统一为 GBK，原注释内容已清理。
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
                        
                        # 注释编码已统一为 GBK，原注释内容已清理。
                        catch {delete_DboPlacedInstPinsIter $lPinsIter}
                        
                        # 统一释放外部申请的属性字符串
                        catch {DboTclHelper_sDeleteCString $pinProp}
                    }
                }

                # 注释编码已统一为 GBK，原注释内容已清理。
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
# 注释编码已统一为 GBK，原注释内容已清理。
# ////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::showNetNameExchangeDialog { pLib } {
    if {[winfo exists .netNameExchange]} {
        destroy .netNameExchange
    }
    # 关键优化2：创建独立顶级窗口，不依赖主窗口显示
    toplevel .netNameExchange
    wm title .netNameExchange "Replace Net Names"
    wm resizable .netNameExchange 0 0
    # 注释编码已统一为 GBK，原注释内容已清理。
    # wm transient .netNameExchange .
    # 寮哄埗鏄剧ず骞剁疆椤?
    wm deiconify .netNameExchange
    raise .netNameExchange
    focus .netNameExchange

    set font {TkDefaultFont 10}
    set pad 8

    frame .netNameExchange.inputFrame -padx $pad -pady $pad
    label .netNameExchange.inputFrame.oldLabel -text "要替换的网络名：" -font $font
    entry .netNameExchange.inputFrame.oldEntry -width 30 -font $font
    label .netNameExchange.inputFrame.newLabel -text "目标网络名：" -font $font
    entry .netNameExchange.inputFrame.newEntry -width 30 -font $font

    grid .netNameExchange.inputFrame.oldLabel -row 0 -column 0 -sticky w -pady 2
    grid .netNameExchange.inputFrame.oldEntry -row 0 -column 1 -sticky w -pady 2
    grid .netNameExchange.inputFrame.newLabel -row 1 -column 0 -sticky w -pady 2
    grid .netNameExchange.inputFrame.newEntry -row 1 -column 1 -sticky w -pady 2

    frame .netNameExchange.btnFrame -padx $pad -pady $pad
    button .netNameExchange.btnFrame.ok -text "确认" -font $font \
        -command [list ::capMenuUtil::performNetNameExchange $pLib \
        [list .netNameExchange.inputFrame.oldEntry] \
        [list .netNameExchange.inputFrame.newEntry] \
        [list .netNameExchange]]
    button .netNameExchange.btnFrame.cancel -text "取消" -font $font \
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
        tk_messageBox -icon warning -message "请输入要替换的网络名字符串"
        return
    }
    destroy [lindex $window 0]
    set ::capMenuUtil::dialogResult 1
    ::capMenuUtil::NetNameExchange $pLib $oldString $newString
}


proc ::capMenuUtil::NetNameExchange { pLib oldString newString } {
    # 注释编码已统一为 GBK，原注释内容已清理。
    set replaceMap [list $oldString $newString]
    
    # 已生成的随机名称集合，确保唯一性
    set lStatus [DboState]
    # 鑾峰彇鎵ц鐨勮璁″璞?
    set lDesign [GetActivePMDesign]
    
    # 检查是否有活动设计
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "未找到当前打开的设计！"
        return
    }
    
    # 计算总页面数用于进度显示
    set totalPages [::capMenuUtil::countTotalPages $lDesign $lStatus]
    if {$totalPages == 0} {
        tk_messageBox -icon warning -message "当前设计中未找到页面！"
        return
    }
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    set progressWindow [::capMenuUtil::showNetExchange处理中Dialog $totalPages $oldString $newString]
    set currentPage 0
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    update
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    # 获取第一个原理图视图
    set lView [$lSchematicIter NextView $lStatus]
    set SchNum 0
    set lNullObj NULL
    set totalReplacements 0  ;# 缁熻鎬绘浛鎹㈡鏁?
    
    while { $lView != $lNullObj} {
        incr SchNum
        # 从DboView转换为DboSchematic
        set lSchematic [DboViewToDboSchematic $lView]
        # 新建页面迭代器，用于遍历
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        # 鑾峰彇绗竴椤?
        set lPage [$lPagesIter NextPage $lStatus]
        set PageNum 0
        
        while {$lPage!=$lNullObj} {
            incr PageNum
            incr currentPage
            
            # 更新进度
            ::capMenuUtil::updateProgress $progressWindow $currentPage $totalPages
            
            puts "\n###############################Process Schematic $SchNum"
            puts "###############################Process Page $PageNum"
            
            ##################################开始替换Net##################################
            puts "Start processing network name replacement"
            
            set lWiresIter [$lPage NewWiresIter $lStatus]
            # 鑾峰彇绗竴鏉″绾?
            set lWire [$lWiresIter NextWire $lStatus] 
            while {$lWire != $lNullObj} {
                set lAliasIter [$lWire NewAliasesIter $lStatus]
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lAlias [$lAliasIter NextAlias $lStatus]
                while { $lAlias!=$lNullObj} {
                    set lAliasString [DboTclHelper_sMakeCString]
                    $lAlias GetName $lAliasString
                    set lNameString [DboTclHelper_sGetConstCharPtr $lAliasString]
                    # 如果含有目标字符，则进行替换
                    if {[string first $oldString $lNameString] != -1} {
                        incr totalReplacements
                        puts "\nFind the network name: $lNameString"
                        set lNewNameString [string map $replaceMap $lNameString]
                        set lName [DboTclHelper_sMakeCString $lNewNameString]
                        $lAlias SetName $lName
                        set lName [DboTclHelper_sGetConstCharPtr $lName]
                        puts "The network name has been replaced by: $lName"
                    }
                    
                    # 注释编码已统一为 GBK，原注释内容已清理。
                    set lAlias [$lAliasIter NextAlias $lStatus]
                }
                delete_DboWireAliasesIter $lAliasIter
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lWire [$lWiresIter NextWire $lStatus] 
            }
            delete_DboPageWiresIter $lWiresIter
            
            puts "\nNetwork name replacement ends"
            ##################################结束替换Net##################################
            
            ##################################开始替换port##################################
            puts "Start processing port name replacement"
            set lPortsIter [$lPage NewPortsIter $lStatus]
            # 注释编码已统一为 GBK，原注释内容已清理。
            set lPort [$lPortsIter NextPort $lStatus]
            while {$lPort!=$lNullObj} {
                set lPortString [DboTclHelper_sMakeCString]
                $lPort GetName $lPortString
                set lNameString [DboTclHelper_sGetConstCharPtr $lPortString]
                # 如果含有目标字符，则进行替换
                if {[string first $oldString $lNameString] != -1} {
                    incr totalReplacements
                    puts "\nFind the port name: $lNameString"
                    set lNewNameString [string map $replaceMap $lNameString]
                    set lName [DboTclHelper_sMakeCString $lNewNameString]
                    $lPort SetName $lName
                    set lName [DboTclHelper_sGetConstCharPtr $lName]
                    puts "The port name has been replaced by: $lName"
                }

                # 注释编码已统一为 GBK，原注释内容已清理。
                set lPort [$lPortsIter NextPort $lStatus]
            }  
            delete_DboPagePortsIter $lPortsIter
            
            puts "\nPort name replacement ends"
            ##################################结束替换port##################################
            
            ##################################开始替换Offpage##################################
            puts "Start processing Offpage name replacement"
            # 注释编码已统一为 GBK，原注释内容已清理。
            if {[info exists ::IterDefs_ALL]} {
                set lOffPagesIter [$lPage NewOffPageConnectorsIter $lStatus $::IterDefs_ALL]
            } else {
                set lOffPagesIter [$lPage NewOffPageConnectorsIter $lStatus]
            }
            # 注释编码已统一为 GBK，原注释内容已清理。
            set lOffPage [$lOffPagesIter NextOffPageConnector $lStatus]
            while {$lOffPage!=$lNullObj} {
                set lOffPageString [DboTclHelper_sMakeCString]
                $lOffPage GetName $lOffPageString
                set lNameString [DboTclHelper_sGetConstCharPtr $lOffPageString]
                # 如果含有目标字符，则进行替换
                if {[string first $oldString $lNameString] != -1} {
                    incr totalReplacements
                    puts "\nFind the Offpage name: $lNameString"
                    set lNewNameString [string map $replaceMap $lNameString]
                    set lName [DboTclHelper_sMakeCString $lNewNameString]
                    $lOffPage SetName $lName
                    set lName [DboTclHelper_sGetConstCharPtr $lName]
                    puts "The Offpage name has been replaced by: $lName"
                }
            
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lOffPage [$lOffPagesIter NextOffPageConnector $lStatus]
            }
            delete_DboPageOffPageConnectorsIter $lOffPagesIter
            puts "\nOffpage name replacement ends"
            ##################################结束替换Offpage##################################
            
            ##################################开始替换power##################################
            puts "Start processing Power name replacement"
            set lGlobalsIter [$lPage NewGlobalsIter $lStatus]
            # 获取第一个全局对象
            set lGlobal [$lGlobalsIter NextGlobal $lStatus]
            while { $lGlobal!=$lNullObj } { 
                set lPropsIter [$lGlobal NewEffectivePropsIter $lStatus]
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lPrpName [DboTclHelper_sMakeCString]
                set lPrpValue [DboTclHelper_sMakeCString]
                set lPrpType [DboTclHelper_sMakeDboValueType]
                set lEditable [DboTclHelper_sMakeInt]
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lStatus [$lPropsIter NextEffectiveProp $lPrpName $lPrpValue $lPrpType $lEditable]
                while { [$lStatus OK] } {
                    set lNameString [DboTclHelper_sGetConstCharPtr $lPrpValue]
                    # 如果含有目标字符，则进行替换
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
                # 获取下一个全局对象
                set lGlobal [$lGlobalsIter NextGlobal $lStatus]
            }
            delete_DboPageGlobalsIter $lGlobalsIter
            puts "\nPower name replacement ends"
            ##################################结束替换power##################################
            
            # 注释编码已统一为 GBK，原注释内容已清理。
            set lPage [$lPagesIter NextPage $lStatus]
        }
        delete_DboSchematicPagesIter $lPagesIter
        # 获取下一个原理图视图
        set lView [$lSchematicIter NextView $lStatus]
    }
    delete_DboLibViewsIter $lSchematicIter
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    destroy $progressWindow
    
    # 显示完成结果
    tk_messageBox -message "Replace Net Names完成！\n替换总数：$totalReplacements" -icon info
}

# ////////////////////////////////////////////////////////////////////////////////
# 注释编码已统一为 GBK，原注释内容已清理。
# ////////////////////////////////////////////////////////////////////////////////

proc ::capMenuUtil::NcPartGrayed { pLib } {
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "未找到当前打开的设计！"
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
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lPropNameCStr [DboTclHelper_sMakeCString "Value"]
                set lPropValueCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lPropNameCStr $lPropValueCStr
                set lPropValueString [DboTclHelper_sGetConstCharPtr $lPropValueCStr]
                
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lPropPNNameCStr [DboTclHelper_sMakeCString "Part Number"]
                set lPropPNCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lPropPNNameCStr $lPropPNCStr
                set lPropPNString [DboTclHelper_sGetConstCharPtr $lPropPNCStr]

                # 判断是否为NC元件
                if { $lPropPNString == "" || [regexp "NC/" $lPropValueString] } {
                    # 注释编码已统一为 GBK，原注释内容已清理。
                    set lColorPropNameCStr [DboTclHelper_sMakeCString "Color"]
                    set lColorPropValueCStr [DboTclHelper_sMakeCString "RGB(192,192,192)"]
                    $lInst SetEffectivePropStringValue $lColorPropNameCStr $lColorPropValueCStr
                    
                    # 注释编码已统一为 GBK，原注释内容已清理。
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
                    # 非NC元件恢复默认颜色
                    set lColorPropNameCStr [DboTclHelper_sMakeCString "Color"]
                    set lColorPropValueCStr [DboTclHelper_sMakeCString "Default"]
                    $lInst SetEffectivePropStringValue $lColorPropNameCStr $lColorPropValueCStr
                    
                    # 注释编码已统一为 GBK，原注释内容已清理。
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
# 注释编码已统一为 GBK，原注释内容已清理。
# ////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::GroundNameVisible { pLib } {
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "未找到当前打开的设计！"
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
                        # 已生成的随机名称集合，确保唯一性
                        if { [regexp "GND" $netName] || $netName == "0" } {
                            set varNullObj NULL
                            set pDispProp [$lGlobal GetDisplayProp $lPrpName $lStatus]
                            if { $pDispProp == $varNullObj } {
                                # 注释编码已统一为 GBK，原注释内容已清理。
                                set rotation 0
                                set logfont [DboTclHelper_sMakeLOGFONT]
                                set lColor $::DboValue_DEFAULT_OBJECT_COLOR
                                set displocation [DboTclHelper_sMakeCPoint 0 10]
                                set pNewDispProp [$lGlobal NewDisplayProp $lStatus $lPrpName $displocation $rotation $logfont $lColor]
                                $pNewDispProp SetDisplayType 1 ;# VALUE_ONLY
                            } else {
                                # 已有属性，强制显示Value
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
# 注释编码已统一为 GBK，原注释内容已清理。
# ////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::ResetNetnameColor { pLib } {
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "未找到当前打开的设计！"
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
            # 重置导线别名颜色
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

            # 重置页间连接颜色
            set lOffPagesIter [$lPage NewOffPageConnectorsIter $lStatus]
            set lOffPage [$lOffPagesIter NextOffPageConnector $lStatus]
            while {$lOffPage!=$lNullObj} {
                set lColorPropNameCStr [DboTclHelper_sMakeCString "Color"]
                set lColorPropValueCStr [DboTclHelper_sMakeCString "Default"]
                $lOffPage SetEffectivePropStringValue $lColorPropNameCStr $lColorPropValueCStr
                
                # 注释编码已统一为 GBK，原注释内容已清理。
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

            # 重置端口颜色
            set lPortsIter [$lPage NewPortsIter $lStatus]
            set lPort [$lPortsIter NextPort $lStatus]
            while {$lPort!=$lNullObj} {
                set lColorPropNameCStr [DboTclHelper_sMakeCString "Color"]
                set lColorPropValueCStr [DboTclHelper_sMakeCString "Default"]
                $lPort SetEffectivePropStringValue $lColorPropNameCStr $lColorPropValueCStr
                
                # 注释编码已统一为 GBK，原注释内容已清理。
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
# 注释编码已统一为 GBK，原注释内容已清理。
# ////////////////////////////////////////////////////////////////////////////////
# 1. 随机字符串生成器 - 兼容Tcl 8.4/8.5

# ////////////////////////////////////////////////////////////////////////////////
# 安全反操作：隐藏/显示类操作，仅切换显示属性，不做快照恢复。
# ////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::GroundNameHidden { pLib } {
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "未找到当前打开的设计！"
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
        tk_messageBox -icon error -message "未找到当前打开的设计！"
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
        tk_messageBox -icon error -message "未找到当前打开的设计！"
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
        tk_messageBox -icon error -message "未找到当前打开的设计！"
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
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    set prefix "XX_"
    set chars "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    set charCount [string length $chars]
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    while {1} {
        set str $prefix
        # 已生成的随机名称集合，确保唯一性
        for {set i 0} {$i < 8} {incr i} {
            append str [string index $chars [expr {int(rand() * $charCount)}]]
        }
        
        # 注释编码已统一为 GBK，原注释内容已清理。
        if {[lsearch $generatedNames $str] == -1} {
            lappend generatedNames $str
            return $str
        }
    }
}

# 已生成的随机名称集合，确保唯一性
proc ::capMenuUtil::normalizeNetName {netName} {
    # 去除前后空格并转为大写，确保相同网络的不同表示形式被识别为同一网络
    return [string trim [string toupper $netName]]
}

# 注释编码已统一为 GBK，原注释内容已清理。
proc ::capMenuUtil::showNetExchange处理中Dialog {totalPages oldString newString} {
    set progressWindow .netExchangeProgress
    if {[winfo exists $progressWindow]} {
        destroy $progressWindow
    }

    # 注释编码已统一为 GBK，原注释内容已清理。
    toplevel $progressWindow
    wm title $progressWindow "Replace Net Names"
    wm resizable $progressWindow 0 0
    wm attributes $progressWindow -toolwindow 1
    # 注释编码已统一为 GBK，原注释内容已清理。
    # wm transient $progressWindow .
    # 寮哄埗鏄剧ず骞剁疆椤?
    wm deiconify $progressWindow
    raise $progressWindow
    focus $progressWindow

    # 设置字体和颜色（兼容16.6的默认字体）
    set font {TkDefaultFont 10}
    set bgColor "#f0f0f0"
    set fgColor "#333333"
    
    # 配置窗口样式
    $progressWindow configure -bg $bgColor
    
    # 创建内容框架
    set contentFrame [frame $progressWindow.content -bg $bgColor -padx 20 -pady 20]
    pack $contentFrame -fill both -expand 1
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    label $contentFrame.label -text "正在替换网络名..." \
        -font $font -fg $fgColor -bg $bgColor
    pack $contentFrame.label -pady 5
    
    # 显示替换信息
    label $contentFrame.replaceInfo -text "正在替换：\"$oldString\" -> \"$newString\"" \
        -font [list TkDefaultFont 9] -fg $fgColor -bg $bgColor -wraplength 300
    pack $contentFrame.replaceInfo -pady 5
    
    # 添加进度文本
    label $contentFrame.status -text "第 0 / $totalPages 页" \
        -font [list TkDefaultFont 9] -fg $fgColor -bg $bgColor
    pack $contentFrame.status -pady 5
    
    # 使用传统进度条（不使用ttk，兼容旧版本Tk)
    frame $contentFrame.progress -relief sunken -bd 1 -width 300 -height 20
    canvas $contentFrame.progress.canvas -width 296 -height 16 -bg white
    $contentFrame.progress.canvas create rectangle 0 0 0 16 -fill blue -outline blue -tags bar
    pack $contentFrame.progress.canvas -fill both -expand 1
    pack $contentFrame.progress -pady 10 -fill x
    
    # 添加说明文字
    label $contentFrame.note -text "请稍候，不要关闭 OrCAD..." \
        -font [list TkDefaultFont 8] -fg "#666666" -bg $bgColor -wraplength 300
    pack $contentFrame.note -pady 5
    # 注释编码已统一为 GBK，原注释内容已清理。
    update

    # 居中显示弹窗
    update idletasks
    set x [expr {([winfo screenwidth .] - [winfo reqwidth $progressWindow]) / 2}]
    set y [expr {([winfo screenheight .] - [winfo reqheight $progressWindow]) / 2}]
    wm geometry $progressWindow "+$x+$y"

    # 强制处理所有挂起的事件
    update

    return $progressWindow
}

# 4. 创建并显示随机化处理弹窗（优化显示）
proc ::capMenuUtil::show处理中Dialog {totalPages} {
    set progressWindow .randomizeProgress
    if {[winfo exists $progressWindow]} {
        destroy $progressWindow
    }

    # 注释编码已统一为 GBK，原注释内容已清理。
    toplevel $progressWindow
    wm title $progressWindow "处理中"
    wm resizable $progressWindow 0 0
    wm attributes $progressWindow -toolwindow 1
    # 注释编码已统一为 GBK，原注释内容已清理。
    # wm transient $progressWindow .
    # 寮哄埗鏄剧ず骞剁疆椤?
    wm deiconify $progressWindow
    raise $progressWindow
    focus $progressWindow

    # 设置字体和颜色（兼容16.6的默认字体）
    set font {TkDefaultFont 10}
    set bgColor "#f0f0f0"
    set fgColor "#333333"
    
    # 配置窗口样式
    $progressWindow configure -bg $bgColor
    
    # 创建内容框架
    set contentFrame [frame $progressWindow.content -bg $bgColor -padx 20 -pady 20]
    pack $contentFrame -fill both -expand 1
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    label $contentFrame.label -text "正在Randomize Net Names..." \
        -font $font -fg $fgColor -bg $bgColor
    pack $contentFrame.label -pady 5
    
    # 添加进度文本
    label $contentFrame.status -text "第 0 / $totalPages 页" \
        -font [list TkDefaultFont 9] -fg $fgColor -bg $bgColor
    pack $contentFrame.status -pady 5
    
    # 使用传统进度条（不使用ttk，兼容旧版本Tk)
    frame $contentFrame.progress -relief sunken -bd 1 -width 300 -height 20
    canvas $contentFrame.progress.canvas -width 296 -height 16 -bg white
    $contentFrame.progress.canvas create rectangle 0 0 0 16 -fill blue -outline blue -tags bar
    pack $contentFrame.progress.canvas -fill both -expand 1
    pack $contentFrame.progress -pady 10 -fill x
    
    # 添加说明文字
    label $contentFrame.note -text "请稍候，不要关闭 OrCAD..." \
        -font [list TkDefaultFont 8] -fg "#666666" -bg $bgColor -wraplength 300
    pack $contentFrame.note -pady 5
    # 注释编码已统一为 GBK，原注释内容已清理。
    update

    # 居中显示弹窗
    update idletasks
    set x [expr {([winfo screenwidth .] - [winfo reqwidth $progressWindow]) / 2}]
    set y [expr {([winfo screenheight .] - [winfo reqheight $progressWindow]) / 2}]
    wm geometry $progressWindow "+$x+$y"

    # 强制处理所有挂起的事件
    update

    return $progressWindow

}

# 注释编码已统一为 GBK，原注释内容已清理。
proc ::capMenuUtil::updateProgress {progressWindow current total} {
    set statusText "第 $current / $total 页"
    $progressWindow.content.status configure -text $statusText
    
    # 璁＄畻杩涘害鐧惧垎姣?
    set percent [expr {double($current) / $total}]
    set width [expr {int(296 * $percent)}]
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    $progressWindow.content.progress.canvas coords bar 0 0 $width 16
    
    # 强制更新界面
    update idletasks
}

# 已生成的随机名称集合，确保唯一性
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

# 注释编码已统一为 GBK，原注释内容已清理。
proc ::capMenuUtil::RandomizeNetNames {pLib} {
    
    
    # 初始化缓存（使用list替代dict，兼容Tcl 8.4的限制）
    variable netNameMap
    variable generatedNames
    set netNameMap [list]
    catch {array unset netNameMapArray}
    array set netNameMapArray {}
    set generatedNames [list]
    
    # 获取设计信息
    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    
    # 检查是否有活动设计
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "未找到当前打开的设计！\n请先打开一个设计。"
        return
    }
    
    # 计算总页面数用于进度显示
    set totalPages [::capMenuUtil::countTotalPages $lDesign $lStatus]
    if {$totalPages == 0} {
        tk_messageBox -icon warning -message "当前设计中未找到页面！"
        return
    }
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    set progressWindow [::capMenuUtil::show处理中Dialog $totalPages]
    set currentPage 0
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    update
    
    # 兼容16.6的迭代器创建方式
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    set lView [$lSchematicIter NextView $lStatus]
    set lNullObj NULL
    set SchNum 0                      ;# 原理图计数器
    
    # 步骤2：遍历所有原理图
    while {$lView != $lNullObj} {
        incr SchNum
        set lSchematic [DboViewToDboSchematic $lView]
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]
        set PageNum 0                  ;# 椤甸潰璁℃暟鍣?

        # 姝ラ3锛氶亶鍘嗗綋鍓嶅師鐞嗗浘鐨勬墍鏈夐〉闈?
        while {$lPage != $lNullObj} {
            incr PageNum
            incr currentPage
            
            # 注释编码已统一为 GBK，原注释内容已清理。
            ::capMenuUtil::updateProgress $progressWindow $currentPage $totalPages
            
            puts "\n===================== 处理中 Schematic $SchNum, Page $PageNum ====================="

            # //////////////////////////////////////////////////////////////////////
            # 注释编码已统一为 GBK，原注释内容已清理。
            # //////////////////////////////////////////////////////////////////////
            puts "\n[clock format [clock seconds] -format {%H:%M:%S}] - 处理中 Wire Aliases..."
            set lWiresIter [$lPage NewWiresIter $lStatus]
            set lWire [$lWiresIter NextWire $lStatus] 
            
            while {$lWire != $lNullObj} {
                set lAliasIter [$lWire NewAliasesIter $lStatus]
                set lAlias [$lAliasIter NextAlias $lStatus]
                
                while { $lAlias != $lNullObj } {
                    # 已生成的随机名称集合，确保唯一性
                    set lAliasString [DboTclHelper_sMakeCString]
                    $lAlias GetName $lAliasString
                    set lNameString [DboTclHelper_sGetConstCharPtr $lAliasString]
                    
                    # 注释编码已统一为 GBK，原注释内容已清理。
                    if {![string match "XX_*" $lNameString] && $lNameString ne ""} {
                        # 注释编码已统一为 GBK，原注释内容已清理。
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
                        
                        # 注释编码已统一为 GBK，原注释内容已清理。
                        set lNewName [DboTclHelper_sMakeCString $newName]
                        $lAlias SetName $lNewName
                    }
                    
                    # 注释编码已统一为 GBK，原注释内容已清理。
                    set lAlias [$lAliasIter NextAlias $lStatus]
                }
                
                delete_DboWireAliasesIter $lAliasIter
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lWire [$lWiresIter NextWire $lStatus] 
            }
            
            delete_DboPageWiresIter $lWiresIter
            puts "[clock format [clock seconds] -format {%H:%M:%S}] - Wire Aliases processed"

            # //////////////////////////////////////////////////////////////////////
            # 注释编码已统一为 GBK，原注释内容已清理。
            # //////////////////////////////////////////////////////////////////////
            puts "\n[clock format [clock seconds] -format {%H:%M:%S}] - 处理中 Ports..."
            set lPortsIter [$lPage NewPortsIter $lStatus]
            set lPort [$lPortsIter NextPort $lStatus]
            
            while {$lPort != $lNullObj} {
                set lPortString [DboTclHelper_sMakeCString]
                $lPort GetName $lPortString
                set lNameString [DboTclHelper_sGetConstCharPtr $lPortString]
                
                # 注释编码已统一为 GBK，原注释内容已清理。
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
                    
                    # 注释编码已统一为 GBK，原注释内容已清理。
                    set lNewName [DboTclHelper_sMakeCString $newName]
                    $lPort SetName $lNewName
                }

                # 注释编码已统一为 GBK，原注释内容已清理。
                set lPort [$lPortsIter NextPort $lStatus]
            }  
            
            delete_DboPagePortsIter $lPortsIter
            puts "[clock format [clock seconds] -format {%H:%M:%S}] - Ports processed"

            # //////////////////////////////////////////////////////////////////////
            # 注释编码已统一为 GBK，原注释内容已清理。
            # //////////////////////////////////////////////////////////////////////
            puts "\n[clock format [clock seconds] -format {%H:%M:%S}] - 处理中 Offpage Connectors..."
            # 鍏煎16.6鐨凮ffPage杩唬鍣ㄥ弬鏁?
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
                
                # 注释编码已统一为 GBK，原注释内容已清理。
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
                    
                    # 注释编码已统一为 GBK，原注释内容已清理。
                    set lNewName [DboTclHelper_sMakeCString $newName]
                    $lOffPage SetName $lNewName
                }
                
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lOffPage [$lOffPagesIter NextOffPageConnector $lStatus]
            }
            
            delete_DboPageOffPageConnectorsIter $lOffPagesIter
            puts "[clock format [clock seconds] -format {%H:%M:%S}] - Offpage Connectors processed"

            # //////////////////////////////////////////////////////////////////////
            # 注释编码已统一为 GBK，原注释内容已清理。
            # //////////////////////////////////////////////////////////////////////
            puts "\n[clock format [clock seconds] -format {%H:%M:%S}] - 处理中 Power..."
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
                        
                        # 注释编码已统一为 GBK，原注释内容已清理。
                        set isFilePath [expr {[string match "*:*" $lNameString] || [string match "*\\*" $lNameString] || [string match "*/*" $lNameString]}]
                        set isNumeric [expr {[string is digit $lNameString]}]
                        
                        # 过滤条件：不是XX_前缀、不包含GND、不是默认值、不是文件路径、不是纯数字
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
                            
                            # 注释编码已统一为 GBK，原注释内容已清理。
                            set lNewName [DboTclHelper_sMakeCString $newName]
                            $lGlobal SetEffectivePropStringValue $lPrpName $lNewName
                        }
                    }
                
                    set lStatus [$lPropsIter NextEffectiveProp $lPrpName $lPrpValue $lPrpType $lEditable]
                }
                
                delete_DboEffectivePropsIter $lPropsIter			
                # 获取下一个全局对象
                set lGlobal [$lGlobalsIter NextGlobal $lStatus]
            }
            
            delete_DboPageGlobalsIter $lGlobalsIter
            puts "[clock format [clock seconds] -format {%H:%M:%S}] - Power/Ground processed"

            # 注释编码已统一为 GBK，原注释内容已清理。
            set lPage [$lPagesIter NextPage $lStatus]
        }
        
        delete_DboSchematicPagesIter $lPagesIter
        # 处理下一个原理图
        set lView [$lSchematicIter NextView $lStatus]
    }
    
    delete_DboLibViewsIter $lSchematicIter

    # 注释编码已统一为 GBK，原注释内容已清理。
    destroy $progressWindow

    
}


# 注释编码已统一为 GBK，原注释内容已清理。
proc ::capMenuUtil::DeleteAllGraphic { pLib } {
    
	
	# 初始化状态对象与空对象标识（文档3.2节标准操作）
    set lStatus [DboState]
    set lNullObj NULL
    set lDeletedCount 0

    # 注释编码已统一为 GBK，原注释内容已清理。
    set lDesign [GetActivePMDesign]
    if {$lDesign == $lNullObj} {
        puts "Error: 未找到当前打开的设计！ Please open a design first."
        $lStatus -delete
        return
    }
	# 计算总页面数用于进度显示
    set totalPages [::capMenuUtil::countTotalPages $lDesign $lStatus]
    if {$totalPages == 0} {
        tk_messageBox -icon warning -message "当前设计中未找到页面！"
        $lStatus -delete
        return
    }
	# 注释编码已统一为 GBK，原注释内容已清理。
    set progressWindow [::capMenuUtil::showDeleteGraphicProgressDialog $totalPages]
    set currentPage 0
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    update
	

    # 注释编码已统一为 GBK，原注释内容已清理。
    set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    set lView [$lSchematicIter NextView $lStatus]

    while { $lView != $lNullObj } {
        # 注释编码已统一为 GBK，原注释内容已清理。
        set lSchematic [DboViewToDboSchematic $lView]
        
        # 注释编码已统一为 GBK，原注释内容已清理。
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        set lPage [$lPagesIter NextPage $lStatus]

        while { $lPage != $lNullObj } {
		    incr currentPage
            # 更新进度
            ::capMenuUtil::updateProgress $progressWindow $currentPage $totalPages
			
            # 先收集所有需要删除的图形对象，然后再统一删除（避免迭代器状态问题）
            set bitmapsToDelete [list]
            
            # 注释编码已统一为 GBK，原注释内容已清理。
            set lGraphicsIter [$lPage NewCommentGraphicsIter $lStatus]
            set lGraphic [$lGraphicsIter NextCommentGraphic $lStatus]
            while { $lGraphic != $lNullObj } {
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lObjType [$lGraphic GetObjectType]
				
                if {$lObjType == $::DboBaseObject_GRAPHIC_BITMAP_INST||$::DboBaseObject_GRAPHIC_LINE_INST||$::DboBaseObject_GRAPHIC_BOX_INST||$::DboBaseObject_GRAPHIC_ARC_INST||$::DboBaseObject_GRAPHIC_BEZIER_INST} {
                    # 已生成的随机名称集合，确保唯一性
					
                    set lImageName [DboTclHelper_sMakeCString]
                    $lGraphic GetName $lImageName  
					
                    set lImageNameStr [DboTclHelper_sGetConstCharPtr $lImageName]
                    ::capMenuUtil::logDebug "Found Graphic: $lImageNameStr"
                    
                    # 添加到待删除列表
                    lappend bitmapsToDelete $lGraphic
                }
                
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lGraphic [$lGraphicsIter NextCommentGraphic $lStatus]
            }

            # 閲婃斁鍥惧舰瀵硅薄杩唬鍣?
            delete_DboPageCommentGraphicsIter $lGraphicsIter

            # 注释编码已统一为 GBK，原注释内容已清理。
            foreach bitmap $bitmapsToDelete {
                $lPage DeleteCommentGraphic $bitmap
                incr lDeletedCount
                ::capMenuUtil::logDebug "Deleted Graphic"
            }

            # 注释编码已统一为 GBK，原注释内容已清理。
            set lPage [$lPagesIter NextPage $lStatus]
        }

        # 閲婃斁椤甸潰杩唬鍣?
        delete_DboSchematicPagesIter $lPagesIter

        # 迭代下一个原理图
        set lView [$lSchematicIter NextView $lStatus]
    }

    # 释放原理图迭代器
    delete_DboLibViewsIter $lSchematicIter

    # 注释编码已统一为 GBK，原注释内容已清理。
    destroy $progressWindow

    # 注释编码已统一为 GBK，原注释内容已清理。
    $lStatus -delete
}

# 鍒涘缓骞舵樉绀哄垹闄ゅ浘褰㈠鐞嗗脊绐?
proc ::capMenuUtil::showDeleteGraphicProgressDialog {totalPages} {
    set progressWindow .deleteGraphicProgress
    if {[winfo exists $progressWindow]} {
        destroy $progressWindow
    }

    # 注释编码已统一为 GBK，原注释内容已清理。
    toplevel $progressWindow
    wm title $progressWindow "删除图形对象"
    wm resizable $progressWindow 0 0
    wm attributes $progressWindow -toolwindow 1
    # 注释编码已统一为 GBK，原注释内容已清理。
    # wm transient $progressWindow .
    # 寮哄埗鏄剧ず骞剁疆椤?
    wm deiconify $progressWindow
    raise $progressWindow
    focus $progressWindow

    # 设置字体和颜色（兼容16.6的默认字体）
    set font {TkDefaultFont 10}
    set bgColor "#f0f0f0"
    set fgColor "#333333"
    
    # 配置窗口样式
    $progressWindow configure -bg $bgColor
    
    # 创建内容框架
    set contentFrame [frame $progressWindow.content -bg $bgColor -padx 20 -pady 20]
    pack $contentFrame -fill both -expand 1
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    label $contentFrame.label -text "正在删除图形对象..." \
        -font $font -fg $fgColor -bg $bgColor
    pack $contentFrame.label -pady 5
    
    # 添加进度文本
    label $contentFrame.status -text "第 0 / $totalPages 页" \
        -font [list TkDefaultFont 9] -fg $fgColor -bg $bgColor
    pack $contentFrame.status -pady 5
    
    # 使用传统进度条（不使用ttk，兼容旧版本Tk)
    frame $contentFrame.progress -relief sunken -bd 1 -width 300 -height 20
    canvas $contentFrame.progress.canvas -width 296 -height 16 -bg white
    $contentFrame.progress.canvas create rectangle 0 0 0 16 -fill blue -outline blue -tags bar
    pack $contentFrame.progress.canvas -fill both -expand 1
    pack $contentFrame.progress -pady 10 -fill x
    
    # 添加说明文字
    label $contentFrame.note -text "请稍候，不要关闭 OrCAD..." \
        -font [list TkDefaultFont 8] -fg "#666666" -bg $bgColor -wraplength 300
    pack $contentFrame.note -pady 5
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    update

    # 居中显示弹窗
    update idletasks
    set x [expr {([winfo screenwidth .] - [winfo reqwidth $progressWindow]) / 2}]
    set y [expr {([winfo screenheight .] - [winfo reqheight $progressWindow]) / 2}]
    wm geometry $progressWindow "+$x+$y"

    # 强制处理所有挂起的事件
    update

    return $progressWindow
}


# ////////////////////////////////////////////////////////////////////////////////
# 一键混淆补充：隐藏器件型号、封装等敏感显示属性。
# ////////////////////////////////////////////////////////////////////////////////
namespace eval ::capMenuUtil {
    variable toolVersion "V1.8"
    variable sensitiveDisplayProperties [list "Value" "规格型号" "Part Number" "PCB Footprint" "Footprint" "Source Package" "Source Part" "Part" "Package"]
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
        tk_messageBox -icon error -message "未找到当前打开的设计！"
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
    # 已生成的随机名称集合，确保唯一性
    set lStatus [DboState]
	
    # 鑾峰彇鎵ц鐨勮璁″璞?
    set lDesign [GetActivePMDesign]
    
    # 检查是否有活动设计
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "未找到当前打开的设计！"
        return
    }
    # 注释编码已统一为 GBK，原注释内容已清理。
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    
    # 获取第一个原理图视图
    set lView [$lSchematicIter NextView $lStatus]
    set SchNum 0
    set lNullObj NULL
	
    while { $lView != $lNullObj } {
        incr SchNum
		
        # 从DboView转换为DboSchematic
        set lSchematic [DboViewToDboSchematic $lView]
        # 新建页面迭代器，用于遍历
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        # 鑾峰彇绗竴椤?
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
                # 鑾峰彇鍣ㄤ欢浣嶅彿锛圧eference Designator锛?
                set lRefDesNameCStr [DboTclHelper_sMakeCString "Reference"]
                set lRefDesValueCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lRefDesNameCStr $lRefDesValueCStr
                set lRefDesString [DboTclHelper_sGetConstCharPtr $lRefDesValueCStr]
                
                ::capMenuUtil::logDebug "  Checking component #$instCount : RefDes = $lRefDesString"

                # 注释编码已统一为 GBK，原注释内容已清理。
                if { [regexp -nocase {^U} $lRefDesString] } {
                    incr uInstCount
                    # 将器件转换为PlacedInst对象
                    set lPlacedInst [DboPartInstToDboPlacedInst $lInst]
                    if { $lPlacedInst != $lNullObj } {
                        # 注释编码已统一为 GBK，原注释内容已清理。
                        set lDisplayPropsIter [$lPlacedInst NewDisplayPropsIter $lStatus]
                        set propCount 0
                        set valueFound 0
                        set lDProp [$lDisplayPropsIter NextProp $lStatus]
                        
                        while { $lDProp != $lNullObj } {
                            incr propCount
                            # 注释编码已统一为 GBK，原注释内容已清理。
                            set lNameCStr [DboTclHelper_sMakeCString]
                            $lDProp GetName $lNameCStr
                            set lNameString [DboTclHelper_sGetConstCharPtr $lNameCStr]
                            ::capMenuUtil::logDebug " sx #$propCount: $lNameString"
                            # 注释编码已统一为 GBK，原注释内容已清理。
                            if {[string equal -nocase $lNameString "Value"]} {
                                catch {
                                    $lDProp SetDisplayType 0
                                    ::capMenuUtil::logDebug "    Success: Value visibility for $lRefDesString set to 0 (invisible)."
                                } errMsg
                                if {$errMsg ne ""} {
                                    ::capMenuUtil::logDebug "    Warning: Failed to set Value visibility for $lRefDesString - $errMsg"
                                }
                                set valueFound 1 ;# 标记为已找到
                            }
                            
                            # 释放CString内存
                            DboTclHelper_sDeleteCString $lNameCStr
                            
                            # 注释编码已统一为 GBK，原注释内容已清理。
                            set lDProp [$lDisplayPropsIter NextProp $lStatus]
                        }
                        
                        if {!$valueFound} {
                           puts "    Warning: 'Value' property not found for component $lRefDesString."
                        }
                        
                        # 释放显示属性迭代器
                        delete_DboDisplayPropsIter $lDisplayPropsIter
                    }
                }
                
                # 释放CString内存
                DboTclHelper_sDeleteCString $lRefDesNameCStr
                DboTclHelper_sDeleteCString $lRefDesValueCStr
                
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lInst [$lPartInstsIter NextPartInst $lStatus] 
            }
            
            # 注释编码已统一为 GBK，原注释内容已清理。
            delete_DboPagePartInstsIter $lPartInstsIter
            
            # 注释编码已统一为 GBK，原注释内容已清理。
            set lPage [$lPagesIter NextPage $lStatus]
        }
        
        # 閲婃斁椤甸潰杩唬鍣?
        delete_DboSchematicPagesIter $lPagesIter
        
        # 获取下一个原理图视图
        set lView [$lSchematicIter NextView $lStatus]
    }
    
    # 释放原理图视图迭代器
    delete_DboLibViewsIter $lSchematicIter
    
    puts "\nOperation completed."
}
proc ::capMenuUtil::HideALLcomponent { pLib } {
    # 已生成的随机名称集合，确保唯一性
    set lStatus [DboState]
	
    # 鑾峰彇鎵ц鐨勮璁″璞?
    set lDesign [GetActivePMDesign]
    
    # 检查是否有活动设计
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "未找到当前打开的设计！"
        return
    }
    # 注释编码已统一为 GBK，原注释内容已清理。
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    
    # 获取第一个原理图视图
    set lView [$lSchematicIter NextView $lStatus]
    set SchNum 0
    set lNullObj NULL
	
    while { $lView != $lNullObj } {
        incr SchNum
		
        # 从DboView转换为DboSchematic
        set lSchematic [DboViewToDboSchematic $lView]
        # 新建页面迭代器，用于遍历
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        # 鑾峰彇绗竴椤?
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
                # 鑾峰彇鍣ㄤ欢浣嶅彿锛圧eference Designator锛?
                set lRefDesNameCStr [DboTclHelper_sMakeCString "Reference"]
                set lRefDesValueCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lRefDesNameCStr $lRefDesValueCStr
                set lRefDesString [DboTclHelper_sGetConstCharPtr $lRefDesValueCStr]
                
                ::capMenuUtil::logDebug "  Checking component #$instCount : RefDes = $lRefDesString"

                
                    incr uInstCount
                    # 将器件转换为PlacedInst对象
                    set lPlacedInst [DboPartInstToDboPlacedInst $lInst]
                    if { $lPlacedInst != $lNullObj } {
                        # 注释编码已统一为 GBK，原注释内容已清理。
                        set lDisplayPropsIter [$lPlacedInst NewDisplayPropsIter $lStatus]
                        set propCount 0
                        set valueFound 0
                        set lDProp [$lDisplayPropsIter NextProp $lStatus]
                        
                        while { $lDProp != $lNullObj } {
                            incr propCount
                            # 注释编码已统一为 GBK，原注释内容已清理。
                            set lNameCStr [DboTclHelper_sMakeCString]
                            $lDProp GetName $lNameCStr
                            set lNameString [DboTclHelper_sGetConstCharPtr $lNameCStr]
                            
                            # 注释编码已统一为 GBK，原注释内容已清理。
                            if {[string equal -nocase $lNameString "Value"]} {
                                catch {
                                    $lDProp SetDisplayType 0
                                    ::capMenuUtil::logDebug "    Success: Value visibility for $lRefDesString set to 0 (invisible)."
                                } errMsg
                                if {$errMsg ne ""} {
                                    ::capMenuUtil::logDebug "    Warning: Failed to set Value visibility for $lRefDesString - $errMsg"
                                }
                                set valueFound 1 ;# 标记为已找到
                            }
                            
                            # 释放CString内存
                            DboTclHelper_sDeleteCString $lNameCStr
                            
                            # 注释编码已统一为 GBK，原注释内容已清理。
                            set lDProp [$lDisplayPropsIter NextProp $lStatus]
                        }
                        
                        if {!$valueFound} {
                           puts "    Warning: 'Value' property not found for component $lRefDesString."
                        }
                        
                        # 释放显示属性迭代器
                        delete_DboDisplayPropsIter $lDisplayPropsIter
                    }
                
                
                # 释放CString内存
                DboTclHelper_sDeleteCString $lRefDesNameCStr
                DboTclHelper_sDeleteCString $lRefDesValueCStr
                
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lInst [$lPartInstsIter NextPartInst $lStatus] 
            }
            
            # 注释编码已统一为 GBK，原注释内容已清理。
            delete_DboPagePartInstsIter $lPartInstsIter
            
            # 注释编码已统一为 GBK，原注释内容已清理。
            set lPage [$lPagesIter NextPage $lStatus]
        }
        
        # 閲婃斁椤甸潰杩唬鍣?
        delete_DboSchematicPagesIter $lPagesIter
        
        # 获取下一个原理图视图
        set lView [$lSchematicIter NextView $lStatus]
    }
    
    # 释放原理图视图迭代器
    delete_DboLibViewsIter $lSchematicIter
    
    puts "\nOperation completed."
}


proc ::capMenuUtil::DeleteTextTitleblocks { pLib } {
    # 已生成的随机名称集合，确保唯一性
    set lStatus [DboState]
	
    # 鑾峰彇鎵ц鐨勮璁″璞?
    set lDesign [GetActivePMDesign]
    
    # 检查是否有活动设计
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        tk_messageBox -icon error -message "未找到当前打开的设计！"
        return
    }
    # 注释编码已统一为 GBK，原注释内容已清理。
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    
    # 获取第一个原理图视图
    set lView [$lSchematicIter NextView $lStatus]
    set SchNum 0
    set lNullObj NULL
	
    
	
    while { $lView != $lNullObj } {
        incr SchNum
		
        # 从DboView转换为DboSchematic
        set lSchematic [DboViewToDboSchematic $lView]
        # 新建页面迭代器，用于遍历
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        # 鑾峰彇绗竴椤?
        set lPage [$lPagesIter NextPage $lStatus]
        set pageCount 0
        
        while { $lPage != $lNullObj } {
            incr pageCount
            puts "\nHandling page #$pageCount..."
            ##################开始删除Titleblocks#########################
			set lTitleBlocksIter [$lPage NewTitleBlocksIter $lStatus]
			set lTitle [$lTitleBlocksIter NextTitleBlock $lStatus]
			while {$lTitle != $lNullObj} {
			   $lPage DeleteTitleBlock $lTitle
			   set lTitle [$lTitleBlocksIter NextTitleBlock $lStatus]
			}
			delete_DboPageTitleBlocksIter $lTitleBlocksIter
			puts "\n Page $pageCount TitleBlocks has been deleted"
			##################结束删除Titleblocks#########################
			
			##################开始删除Text#########################
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
			
			##################结束删除Text#########################
			
			
			
			puts "\n page #$pageCount complete!"
            # 注释编码已统一为 GBK，原注释内容已清理。
            set lPage [$lPagesIter NextPage $lStatus]
        }
        
        # 閲婃斁椤甸潰杩唬鍣?
        delete_DboSchematicPagesIter $lPagesIter
        
        # 获取下一个原理图视图
        set lView [$lSchematicIter NextView $lStatus]
    }
    
    # 释放原理图视图迭代器
    delete_DboLibViewsIter $lSchematicIter
    
}


# ////////////////////////////////////////////////////////////////////////////////
# 注释编码已统一为 GBK，原注释内容已清理。
# ////////////////////////////////////////////////////////////////////////////////
proc ::capMenuUtil::GrayedPartToNC { pLib } {
    # 已生成的随机名称集合，确保唯一性
    set lStatus [DboState]
    
    # 鑾峰彇鎵ц鐨勮璁″璞?
    set lDesign [GetActivePMDesign]
    
    # 检查是否有活动设计
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        puts "Error: 未找到当前打开的设计！"
        return
    }
    
    # 注释编码已统一为 GBK，原注释内容已清理。
    if {[info exists ::IterDefs_SCHEMATICS]} {
        set lSchematicIter [$lDesign NewViewsIter $lStatus $::IterDefs_SCHEMATICS]
    } else {
        set lSchematicIter [$lDesign NewViewsIter $lStatus]
    }
    
    # 获取第一个原理图视图
    set lView [$lSchematicIter NextView $lStatus]
    set SchNum 0
    set lNullObj NULL
    set processedCount 0  ;# 缁熻澶勭悊鐨勫櫒浠舵暟閲?
    
    while { $lView != $lNullObj } {
        incr SchNum
        
        # 从DboView转换为DboSchematic
        set lSchematic [DboViewToDboSchematic $lView]
        
        # 新建页面迭代器，用于遍历
        set lPagesIter [$lSchematic NewPagesIter $lStatus]
        
        # 鑾峰彇绗竴椤?
        set lPage [$lPagesIter NextPage $lStatus]
        set PageNum 0
        
        while { $lPage != $lNullObj } {
            incr PageNum
            
            puts "\n处理中 Schematic $SchNum, Page $PageNum"
            
            # 注释编码已统一为 GBK，原注释内容已清理。
            
            # 注释编码已统一为 GBK，原注释内容已清理。
            set lPartInstsIter [$lPage NewPartInstsIter $lStatus]
            set lInst [$lPartInstsIter NextPartInst $lStatus]
            
            while { $lInst != $lNullObj } {
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lPropNameCStr [DboTclHelper_sMakeCString "Value"]
                set lPropValueCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lPropNameCStr $lPropValueCStr
                set lPropValueString [DboTclHelper_sGetConstCharPtr $lPropValueCStr]
                
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lPropPNNameCStr [DboTclHelper_sMakeCString "Part Number"]
                set lPropPNCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lPropPNNameCStr $lPropPNCStr
                set lPropPNString [DboTclHelper_sGetConstCharPtr $lPropPNCStr]
                
                # 鑾峰彇鍣ㄤ欢浣嶅彿锛圧eference Designator锛?
                set lRefDesNameCStr [DboTclHelper_sMakeCString "Reference"]
                set lRefDesValueCStr [DboTclHelper_sMakeCString]
                $lInst GetEffectivePropStringValue $lRefDesNameCStr $lRefDesValueCStr
                set lRefDesString [DboTclHelper_sGetConstCharPtr $lRefDesValueCStr]
                
                # 判断是否含有NC字样（不区分大小写）
                set hasNC 0
                if { [regexp -nocase {NC} $lPropValueString] || 
                     [regexp -nocase {NC} $lPropPNString] } {
                    set hasNC 1
                }
                
                # 如果含有NC字样，则进行处理
                if { $hasNC } {
                    incr processedCount
                    
                    # 注释编码已统一为 GBK，原注释内容已清理。
                    set lNewValueCStr [DboTclHelper_sMakeCString "NC"]
                    $lInst SetEffectivePropStringValue $lPropNameCStr $lNewValueCStr
                    
                    # 2. 设置元件颜色为灰色（可选，保持与NC Part Grayed一致）
                    set lColorPropNameCStr [DboTclHelper_sMakeCString "Color"]
                    set lColorPropValueCStr [DboTclHelper_sMakeCString "RGB(192,192,192)"]
                    $lInst SetEffectivePropStringValue $lColorPropNameCStr $lColorPropValueCStr
                    
                    # 3. 设置属性显示为可见
                    set lPlacedInst [DboPartInstToDboPlacedInst $lInst]
                    if { $lPlacedInst != $lNullObj } {
                        # 注释编码已统一为 GBK，原注释内容已清理。
                        set lDisplayPropsIter [$lPlacedInst NewDisplayPropsIter $lStatus]
                        set lDProp [$lDisplayPropsIter NextProp $lStatus]
                        
                        while { $lDProp != $lNullObj } {
                            # 注释编码已统一为 GBK，原注释内容已清理。
                            set lNameCStr [DboTclHelper_sMakeCString]
                            $lDProp GetName $lNameCStr
                            set lNameString [DboTclHelper_sGetConstCharPtr $lNameCStr]
                            
                            # 注释编码已统一为 GBK，原注释内容已清理。
                            if { [string equal -nocase $lNameString "Value"] } {
                                $lDProp SetDisplayType 1
                                ::capMenuUtil::logDebug "  Component $lRefDesString: Value set to 'NC' and made visible"
                            }
                            
                            # 注释编码已统一为 GBK，原注释内容已清理。
                            $lDProp SetColor 45
                            
                            # 释放CString内存
                            DboTclHelper_sDeleteCString $lNameCStr
                            
                            # 注释编码已统一为 GBK，原注释内容已清理。
                            set lDProp [$lDisplayPropsIter NextProp $lStatus]
                        }
                        
                        # 释放显示属性迭代器
                        delete_DboDisplayPropsIter $lDisplayPropsIter
                    }
                }
                
                # 释放CString内存
                DboTclHelper_sDeleteCString $lPropNameCStr
                DboTclHelper_sDeleteCString $lPropValueCStr
                DboTclHelper_sDeleteCString $lPropPNNameCStr
                DboTclHelper_sDeleteCString $lPropPNCStr
                DboTclHelper_sDeleteCString $lRefDesNameCStr
                DboTclHelper_sDeleteCString $lRefDesValueCStr
                
                # 注释编码已统一为 GBK，原注释内容已清理。
                set lInst [$lPartInstsIter NextPartInst $lStatus]
            }
            
            # 注释编码已统一为 GBK，原注释内容已清理。
            delete_DboPagePartInstsIter $lPartInstsIter
            
            # 注释编码已统一为 GBK，原注释内容已清理。
            set lPage [$lPagesIter NextPage $lStatus]
        }
        
        # 閲婃斁椤甸潰杩唬鍣?
        delete_DboSchematicPagesIter $lPagesIter
        
        # 获取下一个原理图视图
        set lView [$lSchematicIter NextView $lStatus]
    }
    
    # 释放原理图视图迭代器
    delete_DboLibViewsIter $lSchematicIter
    
    puts "\nGrayedPartToNC completed! Processed $processedCount components with 'NC' value."
}


# ////////////////////////////////////////////////////////////////////////////////
# 注释编码已统一为 GBK，原注释内容已清理。
# ////////////////////////////////////////////////////////////////////////////////
namespace eval ::capRequiredSanitize {
    variable targetProperties [list "Value" "规格型号"]
    variable sanitizedValue "0"
    variable restoreDirName "_required_sanitize_restore"
    variable lastBackupFileName "cap_required_sanitize_last_backup.txt"
}

proc ::capRequiredSanitize::sanitizeFromMenu {args} {
    set confirm [tk_messageBox -icon question -message "将把所有器件的 Value 和 规格型号改为 0，并生成本地恢复文件。\n是否继续？" -type yesno]
    if {$confirm ne "yes"} { return }
    if {[catch {set result [::capRequiredSanitize::sanitizeDesign]} err]} {
        catch {tk_messageBox -icon error -message "按要求脱敏失败：\n$err"}
        puts "\[capRequiredSanitize\] ERROR: $err"
        return
    }
    catch {tk_messageBox -icon info -message "按要求脱敏完成。\n处理数量：$result"}
}

proc ::capRequiredSanitize::restoreFromMenu {args} {
    set confirm [tk_messageBox -icon question -message "将从最近一次本地恢复文件还原 Value 和 规格型号。\n是否继续？" -type yesno]
    if {$confirm ne "yes"} { return }
    if {[catch {set result [::capRequiredSanitize::restoreDesign]} err]} {
        catch {tk_messageBox -icon error -message "Restore Required Sanitization失败：\n$err"}
        puts "\[capRequiredSanitize\] ERROR: $err"
        return
    }
    catch {tk_messageBox -icon info -message "Restore Required Sanitization完成。\n恢复数量：$result"}
}

proc ::capRequiredSanitize::sanitizeDesign {} {
    variable targetProperties
    variable sanitizedValue

    set lStatus [DboState]
    set lDesign [GetActivePMDesign]
    if {$lDesign eq "NULL" || $lDesign eq ""} {
        error "未找到当前打开的设计！"
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
        error "未找到最近一次恢复文件。"
    }

    set records [::capRequiredSanitize::readBackupRecords $backupPath]
    if {[llength $records] == 0} {
        error "恢复文件为空或格式不正确：$backupPath"
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
        error "未找到当前打开的设计！"
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
