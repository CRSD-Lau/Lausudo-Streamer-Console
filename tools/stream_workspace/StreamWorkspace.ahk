#Requires AutoHotkey v2.0
#SingleInstance Force
Persistent

controller := A_ScriptDir "\..\..\streamer_console\stream_workspace.py"
pythonWindowed := EnvGet("LOCALAPPDATA") "\Programs\Python\Python313\pythonw.exe"
stateDir := EnvGet("LOCALAPPDATA") "\NeilMitchell\StreamerConsole"
listenerLog := stateDir "\stream-workspace-hotkey.log"
DirCreate stateDir

LogWorkspaceHotkey(message) {
    global listenerLog
    try FileAppend FormatTime(, "yyyy-MM-ddTHH:mm:ss") " " message "`n", listenerLog, "UTF-8"
}
LogWorkspaceHotkey "F3 workspace listener started."

F3::{
    global controller, pythonWindowed
    try {
        LogWorkspaceHotkey "F3 received."
        previousWindow := WinExist("A")
        if !FileExist(pythonWindowed) {
            throw Error("Python 3.13 windowed runtime was not found.")
        }
        if !FileExist(controller) {
            throw Error("Workspace controller was not found.")
        }

        commandLine := '"' pythonWindowed '" "' controller '" apply'
        exitCode := RunWait(commandLine, A_ScriptDir, "Hide")
        LogWorkspaceHotkey "F3 controller exit code: " exitCode "."

        ; The hotkey process owns the user gesture, so it can reliably return
        ; focus after GUI launches. A background Python child cannot.
        if previousWindow && WinExist("ahk_id " previousWindow) {
            WinActivate "ahk_id " previousWindow
            if !WinWaitActive("ahk_id " previousWindow, , 2) {
                LogWorkspaceHotkey "Previous foreground window did not reactivate."
            }
        }

        if exitCode != 0 {
            TrayTip "Stream Workspace", "F3 made no unsafe fallback changes. Check the local workspace log.", 5
            SoundBeep 650, 180
        }
    } catch Error as err {
        LogWorkspaceHotkey "F3 launch error: " err.Message
        TrayTip "Stream Workspace", "F3 could not start its local controller; no stream settings were changed.", 5
        SoundBeep 650, 180
    }
}
