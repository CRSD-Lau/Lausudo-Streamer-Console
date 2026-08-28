# Configuration reference

## Location and precedence

The default runtime configuration is:

```text
%LOCALAPPDATA%\NeilMitchell\StreamerConsole\config.json
```

The application creates it from safe defaults and writes changes atomically. To
use a separate file:

```powershell
py -3.13 -m streamer_console.app --config C:\path\to\config.json
```

[`config.example.json`](../config.example.json) contains every supported group
and no credentials. Do not add OBS passwords, Twitch tokens, cookies, or stream
keys to configuration.

## Window

| Key | Default | Meaning |
| --- | --- | --- |
| `width`, `height` | `1080`, `1920` | Remembered client size. |
| `x`, `y` | `null` | Remembered position; `null` enables automatic placement. |
| `monitor_name` | empty | Preferred Windows display name. |
| `borderless` | `false` | Removes the native frame and therefore native Snap Layouts. |
| `always_on_top` | `false` | Keeps the console above normal windows. |
| `maximized` | `false` | Restores maximized state. |

## Chat

| Key | Default | Meaning |
| --- | --- | --- |
| `font_size` | `28` | Viewer-message font size. |
| `message_spacing` | `8` | Vertical separation between rows. |
| `max_messages` | `750` | Hard-bounded retained rows. |
| `show_timestamps` | `false` | Shows compact local receipt time. |
| `highlight_terms` | `Lausudo`, `@Lausudo` | Case-insensitive mention terms. |

Optional filters can hide bot names, commands, exact duplicates, or repeated
spam. The normalization boundary always drops generic system notices, joins,
like cards, raw counters, placeholders, anonymous events, and unknown platforms.
Meaningful named alerts are retained independently of optional chat filters.

## Social Stream ingestion

| Key | Default | Meaning |
| --- | --- | --- |
| `host` | `127.0.0.1` | Loopback bind. Non-loopback values are rejected. |
| `port` | `17840` | Local HTTP port. |
| `path` | `/ingest/socialstream` | POST endpoint. |
| `max_body_bytes` | `262144` | Per-request size limit. |
| `queue_size` | `1000` | Bounded delivery queue. |

## OBS and Aitum

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | Enables read-only monitoring. |
| `host` | `127.0.0.1` | OBS WebSocket host. |
| `port` | `0` | `0` reads OBS's configured port; otherwise overrides it. |
| `poll_interval_seconds` | `1.5` | Status refresh interval. |
| `mic_input` | `Mic/Aux` | OBS microphone input name used for privacy evidence. |
| `spotify_input` | `Spotify` | OBS Spotify input used for monitoring evidence. |
| `brb_main_scene` | `BRB - Main` | Main BRB scene. |
| `brb_vertical_scene` | `BRB - Vertical` | Aitum vertical BRB scene. |
| `aitum_vendor_name` | `aitum-stream-suite` | OBS WebSocket vendor namespace. |
| `aitum_vertical_canvas` | `Vertical` | Aitum canvas name. |

OBS's WebSocket password is read from OBS's own configuration only in memory.
It is not represented by a Streamer Console setting.

## Twitch

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | Enables the optional official Twitch service. |
| `client_id` | empty | Public Twitch application Client ID. Not a secret. |

Access and refresh tokens are stored separately in Windows Credential Manager
for the current Windows user. Existing DPAPI-encrypted token files remain
readable as a compatibility fallback. Tokens are never written to the ordinary
JSON configuration. A client secret and redirect URL are not used by the Device
Code flow.

## Logging

| Key | Default | Meaning |
| --- | --- | --- |
| `level` | `INFO` | Minimum diagnostic level. |
| `max_bytes` | `1048576` | Maximum bytes per log before rotation. |
| `backup_count` | `3` | Retained rotated logs. |

Logs intentionally exclude viewer chat, request bodies/headers, cookies,
passwords, tokens, stream keys, and Social Stream session identifiers.

## Safe editing

Close Streamer Console before hand-editing the runtime file so UI persistence
does not overwrite the change. Unknown forward-version keys are ignored and
invalid values fall back to bounded defaults rather than preventing startup.
