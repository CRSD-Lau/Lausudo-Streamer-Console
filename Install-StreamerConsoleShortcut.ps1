[CmdletBinding()]
param(
    [string]$StartMenuShortcut = (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Streamer Console.lnk'),
    [string]$PinnedShortcut = (Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Streamer Console.lnk')
)

$ErrorActionPreference = 'Stop'
$ProjectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonWindowed = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\pythonw.exe'
$Launcher = Join-Path $ProjectDirectory 'run_console.pyw'
$Icon = Join-Path $ProjectDirectory 'streamer_console\assets\lausudo-frostgate.ico'
$AppUserModelId = 'NeilMitchell.StreamerConsole'

foreach ($requiredPath in @($PythonWindowed, $Launcher, $Icon)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required Streamer Console file was not found: $requiredPath"
    }
}

if (-not ('StreamerConsole.ShortcutIdentity' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

namespace StreamerConsole
{
    [StructLayout(LayoutKind.Sequential)]
    internal struct PropertyKey
    {
        internal Guid FormatId;
        internal uint PropertyId;

        internal PropertyKey(Guid formatId, uint propertyId)
        {
            FormatId = formatId;
            PropertyId = propertyId;
        }
    }

    [StructLayout(LayoutKind.Explicit)]
    internal struct PropVariant
    {
        [FieldOffset(0)] internal ushort VariantType;
        [FieldOffset(8)] internal IntPtr PointerValue;
    }

    [ComImport]
    [Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IPropertyStore
    {
        [PreserveSig] int GetCount(out uint propertyCount);
        [PreserveSig] int GetAt(uint propertyIndex, out PropertyKey key);
        [PreserveSig] int GetValue(ref PropertyKey key, out PropVariant value);
        [PreserveSig] int SetValue(ref PropertyKey key, ref PropVariant value);
        [PreserveSig] int Commit();
    }

    [ComImport]
    [Guid("00021401-0000-0000-C000-000000000046")]
    [ClassInterface(ClassInterfaceType.None)]
    internal class ShellLink
    {
    }

    public static class ShortcutIdentity
    {
        private const ushort UnicodeString = 31;
        private static readonly PropertyKey AppUserModelIdKey = new PropertyKey(
            new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), 5);

        [DllImport("ole32.dll", PreserveSig = true)]
        private static extern int PropVariantClear(ref PropVariant value);

        public static void Set(string path, string appUserModelId)
        {
            object link = new ShellLink();
            IPersistFile persist = (IPersistFile)link;
            persist.Load(path, 2);
            IPropertyStore store = (IPropertyStore)link;
            PropertyKey key = AppUserModelIdKey;
            PropVariant value = new PropVariant
            {
                VariantType = UnicodeString,
                PointerValue = Marshal.StringToCoTaskMemUni(appUserModelId)
            };
            try
            {
                Marshal.ThrowExceptionForHR(store.SetValue(ref key, ref value));
                Marshal.ThrowExceptionForHR(store.Commit());
                persist.Save(path, true);
            }
            finally
            {
                PropVariantClear(ref value);
                Marshal.FinalReleaseComObject(link);
            }
        }

    }
}
'@
}

function Set-StreamerConsoleShortcut {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $parentDirectory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parentDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $parentDirectory -Force | Out-Null
    }

    $shell = New-Object -ComObject WScript.Shell
    try {
        $shortcut = $shell.CreateShortcut($Path)
        $shortcut.TargetPath = $PythonWindowed
        $shortcut.Arguments = '"' + $Launcher + '"'
        $shortcut.WorkingDirectory = $ProjectDirectory
        $shortcut.IconLocation = $Icon + ',0'
        $shortcut.Description = 'Lausudo Streamer Console'
        $shortcut.Save()
    }
    finally {
        if ($null -ne $shortcut) {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut)
        }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)
    }

    [StreamerConsole.ShortcutIdentity]::Set($Path, $AppUserModelId)
    $propertyShell = New-Object -ComObject Shell.Application
    try {
        $propertyFolder = $propertyShell.Namespace($parentDirectory)
        $propertyItem = $propertyFolder.ParseName((Split-Path -Leaf $Path))
        $actual = [string]$propertyItem.ExtendedProperty('System.AppUserModel.ID')
    }
    finally {
        if ($null -ne $propertyItem) {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($propertyItem)
        }
        if ($null -ne $propertyFolder) {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($propertyFolder)
        }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($propertyShell)
    }
    if ($actual -ne $AppUserModelId) {
        throw "Shortcut identity verification failed for $Path"
    }
    Write-Output "Verified Streamer Console shortcut identity: $Path"
}

Set-StreamerConsoleShortcut -Path $StartMenuShortcut
if (Test-Path -LiteralPath $PinnedShortcut -PathType Leaf) {
    Set-StreamerConsoleShortcut -Path $PinnedShortcut
}
else {
    Write-Output 'No existing pinned shortcut was changed. Pin Streamer Console from the Start menu if desired.'
}
