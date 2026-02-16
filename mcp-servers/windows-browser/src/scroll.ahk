; scroll.ahk - AutoHotkey v2 scroll helper for Windows Browser MCP
; Usage: AutoHotkey64.exe scroll.ahk <abs_x> <abs_y> <direction> [clicks]
; Direction: up or down
; Clicks: number of scroll steps (default 3)
;
; Coordinates are absolute SCREEN coordinates (virtual desktop space).
; Supports negative X values for left-side monitors.

#Requires AutoHotkey v2.0
#SingleInstance Force

CoordMode "Mouse", "Screen"

if A_Args.Length < 3 {
    FileAppend("error=usage: scroll.ahk <x> <y> <up|down> [clicks]`n", "*")
    ExitApp 1
}

x := Integer(A_Args[1])
y := Integer(A_Args[2])
direction := A_Args[3]
clicks := A_Args.Length >= 4 ? Integer(A_Args[4]) : 3

; Move mouse to target position
MouseMove x, y
Sleep 100

; Send scroll events
Loop clicks {
    if (direction = "up") {
        Send "{WheelUp}"
    } else {
        Send "{WheelDown}"
    }
    Sleep 50
}

; Small delay then get diagnostics
Sleep 50
MouseGetPos &actualX, &actualY

winTitle := ""
try {
    winTitle := WinGetTitle("A")
}

FileAppend("target=" x "," y "|actual=" actualX "," actualY "|direction=" direction "|clicks=" clicks "|activewin=" winTitle "`n", "*")
ExitApp 0
