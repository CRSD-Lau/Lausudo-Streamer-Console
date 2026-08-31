#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$StateDirectory = Join-Path $env:LOCALAPPDATA 'NeilMitchell\StreamerConsole'
$RequestPath = Join-Path $StateDirectory 'tiktok-placement-request.txt'
$ResultPath = Join-Path $StateDirectory 'tiktok-placement-result.json'

Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

public static class LausudoTikTokPlacement
{
    private const uint MONITORINFOF_PRIMARY = 1;
    private const int SW_RESTORE = 9;
    private const uint SWP_NOZORDER = 0x0004;
    private const uint SWP_NOACTIVATE = 0x0010;

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct MONITORINFOEX
    {
        public int Size;
        public RECT Monitor;
        public RECT Work;
        public uint Flags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string Device;
    }

    public sealed class MonitorSpec
    {
        public string Device;
        public RECT Bounds;
        public RECT WorkArea;
        public bool Primary;
    }

    private delegate bool MonitorEnumProc(
        IntPtr monitor, IntPtr hdc, IntPtr rect, IntPtr data
    );
    private delegate bool WindowEnumProc(IntPtr window, IntPtr data);

    [DllImport("user32.dll")]
    private static extern bool EnumDisplayMonitors(
        IntPtr hdc, IntPtr clip, MonitorEnumProc callback, IntPtr data
    );

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern bool GetMonitorInfo(
        IntPtr monitor, ref MONITORINFOEX info
    );

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(WindowEnumProc callback, IntPtr data);

    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr window);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(
        IntPtr window, StringBuilder text, int capacity
    );

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(
        IntPtr window, out uint processId
    );

    [DllImport("user32.dll")]
    private static extern bool GetWindowRect(IntPtr window, out RECT rect);

    [DllImport("user32.dll")]
    private static extern bool ShowWindowAsync(IntPtr window, int command);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetWindowPos(
        IntPtr window,
        IntPtr insertAfter,
        int x,
        int y,
        int width,
        int height,
        uint flags
    );

    public static MonitorSpec[] GetMonitors()
    {
        List<MonitorSpec> monitors = new List<MonitorSpec>();
        MonitorEnumProc callback = delegate(IntPtr handle, IntPtr hdc, IntPtr rect, IntPtr data)
        {
            MONITORINFOEX info = new MONITORINFOEX();
            info.Size = Marshal.SizeOf(typeof(MONITORINFOEX));
            if (GetMonitorInfo(handle, ref info))
            {
                monitors.Add(new MonitorSpec
                {
                    Device = info.Device,
                    Bounds = info.Monitor,
                    WorkArea = info.Work,
                    Primary = (info.Flags & MONITORINFOF_PRIMARY) != 0
                });
            }
            return true;
        };
        EnumDisplayMonitors(IntPtr.Zero, IntPtr.Zero, callback, IntPtr.Zero);
        return monitors.ToArray();
    }

    public static IntPtr FindTikTokWindow()
    {
        IntPtr selected = IntPtr.Zero;
        long selectedArea = 0;
        WindowEnumProc callback = delegate(IntPtr window, IntPtr data)
        {
            if (!IsWindowVisible(window))
                return true;

            uint processId;
            GetWindowThreadProcessId(window, out processId);
            try
            {
                Process process = Process.GetProcessById((int)processId);
                if (!String.Equals(
                    process.ProcessName,
                    "TikTok LIVE Studio",
                    StringComparison.OrdinalIgnoreCase
                ))
                    return true;
            }
            catch
            {
                return true;
            }

            StringBuilder title = new StringBuilder(512);
            GetWindowText(window, title, title.Capacity);
            if (title.ToString().IndexOf(
                "TikTok LIVE Studio", StringComparison.OrdinalIgnoreCase
            ) < 0)
                return true;

            RECT bounds;
            if (!GetWindowRect(window, out bounds))
                return true;
            long area = Math.Max(0, bounds.Right - bounds.Left)
                * (long)Math.Max(0, bounds.Bottom - bounds.Top);
            if (area > selectedArea)
            {
                selected = window;
                selectedArea = area;
            }
            return true;
        };
        EnumWindows(callback, IntPtr.Zero);
        return selected;
    }

    private static bool CloseEnough(RECT actual, RECT expected)
    {
        const int tolerance = 12;
        return Math.Abs(actual.Left - expected.Left) <= tolerance
            && Math.Abs(actual.Top - expected.Top) <= tolerance
            && Math.Abs(actual.Right - expected.Right) <= tolerance
            && Math.Abs(actual.Bottom - expected.Bottom) <= tolerance;
    }

    public static bool PlaceAndVerify(IntPtr window, RECT target)
    {
        ShowWindowAsync(window, SW_RESTORE);
        int stableSamples = 0;
        for (int attempt = 0; attempt < 20; attempt++)
        {
            bool placed = SetWindowPos(
                window,
                IntPtr.Zero,
                target.Left,
                target.Top,
                target.Right - target.Left,
                target.Bottom - target.Top,
                SWP_NOZORDER | SWP_NOACTIVATE
            );
            if (!placed)
                return false;

            Thread.Sleep(200);
            RECT actual;
            if (GetWindowRect(window, out actual) && CloseEnough(actual, target))
            {
                stableSamples++;
                if (stableSamples >= 4)
                    return true;
            }
            else
            {
                stableSamples = 0;
            }
        }
        return false;
    }
}
'@

function Write-BrokerResult {
    param(
        [Parameter(Mandatory = $true)][string]$RequestId,
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][string]$Detail
    )

    New-Item -ItemType Directory -Path $StateDirectory -Force | Out-Null
    $TemporaryPath = $ResultPath + '.tmp'
    $Json = [ordered]@{
        request_id = $RequestId
        status = $Status
        detail = $Detail
        completed_utc = [DateTime]::UtcNow.ToString('o')
    } | ConvertTo-Json -Compress
    $Utf8WithoutBom = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllText($TemporaryPath, $Json, $Utf8WithoutBom)
    Move-Item -LiteralPath $TemporaryPath -Destination $ResultPath -Force
}

$RequestId = 'validation'
try {
    if (-not $ValidateOnly) {
        if (-not (Test-Path -LiteralPath $RequestPath -PathType Leaf)) {
            throw 'Placement request is missing.'
        }
        $RequestId = (Get-Content -LiteralPath $RequestPath -Raw).Trim()
        $ParsedRequestId = [Guid]::Empty
        if (-not [Guid]::TryParse($RequestId, [ref]$ParsedRequestId)) {
            throw 'Placement request is invalid.'
        }
    }

    $Monitors = @([LausudoTikTokPlacement]::GetMonitors())
    $Gaming = $Monitors | Where-Object {
        $_.Primary -and
        ($_.Bounds.Right - $_.Bounds.Left) -eq 2560 -and
        ($_.Bounds.Bottom - $_.Bounds.Top) -eq 1440
    } | Select-Object -First 1
    if ($null -eq $Gaming) {
        throw 'Expected primary gaming display was not found.'
    }

    $Production = $Monitors | Where-Object {
        -not $_.Primary -and
        ($_.Bounds.Right - $_.Bounds.Left) -eq 2560 -and
        ($_.Bounds.Bottom - $_.Bounds.Top) -eq 1440 -and
        $_.Bounds.Top -lt $Gaming.Bounds.Top
    } | Select-Object -First 1
    $Portrait = $Monitors | Where-Object {
        -not $_.Primary -and
        ($_.Bounds.Right - $_.Bounds.Left) -eq 1080 -and
        ($_.Bounds.Bottom - $_.Bounds.Top) -eq 1920 -and
        $_.Bounds.Left -lt $Gaming.Bounds.Left
    } | Select-Object -First 1
    if ($null -eq $Production -or $null -eq $Portrait) {
        throw 'Expected production and portrait displays were not found.'
    }

    $Target = [LausudoTikTokPlacement+RECT]::new()
    $Target.Left = $Production.WorkArea.Right - 1200
    $Target.Top = $Production.WorkArea.Top
    $Target.Right = $Production.WorkArea.Right
    $Target.Bottom = $Production.WorkArea.Bottom

    $TikTokWindow = [LausudoTikTokPlacement]::FindTikTokWindow()
    if ($ValidateOnly) {
        [ordered]@{
            status = 'validated'
            target = [ordered]@{
                left = $Target.Left
                top = $Target.Top
                right = $Target.Right
                bottom = $Target.Bottom
            }
            tiktok_window_found = $TikTokWindow -ne [IntPtr]::Zero
        } | ConvertTo-Json -Compress | Write-Output
        exit 0
    }

    if ($TikTokWindow -eq [IntPtr]::Zero) {
        throw 'TikTok LIVE Studio main window was not found.'
    }

    if (-not [LausudoTikTokPlacement]::PlaceAndVerify($TikTokWindow, $Target)) {
        throw 'Windows rejected or did not retain TikTok placement.'
    }
    Write-BrokerResult -RequestId $RequestId -Status 'placed' -Detail 'verified'
    exit 0
}
catch {
    if (-not $ValidateOnly) {
        Write-BrokerResult -RequestId $RequestId -Status 'failed' -Detail $_.Exception.GetType().Name
    }
    Write-Error $_.Exception.Message
    exit 2
}
