# Privacy

Lausudo Streamer Console is a local desktop application. It contains no analytics,
advertising, remote crash reporting, or maintainer-operated backend.

## Data processed in memory

- Twitch and TikTok viewer chat and supported stream events.
- Twitch channel metadata, viewer count, and authorized account identity.
- OBS/Aitum connection, output, scene, mute, and monitoring status.
- Spotify's local Windows media-session metadata.

Chat is retained only in a bounded in-memory model and is not written to session
files or logs.

## Data stored locally

The default data directory is:

```text
%LOCALAPPDATA%\NeilMitchell\StreamerConsole\
```

It may contain:

- user interface and integration preferences;
- bounded rotating diagnostic logs without chat bodies or credentials;
- aggregate-only session totals and marker metadata;
- a Twitch token payload protected by Windows Credential Manager for the current
  user, with legacy DPAPI file support for existing installations.

OBS's WebSocket password remains in OBS's own configuration. The application
reads it only in memory and does not copy it into its configuration.

## Network connections

| Destination | Purpose |
| --- | --- |
| `127.0.0.1:17840` | Receives normalized Social Stream Ninja payloads locally. |
| `127.0.0.1:4455` (default) | Reads OBS WebSocket status. |
| Twitch identity and Helix APIs | Device authorization, channel info, viewers, stream updates, and markers. |
| Twitch EventSub WebSocket | Native Twitch chat and supported alerts. |

TikTok browser collection is performed by Social Stream Ninja and remains
subject to that project's and TikTok's privacy behavior. Streamer Console does
not read browser cookies.

## Documentation assets

Repository screenshots are generated off-screen from simulated names, messages,
counts, and status. They do not capture a desktop, live chat, account session, or
production credential.

## Removing local data

Follow [Uninstall](docs/UNINSTALL.md). Removing the Streamer Console data
directory does not remove or change OBS, Aitum, TikTok LIVE Studio, Voicemeeter,
Discord, Spotify, or recordings.
