; sendkeys.ahk - AutoHotkey v2 keyboard helper for Windows Browser MCP
; Usage: AutoHotkey64.exe sendkeys.ahk <keys>
; Sends keystrokes using AutoHotkey's native Send command.
;
; Supports full AHK key syntax:
;   Modifiers: ^ (Ctrl), ! (Alt), + (Shift), # (Win)
;   Special keys: {Enter}, {Tab}, {Escape}, {PgDn}, {PgUp}, {Home}, {End}
;                 {Up}, {Down}, {Left}, {Right}, {F1}-{F12}
;                 {Backspace}, {Delete}, {Space}
;   Combos: ^a (Ctrl+A), ^l (Ctrl+L), ^c (Ctrl+C), !{F4} (Alt+F4)
;   Repeat: {PgDn 3} sends PgDn 3 times

#Requires AutoHotkey v2.0
#SingleInstance Force

if A_Args.Length < 1 {
    FileAppend("error=missing keys argument`n", "*")
    ExitApp 1
}

; Join all arguments (in case keys contain spaces)
keys := ""
for i, arg in A_Args {
    keys .= (i > 1 ? " " : "") . arg
}

; Get active window before sending
winBefore := ""
try {
    winBefore := WinGetTitle("A")
}

; Send the keys
Send keys

; Small delay for keys to register
Sleep 50

; Get active window after sending
winAfter := ""
try {
    winAfter := WinGetTitle("A")
}

; Output diagnostics
FileAppend("keys=" keys "|window_before=" winBefore "|window_after=" winAfter "`n", "*")
ExitApp 0
