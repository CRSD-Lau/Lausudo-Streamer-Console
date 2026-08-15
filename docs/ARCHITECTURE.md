# Streamer Console architecture

## Design goals

The console is a native Qt Widgets application built for a 1080x1920 portrait display. It is deliberately separate from OBS, TikTok LIVE Studio, Voicemeeter, Discord, and the game. A failure in one integration must not stop the others.

```text
Twitch chat page / connector ─┐
                              ├─ Social Stream Ninja ─ HTTP POST on 127.0.0.1 ─┐
TikTok LIVE page / connector ─┘                                                │
                                                                               ▼
                                                                     normalize + sequence
                                                                               │
                                                                               ▼
                                                                     bounded chat model
                                                                               │
OBS WebSocket ─ read-only status worker ────────────────────────────────────────┤
                                                                               ▼
                                                                    portrait Qt interface

F1 button ─ Win32 SendInput(F1) ─ existing AutoHotkey helper ─ existing privacy controller
F2 button ─ Win32 SendInput(F2) ─ existing AutoHotkey helper ─ Discord native Toggle Mute
```

## Chat collection

Social Stream Ninja owns platform-specific collection and authentication. The console never reads browser cookies or stores Twitch/TikTok credentials.

The preferred transport is Social Stream Ninja's **Send all to POST server** option, pointed at:

```text
http://127.0.0.1:17840/ingest/socialstream
```

The receiver binds only to loopback, caps request size, validates JSON, assigns a local monotonic sequence and receipt time, converts supported message markup to plain text, and returns promptly. Provider timestamps are retained as metadata when present but do not control ordering.

Only genuine viewer-chat records from Twitch and TikTok cross the normalization boundary. A record must identify one of those two platforms and contain both a viewer name and message text. Event-marked payloads, standalone follows, subscriptions, gifts, raids, bits notices, platform notices, system records, counters, placeholders, and unknown-platform payloads are structurally discarded before the retained model. A real viewer message is retained when it carries subscriber, cheer, donation, or badge metadata but is not source-marked as an event. This is an invariant rather than an optional UI filter, so a stale setting cannot make non-chat records visible. Optional bot, command, duplicate, and repeated-spam filters run only after that boundary.

Messages are deduplicated conservatively and held in a bounded model. The default retention is 750 messages. The two platform paths are independent upstream; a missing TikTok message never blocks a Twitch message. Because the POST path is fire-and-forget rather than a persistent collector socket, a platform is shown as **RECEIVING** only after recent viewer chat and ages to **NO RECENT DATA** after 30 seconds of silence. Social Stream Ninja/browser owns upstream reconnection.

The small teal status dot communicates a ready local collector or recently received chat without claiming a persistent upstream socket. Reconnecting is amber and disconnected is red.

The local POST path is fire-and-forget and has no replay queue. Start the console before starting chat collection.

## OBS status

The OBS worker connects to the existing authenticated OBS WebSocket on loopback. It reads the local OBS WebSocket configuration in memory and never logs the password. It polls a small status batch for:

- connection state
- main stream state
- recording state
- current main scene
- `Mic/Aux` mute/monitor state
- Aitum current vertical scene and output state

OBS failure changes only the OBS status area; chat stays available. Reconnection uses capped backoff.

## Stream controls

The console intentionally contains no second copy of BRB or Discord logic. Its buttons emit the same global F1/F2 keys as the keyboard:

- F1 is intercepted by the existing AutoHotkey helper and invokes `C:\Projects\OBS-Tools\PrivacyToggle\PrivacyToggle.ps1`.
- F2 is intercepted by the same helper and invokes Discord's native Toggle Mute shortcut.

The BRB button state is derived from the actual main and Aitum vertical scenes. A mixed scene state is shown as a warning rather than guessed. Discord does not expose a supported local mute-state API in this setup, so the console reports that the toggle was sent but does not fabricate a muted/unmuted state.

## Configuration and logs

Runtime state lives outside the Git repository:

```text
%LOCALAPPDATA%\NeilMitchell\StreamerConsole\
```

Configuration is written atomically. Logs rotate and record lifecycle/connection/error events only; chat text, cookies, passwords, stream keys, OAuth tokens, and Social Stream session identifiers are not logged.

## Window integration

Normal framed mode keeps the native Windows non-client frame. Windows therefore owns edge resizing, the maximize button, and Windows 11 Snap Layouts shown when the maximize button is hovered. Restored window geometry is fitted to the selected display's available work area so its title bar and resize frame remain reachable.

Borderless mode deliberately removes the native frame for a clean presentation. Without that frame there are no native resize edges, maximize-button hover target, or Windows 11 Snap Layouts. Returning to normal framed mode restores those Windows features; borderless and always-on-top remain independent preferences.

## Resource model

The UI uses Qt Widgets and a custom list model/delegate rather than a browser renderer. Networking runs in small background workers, OBS polling is bounded, the chat model has a hard limit, and there are no continuous animations.
