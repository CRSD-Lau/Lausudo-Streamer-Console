[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectDirectory = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$ScriptPath = Join-Path $ProjectDirectory 'tools\stream_workspace\StreamWorkspace.ahk'
$ShortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'Lausudo Stream Workspace.lnk'

$OwnedProcesses = Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
    $_.Name -like 'AutoHotkey*.exe' -and
    $_.CommandLine -and
    $_.CommandLine.IndexOf($ScriptPath, [StringComparison]::OrdinalIgnoreCase) -ge 0
}
foreach ($OwnedProcess in $OwnedProcesses) {
    Stop-Process -Id $OwnedProcess.ProcessId -ErrorAction Stop
}

if (Test-Path -LiteralPath $ShortcutPath -PathType Leaf) {
    Remove-Item -LiteralPath $ShortcutPath -Force
}

Write-Output "Removed the F3 workspace listener. F1/F2 and application settings were not changed."
