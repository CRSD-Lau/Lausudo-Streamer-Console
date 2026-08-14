# Lausudo Streamer Console

Streamer Console is a lightweight native Qt dashboard for the left 1080×1920
portrait monitor. It presents Twitch and TikTok LIVE messages in one
receipt-ordered feed, displays read-only OBS/Aitum state, and exposes the same
F1 BRB/privacy and F2 Discord-mute controls already used by the keyboard.

It does not replace or reconfigure OBS, Aitum, TikTok LIVE Studio,
Voicemeeter, Discord, or the existing privacy controller.

## Architecture

```text
Twitch chat ─┐
             ├─ Social Stream Ninja ─ POST 127.0.0.1:17840 ─ unified Qt feed
TikTok chat ─┘

OBS WebSocket + Aitum vendor API ─ read-only status ────────────────┘

BRB button ─ F1 ─ existing AutoHotkey/privacy controller
Discord button ─ F2 ─ existing AutoHotkey/Discord native Toggle Mute
```

Messages receive a local sequence when they arrive, so the feed stays
chronological across platforms. Retention is bounded at 750 messages by
default. Twitch and TikTok collection are independent; one source failing
does not stop the other or OBS status. Since the local POST transport has no
persistent connection, a platform shows **RECEIVING** after recent data and
ages to **NO RECENT DATA** after 30 seconds; Social Stream Ninja/browser owns
upstream reconnection.

## Requirements

- Windows 10/11
- Python 3.13 at
  `%LOCALAPPDATA%\Programs\Python\Python313\python.exe`
- OBS Studio with its existing authenticated WebSocket enabled
- Existing AutoHotkey F1/F2 helper for stream controls
- Official Social Stream Ninja extension for live chat collection

Install dependencies once from PowerShell:

```powershell
Set-Location -LiteralPath 'C:\Projects\StreamerConsole'
py -3.13 -m pip install -r .\requirements.txt
```

## Configure combined chat

Install only the official Social Stream Ninja extension, then set **Send all
to POST server** to:

```text
http://127.0.0.1:17840/ingest/socialstream
```

Keep Twitch chat/pop-out chat open. While TikTok is live, keep
`https://www.tiktok.com/@lausudo/live` open with its LIVE chat available.
Browser authentication remains in the browser; Streamer Console stores no
cookies, OAuth tokens, passwords, or stream keys. See
[`docs/SOCIAL_STREAM_SETUP.md`](docs/SOCIAL_STREAM_SETUP.md) for the complete
collector setup and TikTok limitations.

## Launch

Double-click `Start-StreamerConsole.ps1`, or run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'C:\Projects\StreamerConsole\Start-StreamerConsole.ps1'
```

The app defaults to the available portrait display. Window placement, size,
font size, spacing, filters, highlight terms, borderless mode, and always-on-
top mode are remembered locally.

For a safe, fully local visual smoke test (no OBS connection, no chat POSTs,
and F1/F2 controls disabled):

```powershell
py -3.13 -m streamer_console.app --simulate --run-seconds 15
```

## Controls

- **BRB / Privacy (F1):** sends F1 to the existing global helper. The button
  never guesses the result; its LIVE/BRB/MIXED state comes from the next actual
  OBS and Aitum status snapshot.
- **Discord Mute (F2):** sends F2 to the existing helper, which uses Discord's
  native Toggle Mute shortcut. Discord does not expose a supported local mute
  state in this setup, so the console intentionally shows state unavailable.

## Local data and logging

Runtime configuration and bounded rotating logs live under:

```text
%LOCALAPPDATA%\NeilMitchell\StreamerConsole\
```

The checked-in [`config.example.json`](config.example.json) contains no
secrets. The application reads the existing OBS WebSocket password only in
memory from OBS's own local configuration and never copies or logs it. Logs do
not contain chat bodies or credentials.

Windows startup is **not enabled**. If startup is added later, the local
`start_with_windows` setting remains the place to record that choice.

## Development and tests

```powershell
Set-Location -LiteralPath 'C:\Projects\StreamerConsole'
py -3.13 -m unittest discover -s tests -v
```

The test suite uses an off-screen Qt platform and fakes control/network
boundaries; it does not send global keys or production chat messages.

## More documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/SOCIAL_STREAM_SETUP.md`](docs/SOCIAL_STREAM_SETUP.md)
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)
- [`docs/UNINSTALL.md`](docs/UNINSTALL.md)

## Clean removal

Close the console, remove `C:\Projects\StreamerConsole`, and optionally remove
`%LOCALAPPDATA%\NeilMitchell\StreamerConsole`. This does not remove or modify
OBS scenes, Aitum, stream credentials, TikTok LIVE Studio, Voicemeeter,
Discord, recordings, or the existing F1/F2 helper.
