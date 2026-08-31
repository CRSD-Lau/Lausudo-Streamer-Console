[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectDirectory = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$ScriptPath = Join-Path $ProjectDirectory 'tools\stream_workspace\StreamWorkspace.ahk'
$AutoHotkey = 'C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe'
$StartupDirectory = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $StartupDirectory 'Lausudo Stream Workspace.lnk'

if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
    throw "F3 listener was not found at $ScriptPath"
}
if (-not (Test-Path -LiteralPath $AutoHotkey -PathType Leaf)) {
    throw "AutoHotkey v2 was not found at $AutoHotkey"
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $AutoHotkey
$Shortcut.Arguments = '"' + $ScriptPath + '"'
$Shortcut.WorkingDirectory = Split-Path -Parent $ScriptPath
$Shortcut.Description = 'Global F3 launcher for the Lausudo stream workspace'
$Shortcut.IconLocation = (Join-Path $ProjectDirectory 'streamer_console\assets\lausudo-frostgate.ico') + ',0'
$Shortcut.Save()

$AlreadyRunning = Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
    $_.Name -like 'AutoHotkey*.exe' -and
    $_.CommandLine -and
    $_.CommandLine.IndexOf($ScriptPath, [StringComparison]::OrdinalIgnoreCase) -ge 0
} | Select-Object -First 1

if ($null -eq $AlreadyRunning) {
    Start-Process -FilePath $AutoHotkey -ArgumentList @($ScriptPath) -WorkingDirectory (Split-Path -Parent $ScriptPath) -WindowStyle Hidden
}

Write-Output "Installed the F3 workspace listener for the current Windows user."
