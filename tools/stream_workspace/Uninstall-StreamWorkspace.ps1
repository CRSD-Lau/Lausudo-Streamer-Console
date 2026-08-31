[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectDirectory = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$ScriptPath = Join-Path $ProjectDirectory 'tools\stream_workspace\StreamWorkspace.ahk'
$ShortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'Lausudo Stream Workspace.lnk'
$BrokerTaskName = 'Lausudo Stream Workspace TikTok Placement'
$BrokerDirectory = Join-Path $env:ProgramFiles 'Lausudo Streamer Console'
$BrokerInstalledPath = Join-Path $BrokerDirectory 'TikTokPlacementBroker.ps1'
$BrokerTask = Get-ScheduledTask -TaskName $BrokerTaskName -ErrorAction SilentlyContinue
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
$IsAdministrator = $Principal.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (
    ($null -ne $BrokerTask -or (Test-Path -LiteralPath $BrokerInstalledPath)) -and
    -not $IsAdministrator
) {
    throw 'Run this uninstaller from an elevated PowerShell session to remove the protected TikTok placement broker safely.'
}

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

if ($null -ne $BrokerTask) {
    Unregister-ScheduledTask -TaskName $BrokerTaskName -Confirm:$false
}
if (Test-Path -LiteralPath $BrokerInstalledPath -PathType Leaf) {
    Remove-Item -LiteralPath $BrokerInstalledPath -Force
}
if (
    (Test-Path -LiteralPath $BrokerDirectory -PathType Container) -and
    -not (Get-ChildItem -LiteralPath $BrokerDirectory -Force | Select-Object -First 1)
) {
    Remove-Item -LiteralPath $BrokerDirectory -Force
}

Write-Output "Removed the F3 workspace listener and its TikTok placement broker. F1/F2 and application settings were not changed."
