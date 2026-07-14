# Shared lifecycle gate for platform-managed Cadence commands.

namespace eval ::IACPluginRuntime {
    variable ACTIVE
    variable COMMANDS
    if {![array exists ACTIVE]} { array set ACTIVE {} }
    if {![array exists COMMANDS]} { array set COMMANDS {} }
}

proc ::IACPluginRuntime::register {id command} {
    variable ACTIVE
    variable COMMANDS
    set COMMANDS($id) $command
    set ACTIVE($id) 0
    return 1
}

proc ::IACPluginRuntime::activate {id} {
    variable ACTIVE
    variable COMMANDS
    if {![info exists COMMANDS($id)]} {
        return -code error "Plugin is not registered: $id"
    }
    set ACTIVE($id) 1
    return 1
}

proc ::IACPluginRuntime::deactivate {id} {
    variable ACTIVE
    set ACTIVE($id) 0
    return 1
}

proc ::IACPluginRuntime::isActive {id} {
    variable ACTIVE
    return [expr {[info exists ACTIVE($id)] && $ACTIVE($id)}]
}

proc ::IACPluginRuntime::invoke {id args} {
    variable COMMANDS
    if {![::IACPluginRuntime::isActive $id]} {
        if {[info commands ::IAC::log] ne ""} { ::IAC::log "IAC: plugin is disabled: $id" }
        return 0
    }
    if {![info exists COMMANDS($id)]} {
        return -code error "Plugin command is not registered: $id"
    }
    set command $COMMANDS($id)
    if {[llength [info commands [lindex $command 0]]] == 0} {
        return -code error "Plugin command is unavailable: $command"
    }
    return [uplevel #0 [concat $command $args]]
}
