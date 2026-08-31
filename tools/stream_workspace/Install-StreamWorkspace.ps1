[CmdletBinding()]
param(
    [switch]$RequireTikTokBroker
)

$ErrorActionPreference = 'Stop'
$ProjectDirectory = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$ScriptPath = Join-Path $ProjectDirectory 'tools\stream_workspace\StreamWorkspace.ahk'
$BrokerSourcePath = Join-Path $ProjectDirectory 'tools\stream_workspace\TikTokPlacementBroker.ps1'
$AutoHotkey = 'C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe'
$StartupDirectory = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $StartupDirectory 'Lausudo Stream Workspace.lnk'
$BrokerDirectory = Join-Path $env:ProgramFiles 'Lausudo Streamer Console'
$BrokerInstalledPath = Join-Path $BrokerDirectory 'TikTokPlacementBroker.ps1'
$BrokerTaskName = 'Lausudo Stream Workspace TikTok Placement'
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
$IsAdministrator = $Principal.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if ($RequireTikTokBroker -and -not $IsAdministrator) {
    throw 'TikTok placement broker installation requires an elevated PowerShell session.'
}

if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
    throw "F3 listener was not found at $ScriptPath"
}
if (-not (Test-Path -LiteralPath $AutoHotkey -PathType Leaf)) {
    throw "AutoHotkey v2 was not found at $AutoHotkey"
}
if (-not (Test-Path -LiteralPath $BrokerSourcePath -PathType Leaf)) {
    throw "TikTok placement broker was not found at $BrokerSourcePath"
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

if ($null -eq $AlreadyRunning -and -not $IsAdministrator) {
    Start-Process -FilePath $AutoHotkey -ArgumentList @($ScriptPath) -WorkingDirectory (Split-Path -Parent $ScriptPath) -WindowStyle Hidden
}

Write-Output "Installed the F3 workspace listener shortcut for the current Windows user."
if ($IsAdministrator -and $null -eq $AlreadyRunning) {
    Write-Warning 'The elevated install does not start the listener elevated. Run this installer once from a normal PowerShell session, or sign in again, to start F3 normally.'
}

if ($IsAdministrator) {
    New-Item -ItemType Directory -Path $BrokerDirectory -Force | Out-Null
    Copy-Item -LiteralPath $BrokerSourcePath -Destination $BrokerInstalledPath -Force
    $SourceHash = (Get-FileHash -LiteralPath $BrokerSourcePath -Algorithm SHA256).Hash
    $InstalledHash = (Get-FileHash -LiteralPath $BrokerInstalledPath -Algorithm SHA256).Hash
    if ($SourceHash -ne $InstalledHash) {
        throw 'TikTok placement broker copy verification failed.'
    }

    # Composite values such as FullControl contain read and synchronize bits.
    # Using them as a bitmask would falsely reject ordinary ReadAndExecute ACEs.
    $MutationRights = [Security.AccessControl.FileSystemRights]::WriteData -bor
        [Security.AccessControl.FileSystemRights]::AppendData -bor
        [Security.AccessControl.FileSystemRights]::WriteExtendedAttributes -bor
        [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
        [Security.AccessControl.FileSystemRights]::WriteAttributes -bor
        [Security.AccessControl.FileSystemRights]::Delete -bor
        [Security.AccessControl.FileSystemRights]::ChangePermissions -bor
        [Security.AccessControl.FileSystemRights]::TakeOwnership
    $TrustedIdentities = @(
        'NT AUTHORITY\SYSTEM',
        'BUILTIN\Administrators',
        'NT SERVICE\TrustedInstaller'
    )
    $UnsafeRules = @($BrokerDirectory, $BrokerInstalledPath) | ForEach-Object {
        (Get-Acl -LiteralPath $_).Access
    } | Where-Object {
        $_.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and
        ($_.FileSystemRights -band $MutationRights) -ne 0 -and
        $_.IdentityReference.Value -notin $TrustedIdentities
    }
    if (@($UnsafeRules).Count -ne 0) {
        throw 'TikTok placement broker has an unsafe writable ACL; task was not registered.'
    }

    $PowerShellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $ActionArguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "' +
        $BrokerInstalledPath + '"'
    $TaskAction = New-ScheduledTaskAction `
        -Execute $PowerShellPath `
        -Argument $ActionArguments `
        -WorkingDirectory $BrokerDirectory
    $TaskPrincipal = New-ScheduledTaskPrincipal `
        -UserId $Identity.Name `
        -LogonType Interactive `
        -RunLevel Highest
    $TaskSettings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 1) `
        -MultipleInstances IgnoreNew
    Register-ScheduledTask `
        -TaskName $BrokerTaskName `
        -Action $TaskAction `
        -Principal $TaskPrincipal `
        -Settings $TaskSettings `
        -Description 'Moves only TikTok LIVE Studio into the approved production-monitor zone when F3 requests it.' `
        -Force | Out-Null
    Write-Output "Installed the protected elevated TikTok placement broker."
}
else {
    Write-Warning (
        'The F3 listener is installed, but TikTok placement still needs one elevated install. ' +
        'Rerun this script from an administrator PowerShell session with -RequireTikTokBroker.'
    )
}
