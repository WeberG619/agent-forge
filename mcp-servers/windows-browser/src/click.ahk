; click.ahk - AutoHotkey v2 click helper for Windows Browser MCP
; Usage: AutoHotkey64.exe click.ahk <abs_x> <abs_y> [action]
; Actions: click (default), move, rightclick, doubleclick
;
; Coordinates are absolute SCREEN coordinates (virtual desktop space).
; Supports negative X values for left-side monitors.

#Requires AutoHotkey v2.0
#SingleInstance Force

CoordMode "Mouse", "Screen"

if A_Args.Length < 2 {
    FileAppend("error=missing coordinates`n", "*")
    ExitApp 1
}

x := Integer(A_Args[1])
y := Integer(A_Args[2])
action := A_Args.Length >= 3 ? A_Args[3] : "click"

; Perform the action
switch action {
    case "click":
        Click x, y
    case "rightclick":
        Click x, y, "Right"
    case "doubleclick":
        Click x, y, 2
    case "move":
        MouseMove x, y
    default:
        Click x, y
}

; Small delay for click to register
Sleep 50

; Get actual cursor position for diagnostics
MouseGetPos &actualX, &actualY

; Get window info under cursor
winHwnd := 0
try {
    winHwnd := WinGetID("A")
}
winTitle := ""
try {
    winTitle := WinGetTitle("A")
}

; Output diagnostics to stdout
FileAppend("target=" x "," y "|actual=" actualX "," actualY "|action=" action "|activewin=" winTitle "`n", "*")
ExitApp 0
