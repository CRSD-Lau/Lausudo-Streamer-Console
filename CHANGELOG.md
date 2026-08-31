# Changelog

All notable changes to Lausudo Streamer Console are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- Center the READY/LIVE/STANDBY label within its status control while retaining
  the independent teal state dot at the left edge.
- Place TikTok LIVE Studio at its supported 1200-by-740-pixel size so its own
  size constraint no longer makes F3 report a false placement failure and beep.
- Open and minimize the required TikTok LIVE source page and Twitch pop-out
  fallback alongside the Social Stream Ninja background service when F3 runs.
- Clarify that a cold TikTok launch can show TikTok's own UAC prompt while the
  protected placement task continues to run silently.

## [1.1.0] — 2026-08-30

### Added

- An independent global F3 Prepare Stream Workspace listener.
- Fail-closed three-monitor detection and work-area-aware placement for OBS,
  TikTok LIVE Studio, Streamer Console, and Discord.
- Idempotent missing-app launch, existing-window reuse, bounded readiness,
  background Social Stream Ninja/Spotify handling, and focus restoration.
- Reversible per-user Startup installation plus dedicated removal tooling.

### Security

- The F3 controller is isolated from OBS, stream, recording, scene, audio,
  Virtual Camera, Discord mute, and Voicemeeter routing state.

### Fixed

- Preserve installed working directories when launching OBS and TikTok LIVE
  Studio, preventing OBS locale-loading failures.
- Use the normal Windows elevation path for TikTok LIVE Studio and recognize
  elevated application windows without opening their process handles.
- Reuse the existing Chrome profile for Social Stream Ninja instead of creating
  a blank forced-profile app window.
- Restore foreground focus from the initiating F3 hotkey process rather than
  from a background Python child that Windows rejects.

## [1.0.1] — 2026-08-28

### Changed

- Streamer Console now starts the existing F1/F2 AutoHotkey helper with the app
  and stops only the helper process it owns during normal shutdown.
- Twitch Stream Info now explains each setup/approval/connected state, disables
  broadcast editing until authorization is ready, and clearly confirms when the
  connection is securely saved.
- Short, wide Snap layouts now compact the header, stream-status panel, Spotify
  transport, and BRB/Discord controls so the unified chat and alert feed receives
  more than twice the visible height in the shared portrait-monitor arrangement.

### Fixed

- Twitch authorization now persists through Windows Credential Manager when
  direct DPAPI access is denied, while retaining the legacy encrypted-file reader
  for existing installations.

## [1.0.0] — 2026-08-15

### Added

- One receipt-ordered Twitch and TikTok LIVE viewer feed with bounded retention.
- Meaningful follow, subscription, gift, raid, Bits, reward, and share alerts.
- Twitch Helix Stream Info, EventSub chat/alerts, viewer count, and stream markers.
- TikTok viewer, new-follow, and like activity counters from Social Stream Ninja.
- Read-only OBS WebSocket and Aitum vertical-canvas status.
- Shared F1 BRB/privacy and F2 Discord-mute controls.
- Windows Spotify media-session controls and metadata.
- Native portrait-window placement, resizing, Windows 11 Snap Layouts, application
  identity, taskbar icon, and shortcut installer.
- Aggregate-only stream session summaries and bounded rotating logs.

### Security

- Loopback-only Social Stream ingestion with request-size limits and JSON validation.
- DPAPI encryption for Twitch tokens.
- Credential redaction and no chat-body logging.
- Evidence-based BRB privacy status covering microphone monitoring and Spotify routing.

[1.1.0]: https://github.com/CRSD-Lau/Lausudo-Streamer-Console/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/CRSD-Lau/Lausudo-Streamer-Console/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/CRSD-Lau/Lausudo-Streamer-Console/releases/tag/v1.0.0
