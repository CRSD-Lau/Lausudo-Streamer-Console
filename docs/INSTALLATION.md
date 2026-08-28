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
