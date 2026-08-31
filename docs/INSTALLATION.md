# Installation

## 1. Prerequisites

- Windows 10 or 11
- Python 3.11 or 3.13 with `pip`
- OBS Studio with OBS WebSocket enabled
- Aitum Stream Suite when the vertical output is used
- Official Social Stream Ninja browser extension for TikTok LIVE collection
- Spotify desktop app for the optional media controls

The BRB/privacy and Discord buttons require AutoHotkey v2 and the separate
`PrivacyToggle.ahk` helper used by the Lausudo stream setup. Streamer Console
automatically starts the helper when the app opens and stops the helper it owns
when the app closes. An exact helper instance that was already running remains
externally owned and is left running. Chat and read-only status remain useful
when AutoHotkey or the helper is absent.

The default helper locations are:

```text
C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe
D:\Projects\OBS-Tools\PrivacyToggle\PrivacyToggle.ahk
```

Portable installations can set `STREAMER_CONSOLE_AHK_EXE` and
`STREAMER_CONSOLE_AHK_SCRIPT` before launching the console.

## 2. Clone and install

```powershell
git clone https://github.com/CRSD-Lau/Lausudo-Streamer-Console.git
Set-Location -LiteralPath '.\Lausudo-Streamer-Console'
py -3.13 -m pip install -r .\requirements.txt
```

Python 3.11 is also supported:

```powershell
py -3.11 -m pip install -r .\requirements.txt
```

## 3. Configure Social Stream Ninja

Set **Send all to POST server** to:

```text
http://127.0.0.1:17840/ingest/socialstream
```

Keep the Social Stream background service page and the TikTok LIVE page open
while collecting. See [Social Stream setup](SOCIAL_STREAM_SETUP.md).

## 4. Start the console

```powershell
.\Start-StreamerConsole.ps1
```

The launcher uses the Python 3.13 `pythonw.exe` installation under the current
user profile and opens no console window. If only Python 3.11 is installed,
launch directly:

```powershell
pyw -3.11 .\run_console.pyw
```

## 5. Install the Windows shortcut

```powershell
.\Install-StreamerConsoleShortcut.ps1
```

The script creates or repairs the current user's Start-menu shortcut and updates
an existing pinned taskbar shortcut. It assigns the same application identity
used by the running window, so Windows groups the window over the pin. It does
not enable startup.

If Windows retains an old cached taskbar entry, unpin it once and pin **Streamer
Console** again from the Start menu.

## 6. Connect Twitch (optional)

1. Create a public application in the Twitch developer console.
2. Copy the Client ID; do not create or provide a client secret.
3. Open **INFO** in Streamer Console and paste the Client ID.
4. Choose **CONNECT TWITCH** and approve the device code in the browser.

The Device Code flow does not use an OAuth redirect URL. Twitch authorization is
needed for native Twitch chat, EventSub alerts, viewers, stream markers, and
Stream Info updates. Once **CONNECTED · SAVED** appears, Windows Credential
Manager retains the connection and Twitch refreshes it automatically; approval
is normally needed only once. TikTok/Social Stream collection remains independent.

## Global F3 stream workspace

Install the independent F3 listener for the current Windows user:

```powershell
.\tools\stream_workspace\Install-StreamWorkspace.ps1
```

Then open **PowerShell as Administrator**, return to the repository directory,
and install the fixed TikTok placement broker:

```powershell
.\tools\stream_workspace\Install-StreamWorkspace.ps1 -RequireTikTokBroker
```

This one-time elevation copies only `TikTokPlacementBroker.ps1` into
`C:\Program Files\Lausudo Streamer Console`, verifies its SHA-256 hash and ACL,
and registers an on-demand highest-run-level task. The elevated pass deliberately
does not start the F3 listener elevated. Pressing F3 later does not prompt for
UAC and does not elevate the normal Python controller.

The installer creates **Lausudo Stream Workspace.lnk** in the current user's
Startup folder and starts the listener immediately. The listener remains
available when Streamer Console is closed and owns only F3; the console-managed
F1/F2 privacy helper retains its existing lifecycle.

F3 is an idempotent **Prepare Stream Workspace** command, not a toggle. Its
defaults are calculated from the current Windows work areas:

| Display | Placement |
| --- | --- |
| Top 2560x1440 production display | OBS left 1360 px; TikTok LIVE Studio right 1200 px |
| Left 1080x1920 portrait display | Streamer Console upper 38%; Discord lower 62% |
| Bottom 2560x1440 primary gaming display | Left untouched; the previously focused window is restored |

F3 opens the installed Social Stream Ninja background service page using the
configured Chrome **Default** profile and exact official extension ID, then
minimizes that app window. Keep the Twitch/TikTok source pages configured as
described in [Social Stream Ninja setup](SOCIAL_STREAM_SETUP.md). Spotify opens
through the installed Microsoft Store package and is minimized. Voicemeeter is
never launched or configured; if its window is already open, the window is
placed on the production display and minimized.

Safety behavior:

- Existing application windows are reused; F3 never closes, restarts, or
  deliberately duplicates an application.
- TikTok LIVE Studio requests elevated Windows integrity and a minimum
  1200-pixel width. The protected broker places only that existing window; it
  cannot launch software or accept arbitrary commands. Without the broker, F3
  exits safely and logs the missing scheduled-task result.
- Discord may restore its own saved geometry after startup. F3 waits for that
  restoration and reapplies the portrait-bottom placement until verified.
- All three expected displays must be connected. If the topology does not
  match, the operation aborts before launching or moving anything instead of
  spilling production windows onto the gaming display.
- F3 controls only windows. It has no OBS WebSocket integration and cannot
  change stream/recording state, scenes, Virtual Camera, microphone or monitor
  state, Discord mute, Spotify routing, or Voicemeeter routing.
- A named mutex collapses overlapping F3 presses into one operation. App
  readiness uses bounded window polling rather than fixed blind delays.
- Failures are recorded in bounded local logs under
  `%LOCALAPPDATA%\NeilMitchell\StreamerConsole`; window titles and credentials
  are not logged.

Preview the exact sanitized plan without launching or moving anything:

```powershell
py -3.13 .\streamer_console\stream_workspace.py plan --json
```

Remove the F3 listener, Startup shortcut, and protected TikTok broker from an
**Administrator PowerShell** with:

```powershell
.\tools\stream_workspace\Uninstall-StreamWorkspace.ps1
```

This rollback does not touch F1/F2, Streamer Console, OBS, TikTok LIVE Studio,
Discord, Spotify, Social Stream Ninja, Voicemeeter, or their settings.

## 7. Validate without production services

```powershell
py -3.13 -m streamer_console.app --simulate --run-seconds 15
```

Simulation mode uses local messages and status, disables controls, and does not
connect to OBS, Twitch, TikTok, Social Stream Ninja, or Spotify.

## Updating

```powershell
git pull --ff-only
py -3.13 -m pip install -r .\requirements.txt
.\Install-StreamerConsoleShortcut.ps1
```

Restart Streamer Console after updating. Do not restart OBS, Virtual Camera, a
stream, or a recording solely to update this application.
